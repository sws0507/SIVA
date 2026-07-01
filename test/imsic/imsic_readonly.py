########################################################################################
# Copyright (c) 2024 Beijing Institute of Open Source Chip (BOSC)
#
# ChiselAIA is licensed under Mulan PSL v2.
########################################################################################

import cocotb
from imsic_common import *


@cocotb.test()
async def imsic_eip0_readonly_zero_test(dut):
  """EIP bit 0 stays read-only zero through CSR and MSI writes."""
  await setup_imsic(dut)

  cocotb.log.info("eip0[0]_readonly_0:write_csr began")
  await write_csr(dut, csr_addr_eip0, 0x1)
  rdata = await read_csr(dut, csr_addr_eip0)
  assert rdata == 0
  cocotb.log.info("eip0[0]_readonly_0:write_csr passed")

  cocotb.log.info("eip0[0]_readonly_0:seteipnum began")
  await m_int(dut, 0)
  rdata = await read_csr(dut, csr_addr_eip0)
  assert rdata == 0
  cocotb.log.info("eip0[0]_readonly_0:seteipnum passed")
