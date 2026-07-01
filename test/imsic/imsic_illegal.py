########################################################################################
# Copyright (c) 2024 Beijing Institute of Open Source Chip (BOSC)
#
# ChiselAIA is licensed under Mulan PSL v2.
########################################################################################

import cocotb
from imsic_common import *


@cocotb.test()
async def imsic_illegal_iselect_test(dut):
  """Illegal CSR select value."""
  await setup_imsic(dut)
  await write_csr_op(dut, 0x81, 0xc0, op_csrrs)
  assert int(dut.toCSR1_illegal.value) == 1


@cocotb.test()
async def imsic_illegal_vgein_test(dut):
  """Illegal VS guest index."""
  await setup_imsic(dut)
  await select_vs_intfile(dut, 8)
  await write_csr(dut, csr_addr_eidelivery, 1)
  assert int(dut.toCSR1_illegal.value) == 1


@cocotb.test()
async def imsic_illegal_wdata_op_test(dut):
  """Illegal CSR write operation encoding."""
  await setup_imsic(dut)
  await write_csr_op(dut, csr_addr_eidelivery, 0xc0, op_illegal)
  assert int(dut.toCSR1_illegal.value) == 1


@cocotb.test()
async def imsic_illegal_privilege_test(dut):
  """Illegal M+virtual privilege combination."""
  await setup_imsic(dut)
  fromCSR1_priv = getattr(dut, "fromCSR1_addr_bits_priv")
  fromCSR1_virt = getattr(dut, "fromCSR1_addr_bits_virt")
  fromCSR1_priv.value = 3
  fromCSR1_virt.value = 1
  await write_csr(dut, csr_addr_eidelivery, 0xfa)
  assert int(dut.toCSR1_illegal.value) == 1
