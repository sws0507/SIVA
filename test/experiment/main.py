########################################################################################
# Copyright (c) 2024 Beijing Institute of Open Source Chip (BOSC)
#
# ChiselAIA is licensed under Mulan PSL v2.
########################################################################################

import csv
import os

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge

from common import *

try:
  csr_addr_vs_domain_bitmap
except NameError:
  csr_addr_vs_domain_bitmap = 0x78

try:
  imsic_dynamic_tag_offset
except NameError:
  imsic_dynamic_tag_offset = 0x800

try:
  offset_intsource_sec
except NameError:
  offset_intsource_sec = 0x2800


NON_SEC = 0
SEC = 1

# The RTL keeps APLIC source 0 reserved/read-only. The experiment uses logical
# source 0-7 for paper-facing reports, and maps them to RTL source 1-8.
LOGICAL_SOURCES = tuple(range(8))
RTL_SOURCE_FOR_LOGICAL = {logical: logical + 1 for logical in LOGICAL_SOURCES}
RTL_SOURCES = tuple(RTL_SOURCE_FOR_LOGICAL.values())
HARTS = (0, 1)
GUEST_FILES = (1, 2, 3, 4)

SOURCE_DOMAINS = {logical: NON_SEC if logical < 4 else SEC for logical in LOGICAL_SOURCES}
FILE_DOMAINS = {guest_file: NON_SEC if guest_file <= 2 else SEC for guest_file in GUEST_FILES}

SEC_SOURCE_MASK = sum(
  1 << RTL_SOURCE_FOR_LOGICAL[logical]
  for logical in LOGICAL_SOURCES
  if SOURCE_DOMAINS[logical] == SEC
)
SEC_FILE_BITMAP = sum(
  1 << (guest_file - 1)
  for guest_file in GUEST_FILES
  if FILE_DOMAINS[guest_file] == SEC
)

CSV_FIELDS = (
  "mode",
  "rtl_source_id",
  "logical_source_id",
  "src_domain",
  "hart_id",
  "guest_file_id",
  "file_domain",
  "eiid",
  "msi_addr",
  "msi_data",
  "addr_sec",
  "commit",
  "commit_hart",
  "commit_guest_file",
  "commit_domain",
  "result_class",
  "target_eip0",
  "target_topei",
  "target_pendings",
  "target_notifies",
  "invariant_ok",
)


def domain_name(domain):
  return "sec" if domain else "non-sec"


def get_signal(dut, path):
  handle = dut
  for name in path.split("."):
    handle = getattr(handle, name)
  return handle


def has_signal(dut, name):
  try:
    get_signal(dut, name)
    return True
  except AttributeError:
    return False


def int_signal(dut, name, default=0):
  try:
    return int(get_signal(dut, name).value)
  except (AttributeError, ValueError):
    return default


def is_dtid_dut(dut):
  return has_signal(dut, "sec0") and has_signal(dut, "toCSR0_notifies")


async def maybe_set_sec(dut, domain, hart, dtid_enabled):
  if dtid_enabled:
    await set_sec(dut, domain, hart)


async def setup_clock_reset(dut):
  cocotb.start_soon(Clock(dut.clock, 1, unit="ns").start())
  dut.reset.value = 1
  dut.toaia_0_a_valid.value = 0
  dut.toaia_0_d_ready.value = 1
  for source in RTL_SOURCES:
    getattr(dut, f"intSrcs_{source}").value = 0
  for hart in range(4):
    if has_signal(dut, f"sec{hart}"):
      getattr(dut, f"sec{hart}").value = 0
  for _ in range(10):
    await RisingEdge(dut.clock)
  dut.reset.value = 0
  await FallingEdge(dut.clock)


async def enable_vs_file(dut, hart, guest_file, dtid_enabled):
  file_domain = FILE_DOMAINS[guest_file]
  await maybe_set_sec(dut, file_domain, hart, dtid_enabled)
  await select_vs_intfile(dut, guest_file, hart)
  await write_csr(dut, csr_addr_eidelivery, 1, hart)
  await write_csr(dut, csr_addr_eie0, -1, hart)
  await write_csr(dut, csr_addr_eip0, 0, hart)


async def init_imsics(dut, dtid_enabled):
  for hart in HARTS:
    await maybe_set_sec(dut, NON_SEC, hart, dtid_enabled)
    await select_m_intfile(dut, hart)
    await write_csr(dut, csr_addr_eidelivery, 1, hart)
    await write_csr(dut, csr_addr_eie0, -1, hart)
    if dtid_enabled:
      await write_csr(dut, csr_addr_vs_domain_bitmap, SEC_FILE_BITMAP, hart)
    for guest_file in GUEST_FILES:
      await enable_vs_file(dut, hart, guest_file, dtid_enabled)


async def clear_guest_files(dut, dtid_enabled):
  for hart in HARTS:
    for guest_file in GUEST_FILES:
      await maybe_set_sec(dut, FILE_DOMAINS[guest_file], hart, dtid_enabled)
      await select_vs_intfile(dut, guest_file, hart)
      await write_csr(dut, csr_addr_eip0, 0, hart)


async def init_aplic(dut, dtid_enabled):
  await a_put_full32(dut, aplic_m_base_addr + offset_domaincfg, 0x80000104)
  await a_put_full32(dut, aplic_sg_base_addr + offset_domaincfg, 0x80000104)

  for source in RTL_SOURCES:
    source_offset = (source - 1) * 4
    await a_put_full32(dut, aplic_m_base_addr + offset_sourcecfg + source_offset, 1 << 10)
    await a_put_full32(dut, aplic_sg_base_addr + offset_sourcecfg + source_offset, sourcecfg_sm_edge1)

  enable_mask = sum(1 << source for source in RTL_SOURCES)
  await a_put_full32(dut, aplic_m_base_addr + offset_seties, enable_mask)
  await a_put_full32(dut, aplic_sg_base_addr + offset_seties, enable_mask)

  if dtid_enabled:
    await a_put_full32(dut, aplic_m_base_addr + offset_intsource_sec, SEC_SOURCE_MASK)
    await a_put_full32(dut, aplic_sg_base_addr + offset_intsource_sec, SEC_SOURCE_MASK)


async def program_target(dut, rtl_source, hart, guest_file, eiid):
  target_value = (hart << 18) | (guest_file << 12) | eiid
  await a_put_full32(
    dut,
    aplic_sg_base_addr + offset_targets + (rtl_source - 1) * 4,
    target_value,
  )


async def trigger_source_and_capture_msi(dut, rtl_source):
  source_signal = getattr(dut, f"intSrcs_{rtl_source}")
  source_signal.value = 0
  await FallingEdge(dut.clock)
  source_signal.value = 1

  captured_addr = None
  captured_data = None
  for _ in range(80):
    await RisingEdge(dut.clock)
    valid = int_signal(dut, "aplic.auto_toIMSIC_out_a_valid")
    if valid:
      captured_addr = int_signal(dut, "aplic.auto_toIMSIC_out_a_bits_address")
      captured_data = int_signal(dut, "aplic.auto_toIMSIC_out_a_bits_data")
      break

  source_signal.value = 0
  await delay_fifo(dut)

  assert captured_addr is not None, f"APLIC did not emit an MSI for RTL source {rtl_source}"
  return captured_addr, captured_data


async def observe_guest_file(dut, hart, guest_file, eiid, dtid_enabled):
  file_domain = FILE_DOMAINS[guest_file]
  await maybe_set_sec(dut, file_domain, hart, dtid_enabled)
  await select_vs_intfile(dut, guest_file, hart)
  await FallingEdge(dut.clock)

  topei = int_signal(dut, f"toCSR{hart}_topeis_2")
  pendings = int_signal(dut, f"toCSR{hart}_pendings")
  notifies = int_signal(dut, f"toCSR{hart}_notifies")
  eip0 = await read_csr(dut, csr_addr_eip0, hart)
  committed = topei == wrap_topei(eiid) or bool(eip0 & (1 << eiid))

  return {
    "hart": hart,
    "guest_file": guest_file,
    "domain": file_domain,
    "topei": topei,
    "pendings": pendings,
    "notifies": notifies,
    "eip0": eip0,
    "committed": committed,
  }


async def scan_commits(dut, eiid, dtid_enabled):
  observations = []
  commits = []
  for hart in HARTS:
    for guest_file in GUEST_FILES:
      obs = await observe_guest_file(dut, hart, guest_file, eiid, dtid_enabled)
      observations.append(obs)
      if obs["committed"]:
        commits.append(obs)
  return observations, commits


def classify_result(commits):
  if not commits:
    return "dropped"
  if commits[0]["domain"] == SEC:
    return "sec_commit"
  return "nonsec_commit"


def target_observation(observations, hart, guest_file):
  for obs in observations:
    if obs["hart"] == hart and obs["guest_file"] == guest_file:
      return obs
  assert False, "target observation missing"


def check_expectation(dtid_enabled, src_domain, file_domain, commits):
  if dtid_enabled:
    if src_domain == file_domain:
      return len(commits) == 1 and commits[0]["domain"] == file_domain
    return len(commits) == 0

  # Baseline AIA has no domain check; the programmed target should commit.
  return len(commits) == 1


def write_csv(rows):
  os.makedirs("results", exist_ok=True)
  with open("results/dtid_cross_domain_matrix.csv", "w", newline="") as csv_file:
    writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
    writer.writeheader()
    writer.writerows(rows)


def log_summary(dut, mode, rows):
  buckets = {}
  for row in rows:
    key = (row["src_domain"], row["file_domain"], row["result_class"])
    buckets[key] = buckets.get(key, 0) + 1

  dut._log.info("experiment mode: %s", mode)
  for key in sorted(buckets):
    src_domain, file_domain, result = key
    dut._log.info(
      "src=%s target=%s result=%s count=%d",
      src_domain,
      file_domain,
      result,
      buckets[key],
    )


@cocotb.test()
async def dtid_cross_domain_matrix_test(dut):
  await setup_clock_reset(dut)

  dtid_enabled = is_dtid_dut(dut)
  mode = "DTID" if dtid_enabled else "AIA"
  await init_imsics(dut, dtid_enabled)
  await init_aplic(dut, dtid_enabled)

  rows = []
  failed = []

  for logical_source in LOGICAL_SOURCES:
    rtl_source = RTL_SOURCE_FOR_LOGICAL[logical_source]
    src_domain = SOURCE_DOMAINS[logical_source]
    for hart in HARTS:
      for guest_file in GUEST_FILES:
        file_domain = FILE_DOMAINS[guest_file]
        eiid = 16 + rtl_source

        await clear_guest_files(dut, dtid_enabled)
        await program_target(dut, rtl_source, hart, guest_file, eiid)
        msi_addr, msi_data = await trigger_source_and_capture_msi(dut, rtl_source)
        observations, commits = await scan_commits(dut, eiid, dtid_enabled)

        target = target_observation(observations, hart, guest_file)
        invariant_ok = all(commit["domain"] == src_domain for commit in commits)
        expected_ok = check_expectation(dtid_enabled, src_domain, file_domain, commits)
        result_class = classify_result(commits)
        commit = commits[0] if commits else None

        row = {
          "mode": mode,
          "rtl_source_id": rtl_source,
          "logical_source_id": logical_source,
          "src_domain": domain_name(src_domain),
          "hart_id": hart,
          "guest_file_id": guest_file,
          "file_domain": domain_name(file_domain),
          "eiid": eiid,
          "msi_addr": f"0x{msi_addr:x}",
          "msi_data": f"0x{msi_data:x}",
          "addr_sec": 1 if (msi_addr & imsic_dynamic_tag_offset) else 0,
          "commit": 1 if commits else 0,
          "commit_hart": "" if commit is None else commit["hart"],
          "commit_guest_file": "" if commit is None else commit["guest_file"],
          "commit_domain": "" if commit is None else domain_name(commit["domain"]),
          "result_class": result_class,
          "target_eip0": f"0x{target['eip0']:x}",
          "target_topei": f"0x{target['topei']:x}",
          "target_pendings": f"0x{target['pendings']:x}",
          "target_notifies": f"0x{target['notifies']:x}",
          "invariant_ok": 1 if invariant_ok else 0,
        }
        rows.append(row)

        if not invariant_ok or not expected_ok:
          failed.append(row)

  write_csv(rows)
  log_summary(dut, mode, rows)

  assert not failed, f"cross-domain experiment found {len(failed)} unexpected events"
