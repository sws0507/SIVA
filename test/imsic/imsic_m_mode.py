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


@cocotb.test()
async def imsic_m_mode_interrupt_test(dut):
  await setup_imsic(dut)
  await select_m_intfile(dut)

  await m_int(dut, 1996 % 256)
  await FallingEdge(dut.clock)
  await delay_fifo(dut)
  assert int(dut.toCSR1_topeis_0.value) == wrap_topei(1996 % 256)
  assert int(dut.toCSR1_pendings.value) & 1
  assert (int(dut.toCSR1_notifies.value) & 1) == 0

  await claim(dut)
  assert int(dut.toCSR1_topeis_0.value) == wrap_topei(0)

  await m_int(dut, 12)
  await FallingEdge(dut.clock)
  await delay_fifo(dut)
  assert int(dut.toCSR1_topeis_0.value) == wrap_topei(12)

  await m_int(dut, 8)
  await FallingEdge(dut.clock)
  await delay_fifo(dut)
  assert int(dut.toCSR1_topeis_0.value) == wrap_topei(8)

  await claim(dut)
  assert int(dut.toCSR1_topeis_0.value) == wrap_topei(12)
