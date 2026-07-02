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
async def imsic_csr_access_test(dut):
  await setup_imsic(dut)
  await select_m_intfile(dut)
  await m_int(dut, 12)
  await FallingEdge(dut.clock)
  await delay_fifo(dut)

  await write_csr_op(dut, csr_addr_eidelivery, 0xc0, op_csrrs)
  assert int(dut.toCSR1_illegal.value) == 0
  await write_csr_op(dut, csr_addr_eidelivery, 0xc0, op_csrrc)

  await write_csr(dut, csr_addr_eidelivery, 0)
  await write_csr(dut, csr_addr_eidelivery, 1)

  mtopei = int(dut.toCSR1_topeis_0.value)
  await write_csr(dut, csr_addr_eithreshold, mtopei & 0x7ff)
  assert int(dut.toCSR1_topeis_0.value) != wrap_topei(mtopei)
  await write_csr(dut, csr_addr_eithreshold, mtopei + 1)
  assert int(dut.toCSR1_topeis_0.value) == mtopei
  await write_csr(dut, csr_addr_eithreshold, 0)

  await write_csr(dut, csr_addr_eip0, 0xc)
  assert int(dut.toCSR1_topeis_0.value) == wrap_topei(2)

  mtopei = int(dut.toCSR1_topeis_0.value)
  mask = 1 << (mtopei & 0x7ff)
  await write_csr_op(dut, csr_addr_eie0, mask, op_csrrc)
  assert int(dut.toCSR1_topeis_0.value) != mtopei
  await write_csr_op(dut, csr_addr_eie0, mask, op_csrrs)
  assert int(dut.toCSR1_topeis_0.value) == mtopei

  await read_csr(dut, csr_addr_eie0)
  await FallingEdge(dut.clock)
