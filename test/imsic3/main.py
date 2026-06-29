import cocotb
from imsic_split_common import *


@cocotb.test()
async def imsic_supervisor_and_vs_test(dut):
  await start_imsic_test(dut)

  cocotb.log.info("supervisor interrupt file began")
  await enable_s_file(dut, 0, 1234 % 256)
  await select_s_intfile(dut)
  assert int(dut.toCSR1_topeis_1.value) == wrap_topei(0)
  await s_int(dut, 1234 % 256)
  await wait_for_msi(dut)
  assert int(dut.toCSR1_topeis_1.value) == wrap_topei(1234 % 256)
  cocotb.log.info("supervisor interrupt file passed")

  cocotb.log.info("virtual supervisor interrupt file began")
  await enable_vs_file(dut, 0, 2, 137)
  await select_vs_intfile(dut, 2)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(0)
  await v_int_vgein(dut, 137)
  await wait_for_msi(dut)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(137)
  await select_m_intfile(dut)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(137)
  cocotb.log.info("virtual supervisor interrupt file passed")
