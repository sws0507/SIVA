import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge
from common import *


async def start_imsic_test(dut, imsicID=1):
  cocotb.start_soon(Clock(dut.clock, 1, unit="ns").start())

  dut.reset.value = 1
  for _ in range(10):
    await RisingEdge(dut.clock)
  dut.reset.value = 0

  dut.toaia_0_d_ready.value = 1
  await FallingEdge(dut.clock)

  await set_smmtt_enable(dut, 1, imsicID)
  await set_sdicn(dut, 1, imsicID)
  await set_msdeie(dut, 0, imsicID)
  await select_m_intfile(dut, imsicID)


async def enable_current_file(dut, *intnums, imsicID=1):
  await write_csr(dut, csr_addr_eidelivery, 1, imsicID)
  for eix in sorted({int(intnum) // 64 for intnum in intnums}):
    await write_csr(dut, csr_addr_eie0 + 2 * eix, -1, imsicID)


async def enable_m_file(dut, *intnums, imsicID=1):
  await select_m_intfile(dut, imsicID)
  await enable_current_file(dut, *intnums, imsicID=imsicID)


async def enable_s_file(dut, domain, *intnums, imsicID=1):
  await set_sdicn(dut, domain + 1, imsicID)
  await select_s_intfile(dut, imsicID)
  await enable_current_file(dut, *intnums, imsicID=imsicID)


async def enable_vs_file(dut, domain, vgein, *intnums, imsicID=1):
  await set_sdicn(dut, domain + 1, imsicID)
  await select_vs_intfile(dut, vgein, imsicID)
  await enable_current_file(dut, *intnums, imsicID=imsicID)


async def wait_for_msi(dut):
  await FallingEdge(dut.clock)
  await delay_fifo(dut)
