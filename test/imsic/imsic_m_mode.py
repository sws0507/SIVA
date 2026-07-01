########################################################################################
# Copyright (c) 2024 Beijing Institute of Open Source Chip (BOSC)
#
# ChiselAIA is licensed under Mulan PSL v2.
########################################################################################

import cocotb
from cocotb.triggers import FallingEdge
from imsic_common import *


@cocotb.test()
async def imsic_m_mode_interrupt_test(dut):
  """M-mode MSI delivery, claim, and priority behavior."""
  await setup_imsic(dut)

  cocotb.log.info("mseteipnum began")
  await m_int(dut, 1996 % 256)
  await FallingEdge(dut.clock)
  await delay_fifo(dut)
  assert int(dut.toCSR1_topeis_0.value) == wrap_topei(1996 % 256)
  cocotb.log.info("mseteipnum passed")

  cocotb.log.info("mclaim began")
  await claim(dut)
  assert int(dut.toCSR1_topeis_0.value) == wrap_topei(0)
  cocotb.log.info("mclaim passed")

  cocotb.log.info("2_mseteipnum_1_bits_mclaim began")
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
  cocotb.log.info("2_mseteipnum_1_bits_mclaim passed")
