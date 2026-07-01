########################################################################################
# Copyright (c) 2024 Beijing Institute of Open Source Chip (BOSC)
#
# ChiselAIA is licensed under Mulan PSL v2.
########################################################################################

import cocotb
from cocotb.triggers import FallingEdge
from imsic_common import *


@cocotb.test()
async def imsic_csr_access_test(dut):
  """CSR write/read operations that affect delivery, threshold, EIP, and EIE."""
  await setup_imsic(dut)

  await m_int(dut, 19)
  await FallingEdge(dut.clock)
  await delay_fifo(dut)
  assert int(dut.toCSR1_topeis_0.value) == wrap_topei(19)

  cocotb.log.info("write_csr:op began")
  await write_csr_op(dut, csr_addr_eidelivery, 0xc0, op_csrrs)
  assert int(dut.toCSR1_illegal.value) == 0
  await write_csr_op(dut, csr_addr_eidelivery, 0xc0, op_csrrc)
  cocotb.log.info("write_csr:op passed")

  cocotb.log.info("write_csr:eidelivery began")
  await write_csr(dut, csr_addr_eidelivery, 0)
  await write_csr(dut, csr_addr_eidelivery, 1)
  cocotb.log.info("write_csr:eidelivery passed")

  cocotb.log.info("write_csr:meithreshold began")
  mtopei = int(dut.toCSR1_topeis_0.value)
  await write_csr(dut, csr_addr_eithreshold, mtopei & 0x7ff)
  assert int(dut.toCSR1_topeis_0.value) != wrap_topei(mtopei)
  await write_csr(dut, csr_addr_eithreshold, mtopei + 1)
  assert int(dut.toCSR1_topeis_0.value) == mtopei
  await write_csr(dut, csr_addr_eithreshold, 0)
  cocotb.log.info("write_csr:meithreshold end")

  cocotb.log.info("write_csr:eip began")
  await write_csr(dut, csr_addr_eip0, 0xc)
  assert int(dut.toCSR1_topeis_0.value) == wrap_topei(2)
  cocotb.log.info("write_csr:eip end")

  cocotb.log.info("write_csr:eie began")
  mtopei = int(dut.toCSR1_topeis_0.value)
  mask = 1 << (mtopei & 0x7ff)
  await write_csr_op(dut, csr_addr_eie0, mask, op_csrrc)
  assert int(dut.toCSR1_topeis_0.value) != mtopei
  await write_csr_op(dut, csr_addr_eie0, mask, op_csrrs)
  assert int(dut.toCSR1_topeis_0.value) == mtopei
  cocotb.log.info("write_csr:eie passed")

  cocotb.log.info("read_csr:eie began")
  await read_csr(dut, csr_addr_eie0)
  await FallingEdge(dut.clock)
  cocotb.log.info("read_csr:eie passed")
