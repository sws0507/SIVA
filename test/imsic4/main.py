import cocotb
from cocotb.triggers import FallingEdge
from imsic_split_common import *


@cocotb.test()
async def imsic_smmtt_and_ifp_test(dut):
  await start_imsic_test(dut)

  await enable_s_file(dut, 0, 64)
  await s_int_domain(dut, 64, domain=0)
  await wait_for_msi(dut)

  await enable_vs_file(dut, 0, 2, 65)
  await v_int_vgein(dut, 65, domain=0)
  await wait_for_msi(dut)

  cocotb.log.info("smmtt two-domain routing began")
  await enable_s_file(dut, 1, 77)
  await set_sdicn(dut, 2)
  await select_s_intfile(dut)
  assert int(dut.toCSR1_topeis_1.value) == wrap_topei(0)
  await s_int_domain(dut, 77, domain=1)
  await wait_for_msi(dut)
  assert int(dut.toCSR1_topeis_1.value) == wrap_topei(77)

  await enable_vs_file(dut, 1, 2, 138)
  await select_vs_intfile(dut, 2)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(0)
  await v_int_vgein(dut, 138, domain=1)
  await wait_for_msi(dut)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(138)

  await set_sdicn(dut, 1)
  await select_s_intfile(dut)
  assert int(dut.toCSR1_topeis_1.value) == wrap_topei(64)
  await select_vs_intfile(dut, 2)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(65)

  assert int(dut.toCSR1_msdeip.value) & 0b110 == 0b110
  await set_msdeie(dut, 1 << 2)
  await FallingEdge(dut.clock)
  assert int(dut.toCSR1_lsdeip.value) == 1
  await set_msdeie(dut, 0)
  await FallingEdge(dut.clock)
  assert int(dut.toCSR1_lsdeip.value) == 0
  cocotb.log.info("smmtt two-domain routing passed")

  cocotb.log.info("interrupt-file pooling began")
  await enable_vs_file(dut, 1, 3, 139)
  await v_int_vgein(dut, 139, guestID=3, domain=1)
  await wait_for_msi(dut)

  await set_smmtt_enable(dut, 0)
  await set_sdicn(dut, 0)
  await select_s_intfile(dut)
  assert int(dut.toCSR1_topeis_1.value) == wrap_topei(64)

  await select_vs_intfile(dut, imsic_geilen + 1)
  await FallingEdge(dut.clock)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(77)

  await select_vs_intfile(dut, imsic_geilen + 1 + 3)
  await FallingEdge(dut.clock)
  assert int(dut.toCSR1_topeis_2.value) == wrap_topei(139)

  assert int(dut.toCSR1_msdeip.value) == 0
  await set_msdeie(dut, 0b110)
  await FallingEdge(dut.clock)
  assert int(dut.toCSR1_lsdeip.value) == 0
  cocotb.log.info("interrupt-file pooling passed")
