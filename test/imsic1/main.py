import cocotb
from imsic_split_common import *


@cocotb.test()
async def imsic_m_file_basic_test(dut):
  await start_imsic_test(dut)
  await enable_m_file(dut, 1996 % 256, 12, 8)
  await select_m_intfile(dut)

  cocotb.log.info("m-mode seteipnum and claim began")
  await m_int(dut, 1996 % 256)
  await wait_for_msi(dut)
  assert int(dut.toCSR1_topeis_0.value) == wrap_topei(1996 % 256)

  await claim(dut)
  assert int(dut.toCSR1_topeis_0.value) == wrap_topei(0)

  await m_int(dut, 12)
  await wait_for_msi(dut)
  assert int(dut.toCSR1_topeis_0.value) == wrap_topei(12)

  await m_int(dut, 8)
  await wait_for_msi(dut)
  assert int(dut.toCSR1_topeis_0.value) == wrap_topei(8)

  await claim(dut)
  assert int(dut.toCSR1_topeis_0.value) == wrap_topei(12)
  cocotb.log.info("m-mode seteipnum and claim passed")
