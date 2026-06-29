import cocotb
from cocotb.triggers import FallingEdge
from imsic_split_common import *


async def settle_illegal(dut):
  await FallingEdge(dut.clock)
  await FallingEdge(dut.clock)


@cocotb.test()
async def imsic_illegal_and_readonly_test(dut):
  await start_imsic_test(dut)

  cocotb.log.info("illegal iselect began")
  await select_m_intfile(dut)
  await write_csr_op(dut, 0x81, 0xc0, op_csrrs)
  assert int(dut.toCSR1_illegal.value) == 1
  cocotb.log.info("illegal iselect passed")

  cocotb.log.info("invalid sdicn began")
  await settle_illegal(dut)
  await set_sdicn(dut, 0)
  await select_s_intfile(dut)
  await write_csr(dut, csr_addr_eidelivery, 1)
  assert int(dut.toCSR1_illegal.value) == 1
  cocotb.log.info("invalid sdicn passed")

  cocotb.log.info("illegal vgein began")
  await settle_illegal(dut)
  await set_sdicn(dut, 1)
  await select_vs_intfile(dut, 8)
  await write_csr(dut, csr_addr_eidelivery, 1)
  assert int(dut.toCSR1_illegal.value) == 1
  cocotb.log.info("illegal vgein passed")

  cocotb.log.info("illegal wdata op began")
  await settle_illegal(dut)
  await select_m_intfile(dut)
  await write_csr_op(dut, csr_addr_eidelivery, 0xc0, op_illegal)
  assert int(dut.toCSR1_illegal.value) == 1
  cocotb.log.info("illegal wdata op passed")

  cocotb.log.info("illegal privilege began")
  await settle_illegal(dut)
  dut.fromCSR1_addr_bits_priv.value = 3
  dut.fromCSR1_addr_bits_virt.value = 1
  await write_csr(dut, csr_addr_eidelivery, 0xfa)
  assert int(dut.toCSR1_illegal.value) == 1
  cocotb.log.info("illegal privilege passed")

  cocotb.log.info("eip0 bit0 read-only began")
  await settle_illegal(dut)
  await select_m_intfile(dut)
  await write_csr(dut, csr_addr_eip0, 0x1)
  assert await read_csr(dut, csr_addr_eip0) == 0

  await m_int(dut, 0)
  assert await read_csr(dut, csr_addr_eip0) == 0
  cocotb.log.info("eip0 bit0 read-only passed")
