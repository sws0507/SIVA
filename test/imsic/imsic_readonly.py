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
from common import *
from imsic_common import setup_imsic


@cocotb.test()
async def imsic_eip0_readonly_zero_test(dut):
  await setup_imsic(dut)

  await write_csr(dut, csr_addr_eip0, 0x1)
  rdata = await read_csr(dut, csr_addr_eip0)
  assert rdata == 0

  await m_int(dut, 0)
  rdata = await read_csr(dut, csr_addr_eip0)
  assert rdata == 0
