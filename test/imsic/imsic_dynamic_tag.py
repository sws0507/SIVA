########################################################################################
# Copyright (c) 2024 Beijing Institute of Open Source Chip (BOSC)
#
# ChiselAIA is licensed under Mulan PSL v2.
########################################################################################

import cocotb
from cocotb.triggers import FallingEdge
from imsic_common import *


def vs_pending_bit(guest_id):
  return 1 << (1 + guest_id)


@cocotb.test()
async def imsic_dynamic_tag_s_file_test(dut):
  """Pooling mode selects non-sec/sec S files with the 0x800 address tag."""
  await setup_imsic(dut)
  await set_smmtt_enable(dut, 0)

  await set_sec(dut, 1)
  await select_s_intfile(dut)
  await write_csr(dut, csr_addr_eidelivery, 1)
  for e in range(0, 32):
    await write_csr(dut, csr_addr_eie0 + 2 * e, -1)

  assert int(dut.toCSR1_topeis_1.value) == wrap_topei(0)
  await s_int_sec(dut, 77)
  await FallingEdge(dut.clock)
  await delay_fifo(dut)
  assert int(dut.toCSR1_topeis_1.value) == wrap_topei(77)


@cocotb.test()
async def imsic_dynamic_tag_vs_file_test(dut):
  """VS MSI writes are accepted only when the address tag matches the bitmap."""
  await setup_imsic(dut)
  await set_smmtt_enable(dut, 0)

  guest_id = 3
  await select_m_intfile(dut)
  await write_csr(dut, csr_addr_vs_domain_bitmap, 1 << (guest_id - 1))
  await set_sec(dut, 0)
  await select_vs_intfile(dut, guest_id)

  await v_int_vgein(dut, 211, guestID=guest_id)
  await FallingEdge(dut.clock)
  await delay_fifo(dut)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(0)

  await v_int_vgein_sec(dut, 211, guestID=guest_id)
  await FallingEdge(dut.clock)
  await delay_fifo(dut)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(0)
  assert int(dut.toCSR1_notifies.value) & vs_pending_bit(guest_id)

  await set_sec(dut, 1)
  await select_vs_intfile(dut, guest_id)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(211)
  assert int(dut.toCSR1_pendings.value) & vs_pending_bit(guest_id)


@cocotb.test()
async def imsic_dynamic_tag_csr_guard_test(dut):
  """A non-sec CSR write to a sec VS file is silently ignored."""
  await setup_imsic(dut)
  await set_smmtt_enable(dut, 0)

  guest_id = 3
  await select_m_intfile(dut)
  await write_csr(dut, csr_addr_vs_domain_bitmap, 1 << (guest_id - 1))
  await FallingEdge(dut.clock)
  await set_sec(dut, 0)
  await select_vs_intfile(dut, guest_id)
  await v_int_vgein_sec(dut, 211, guestID=guest_id)
  await FallingEdge(dut.clock)
  await delay_fifo(dut)

  await set_sec(dut, 1)
  await select_vs_intfile(dut, guest_id)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(211)

  await set_sec(dut, 0)
  await select_vs_intfile(dut, guest_id)
  await write_csr(dut, csr_addr_eidelivery, 0)
  await FallingEdge(dut.clock)
  assert int(dut.toCSR1_illegal.value) == 0
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(0)
  assert int(dut.toCSR1_notifies.value) & vs_pending_bit(guest_id)

  await set_sec(dut, 1)
  await select_vs_intfile(dut, guest_id)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(211)
  await write_csr(dut, csr_addr_eidelivery, 0)
  await FallingEdge(dut.clock)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(0)
