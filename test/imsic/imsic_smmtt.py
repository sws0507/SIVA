########################################################################################
# Copyright (c) 2024 Beijing Institute of Open Source Chip (BOSC)
#
# ChiselAIA is licensed under Mulan PSL v2.
########################################################################################

import cocotb
from cocotb.triggers import FallingEdge
from imsic_common import *


@cocotb.test()
async def imsic_smmtt_bank_selection_test(dut):
  """Simple Smmtt bank selection, pending summary, and invalid SDICN behavior."""
  await setup_imsic(dut)

  cocotb.log.info("simple_smmtt_bank_selection began")
  await set_sdicn(dut, 0)
  await select_s_intfile(dut)
  await s_int(dut, 1234 % 256, domain=0)
  await FallingEdge(dut.clock)
  await delay_fifo(dut)
  assert int(dut.toCSR1_topeis_1.value) == wrap_topei(1234 % 256)

  await set_sdicn(dut, 1)
  await select_s_intfile(dut)
  assert int(dut.toCSR1_topeis_1.value) == wrap_topei(0)
  await s_int(dut, 77, domain=1)
  await FallingEdge(dut.clock)
  await delay_fifo(dut)
  assert int(dut.toCSR1_topeis_1.value) == wrap_topei(77)

  await set_sdicn(dut, 0)
  await select_s_intfile(dut)
  assert int(dut.toCSR1_topeis_1.value) == wrap_topei(1234 % 256)

  await set_sdicn(dut, 1)
  await select_vs_intfile(dut, 2)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(0)
  await v_int_vgein(dut, 138, guestID=2, domain=1)
  await FallingEdge(dut.clock)
  await delay_fifo(dut)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(138)

  assert int(dut.toSmmtt1_msdeip.value) & 0b11 == 0b11
  await set_msdeie(dut, 1 << 1)
  await FallingEdge(dut.clock)
  assert int(dut.toSmmtt1_lsdeip.value) == 1
  await set_msdeie(dut, 0)
  await FallingEdge(dut.clock)
  assert int(dut.toSmmtt1_lsdeip.value) == 0

  await set_sdicn(dut, 2)
  await select_s_intfile(dut)
  await write_csr(dut, csr_addr_eidelivery, 1)
  assert int(dut.toCSR1_illegal.value) == 1
  await set_sdicn(dut, 0)
  await select_m_intfile(dut)
  cocotb.log.info("simple_smmtt_bank_selection end")


@cocotb.test()
async def imsic_smmtt_inactive_domain1_vs_msi_test(dut):
  """A domain 1 VS MSI is summarized while SDICN selects domain 0."""
  await setup_imsic(dut)

  guest_id = 2
  int_id = 201
  guest_pending_bit = 1 << (1 + guest_id)

  await set_sdicn(dut, 0)
  await set_msdeie(dut, 0)
  await select_vs_intfile(dut, guest_id)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(0)

  await v_int_vgein(dut, int_id, guestID=guest_id, domain=1)
  await FallingEdge(dut.clock)
  await delay_fifo(dut)

  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(0)
  assert int(dut.toCSR1_pendings.value) & guest_pending_bit == 0
  assert int(dut.toSmmtt1_msdeip.value) & 0b11 == 0b10
  assert int(dut.toSmmtt1_lsdeip.value) == 0

  await set_msdeie(dut, 1 << 1)
  await FallingEdge(dut.clock)
  assert int(dut.toSmmtt1_lsdeip.value) == 1

  await set_msdeie(dut, 0)
  await FallingEdge(dut.clock)
  assert int(dut.toSmmtt1_lsdeip.value) == 0

  await set_sdicn(dut, 1)
  await select_vs_intfile(dut, guest_id)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(int_id)
  assert int(dut.toCSR1_pendings.value) & guest_pending_bit != 0


@cocotb.test()
async def imsic_smmtt_inactive_domain0_vs_msi_test(dut):
  """A domain 0 VS MSI is summarized while SDICN selects domain 1."""
  await setup_imsic(dut)

  guest_id = 2
  int_id = 202
  guest_pending_bit = 1 << (1 + guest_id)

  await set_sdicn(dut, 1)
  await set_msdeie(dut, 0)
  await select_vs_intfile(dut, guest_id)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(0)

  await v_int_vgein(dut, int_id, guestID=guest_id, domain=0)
  await FallingEdge(dut.clock)
  await delay_fifo(dut)

  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(0)
  assert int(dut.toCSR1_pendings.value) & guest_pending_bit == 0
  assert int(dut.toSmmtt1_msdeip.value) & 0b11 == 0b01
  assert int(dut.toSmmtt1_lsdeip.value) == 0

  await set_msdeie(dut, 1 << 0)
  await FallingEdge(dut.clock)
  assert int(dut.toSmmtt1_lsdeip.value) == 1

  await set_msdeie(dut, 0)
  await FallingEdge(dut.clock)
  assert int(dut.toSmmtt1_lsdeip.value) == 0

  await set_sdicn(dut, 0)
  await select_vs_intfile(dut, guest_id)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(int_id)
  assert int(dut.toCSR1_pendings.value) & guest_pending_bit != 0
