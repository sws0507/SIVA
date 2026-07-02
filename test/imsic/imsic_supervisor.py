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
async def imsic_supervisor_and_vs_test(dut):
  await setup_imsic(dut)

  await select_s_intfile(dut)
  assert int(dut.toCSR1_topeis_1.value) == wrap_topei(0)
  await s_int(dut, 1234 % 256)
  await FallingEdge(dut.clock)
  await delay_fifo(dut)
  assert int(dut.toCSR1_topeis_1.value) == wrap_topei(1234 % 256)
  await select_m_intfile(dut)

  await select_vs_intfile(dut, 2)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(0)
  await v_int_vgein(dut, 137)
  await FallingEdge(dut.clock)
  await delay_fifo(dut)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(137)
  await select_m_intfile(dut)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(137)
