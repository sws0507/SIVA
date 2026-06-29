import cocotb
from cocotb.triggers import FallingEdge
from imsic_split_common import *


@cocotb.test()
async def imsic_m_csr_test(dut):
  await start_imsic_test(dut)
  await enable_m_file(dut, 2, 3, 5)
  await select_m_intfile(dut)

  cocotb.log.info("m-mode CSR operations began")
  await write_csr_op(dut, csr_addr_eidelivery, 0xc0, op_csrrs)
  assert int(dut.toCSR1_illegal.value) == 0
  await write_csr_op(dut, csr_addr_eidelivery, 0xc0, op_csrrc)

  await write_csr(dut, csr_addr_eidelivery, 0)
  await write_csr(dut, csr_addr_eidelivery, 1)

  await m_int(dut, 5)
  await wait_for_msi(dut)
  assert int(dut.toCSR1_topeis_0.value) == wrap_topei(5)

  await write_csr(dut, csr_addr_eithreshold, 5)
  assert int(dut.toCSR1_topeis_0.value) == wrap_topei(0)
  await write_csr(dut, csr_addr_eithreshold, 6)
  assert int(dut.toCSR1_topeis_0.value) == wrap_topei(5)
  await write_csr(dut, csr_addr_eithreshold, 0)

  await write_csr(dut, csr_addr_eip0, 0xc)
  assert int(dut.toCSR1_topeis_0.value) == wrap_topei(2)

  await write_csr_op(dut, csr_addr_eie0, 1 << 2, op_csrrc)
  assert int(dut.toCSR1_topeis_0.value) != wrap_topei(2)
  await write_csr_op(dut, csr_addr_eie0, 1 << 2, op_csrrs)
  assert int(dut.toCSR1_topeis_0.value) == wrap_topei(2)

  await read_csr(dut, csr_addr_eie0)
  await FallingEdge(dut.clock)
  cocotb.log.info("m-mode CSR operations passed")
