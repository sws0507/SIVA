########################################################################################
# Copyright (c) 2024 Beijing Institute of Open Source Chip (BOSC)
#
# ChiselAIA is licensed under Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#          http://license.coscl.org.cn/MulanPSL2
#
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
# EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
# MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE.
#
# See the Mulan PSL v2 for more details.
########################################################################################

import cocotb
from cocotb.triggers import FallingEdge
from common import *
from imsic_common import setup_imsic


def vs_pending_bit(guest_id):
  return 1 << (1 + guest_id)


@cocotb.test()
async def imsic_dynamic_tag_s_file_test(dut):
  await setup_imsic(dut)

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
  await setup_imsic(dut)

  await select_m_intfile(dut)
  await write_csr(dut, csr_addr_vs_domain_bitmap, 1 << (3 - 1))
  await set_sec(dut, 0)
  await select_vs_intfile(dut, 3)

  await v_int_vgein(dut, 211, guestID=3)
  await FallingEdge(dut.clock)
  await delay_fifo(dut)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(0)

  await v_int_vgein_sec(dut, 211, guestID=3)
  await FallingEdge(dut.clock)
  await delay_fifo(dut)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(0)
  assert int(dut.toCSR1_notifies.value) & vs_pending_bit(3)

  await set_sec(dut, 1)
  await select_vs_intfile(dut, 3)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(211)
  assert int(dut.toCSR1_pendings.value) & vs_pending_bit(3)


@cocotb.test()
async def imsic_dynamic_tag_csr_guard_test(dut):
  await setup_imsic(dut)

  await select_m_intfile(dut)
  await write_csr(dut, csr_addr_vs_domain_bitmap, 1 << (3 - 1))
  await select_vs_intfile(dut, 3)
  await v_int_vgein_sec(dut, 211, guestID=3)
  await FallingEdge(dut.clock)
  await delay_fifo(dut)
  await set_sec(dut, 1)
  await select_vs_intfile(dut, 3)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(211)

  await set_sec(dut, 0)
  await select_vs_intfile(dut, 3)
  await write_csr(dut, csr_addr_eidelivery, 0)
  assert int(dut.toCSR1_illegal.value) == 1
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(0)
  assert int(dut.toCSR1_notifies.value) & vs_pending_bit(3)

  await set_sec(dut, 1)
  await select_vs_intfile(dut, 3)
  await write_csr(dut, csr_addr_eidelivery, 0)
  await FallingEdge(dut.clock)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(0)
