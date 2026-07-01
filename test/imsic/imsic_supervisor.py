########################################################################################
# Copyright (c) 2024 Beijing Institute of Open Source Chip (BOSC)
#
# ChiselAIA is licensed under Mulan PSL v2.
########################################################################################

import cocotb
from cocotb.triggers import FallingEdge
from imsic_common import *


@cocotb.test()
async def imsic_supervisor_and_vs_test(dut):
  """Supervisor and virtual-supervisor interrupt file behavior."""
  await setup_imsic(dut)

  cocotb.log.info("simple_supervisor_level began")
  await select_s_intfile(dut)
  assert int(dut.toCSR1_topeis_1.value) == wrap_topei(0)
  await s_int(dut, 1234 % 256)
  await FallingEdge(dut.clock)
  await delay_fifo(dut)
  assert int(dut.toCSR1_topeis_1.value) == wrap_topei(1234 % 256)
  await select_m_intfile(dut)
  cocotb.log.info("simple_supervisor_level end")

  cocotb.log.info("simple_virtualized_supervisor_level:vgein2 began")
  await select_vs_intfile(dut, 2)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(0)
  await v_int_vgein(dut, 137)
  await FallingEdge(dut.clock)
  await delay_fifo(dut)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(137)
  await select_m_intfile(dut)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(137)
  cocotb.log.info("simple_virtualized_supervisor_level:vgein2 end")
