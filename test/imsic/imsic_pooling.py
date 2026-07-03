########################################################################################
# Copyright (c) 2024 Beijing Institute of Open Source Chip (BOSC)
#
# ChiselAIA is licensed under Mulan PSL v2.
########################################################################################

import cocotb
from cocotb.triggers import FallingEdge
from imsic_common import *


@cocotb.test()
async def imsic_pooling_vs_msi_test(dut):
  """Pooling mode maps logical VS files across physical IMSIC banks."""
  await setup_imsic(dut)
  await set_smmtt_enable(dut, 0)

  logical_vgein = imsic_geilen + 2
  int_id = 211
  pending_bit = 1 << (1 + logical_vgein)

  await select_vs_intfile(dut, logical_vgein)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(0)

  await pooled_vs_int_vgein(dut, int_id, vgein=logical_vgein)
  await FallingEdge(dut.clock)
  await delay_fifo(dut)

  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(int_id)
  assert int(dut.toCSR1_pendings.value) & pending_bit != 0
  assert int(dut.toSmmtt1_msdeip.value) == 0
  assert int(dut.toSmmtt1_lsdeip.value) == 0


@cocotb.test()
async def imsic_pooling_extra_s_slot_reinterpreted_as_vs_test(dut):
  """Pooling mode keeps one S file and reinterprets extra S slots as VS files."""
  await setup_imsic(dut)
  await set_smmtt_enable(dut, 0)

  s_int_id = 55
  vs_int_id = 66
  logical_vgein = imsic_geilen + 1

  await select_s_intfile(dut)
  await s_int(dut, s_int_id, domain=0)
  await FallingEdge(dut.clock)
  await delay_fifo(dut)
  assert int(dut.toCSR1_topeis_1.value) == wrap_topei(s_int_id)

  await select_vs_intfile(dut, logical_vgein)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(0)
  await a_put_full32(dut, imsic_sg_file_addr(domain=1, guestID=0), vs_int_id)
  await FallingEdge(dut.clock)
  await delay_fifo(dut)

  await select_s_intfile(dut)
  assert int(dut.toCSR1_topeis_1.value) == wrap_topei(s_int_id)
  await select_vs_intfile(dut, logical_vgein)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(vs_int_id)


@cocotb.test()
async def imsic_pooling_invalid_tail_slot_drops_msi_test(dut):
  """An unpooled tail SG slot is dropped and does not block later MSI delivery."""
  await setup_imsic(dut)
  await set_smmtt_enable(dut, 0)

  invalid_domain = imsic_imsic_num - 1
  invalid_guest = imsic_sg_files_per_domain - 1
  valid_vgein = imsic_pooled_geilen
  valid_int_id = 89

  await a_put_full32(dut, imsic_sg_file_addr(domain=invalid_domain, guestID=invalid_guest), 88)
  await FallingEdge(dut.clock)
  await delay_fifo(dut)

  await select_vs_intfile(dut, valid_vgein)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(0)

  await pooled_vs_int_vgein(dut, valid_int_id, vgein=valid_vgein)
  await FallingEdge(dut.clock)
  await delay_fifo(dut)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(valid_int_id)
