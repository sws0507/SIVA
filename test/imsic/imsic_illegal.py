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


async def clear_illegal(dut):
  await FallingEdge(dut.clock)
  await FallingEdge(dut.clock)
  dut.toCSR1_illegal.value = 0


@cocotb.test()
async def imsic_illegal_iselect_test(dut):
  await setup_imsic(dut)
  await write_csr_op(dut, 0x81, 0xc0, op_csrrs)
  assert int(dut.toCSR1_illegal.value) == 1


@cocotb.test()
async def imsic_illegal_vgein_test(dut):
  await setup_imsic(dut)
  await clear_illegal(dut)
  await select_vs_intfile(dut, 8)
  await write_csr(dut, csr_addr_eidelivery, 1)
  assert int(dut.toCSR1_illegal.value) == 1


@cocotb.test()
async def imsic_illegal_wdata_op_test(dut):
  await setup_imsic(dut)
  await clear_illegal(dut)
  await write_csr_op(dut, csr_addr_eidelivery, 0xc0, op_illegal)
  assert int(dut.toCSR1_illegal.value) == 1


@cocotb.test()
async def imsic_illegal_privilege_test(dut):
  await setup_imsic(dut)
  await clear_illegal(dut)
  fromCSR1_priv = getattr(dut, "fromCSR1_addr_bits_priv")
  fromCSR1_virt = getattr(dut, "fromCSR1_addr_bits_virt")
  fromCSR1_priv.value = 3
  fromCSR1_virt.value = 1
  await write_csr(dut, csr_addr_eidelivery, 0xfa)
  assert int(dut.toCSR1_illegal.value) == 1
