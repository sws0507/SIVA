########################################################################################
# Copyright (c) 2024 Beijing Institute of Open Source Chip (BOSC)
#
# ChiselAIA is licensed under Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#          http://license.coscl.org.cn/MulanPSL2
#
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
# EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
# MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
#
# See the Mulan PSL v2 for more details.
########################################################################################

from cocotb.triggers import RisingEdge, FallingEdge

## delay about async fifo for imsic,EnableImsicAsyncBridge indicate the delay caused by imsic is async
EnableImsicAsyncBridge = 0
async def delay_fifo(dut):
    if EnableImsicAsyncBridge ==1 :
        for _ in range(5):
            await FallingEdge(dut.clock) ## delay caused by async fifo: source and sink, when EnableImsicAsyncBridge is true
    else:
        for _ in range(10):
            await FallingEdge(dut.clock) ## delay caused by async fifo: source and sink, when EnableImsicAsyncBridge is true
        """EnableImsicAsyncbridge is 0."""
  
## delay about async fifo for imsic

op_put_full = 0
op_get = 4
op_access_ack = 0
op_access_ack_data = 1
async def a_op(dut, addr, data, op, mask, size) -> None:
  await FallingEdge(dut.clock)
  while int(dut.toaia_0_a_ready.value) == 0:
    await FallingEdge(dut.clock)
  dut.toaia_0_a_valid.value = 1
  dut.toaia_0_a_bits_opcode.value = op
  dut.toaia_0_a_bits_address.value = addr
  dut.toaia_0_a_bits_mask.value = mask
  dut.toaia_0_a_bits_size.value = size
  dut.toaia_0_a_bits_data.value = data
  await FallingEdge(dut.clock)
  dut.toaia_0_a_valid.value = 0
async def a_op32(dut, addr, data, op) -> None:
  await a_op(
    dut, addr,
    data if addr%4==0 else data<<32,
    op,
    0x0f if addr%4==0 else 0xf,
    2,
  )
async def a_put_full32(dut, addr, data) -> None:
  await a_op32(dut, addr, data, op_put_full)
  for _ in range(10):
    await RisingEdge(dut.clock)
    if int(dut.toaia_0_d_bits_opcode.value) == op_access_ack and int(dut.toaia_0_d_valid.value) == 1:
      break
  else:
    assert False, f"Timeout waiting for op_access_ack"
async def a_get32(dut, addr) -> int:
  await a_op32(dut, addr, 0, op_get)
  for _ in range(10):
    await RisingEdge(dut.clock)
    if int(dut.toaia_0_d_bits_opcode.value) == op_access_ack_data and int(dut.toaia_0_d_valid.value) == 1:
      break
  else:
    assert False, f"Timeout waiting for op_access_ack_data"
  odata = int(dut.toaia_0_d_bits_data.value)
  res = odata if addr%4==0 else odata>>32
  return res & 0xffffffff

async def interrupt(dut, i):
  intSrcs_x = getattr(dut, f"intSrcs_{i}")
  await FallingEdge(dut.clock)
  intSrcs_x.value = 0
  await FallingEdge(dut.clock)
  intSrcs_x.value = 1
  if EnableImsicAsyncBridge ==1 :
    for _ in range(15):
      await FallingEdge(dut.clock)
      if int(dut.toCSR0_topeis_0.value) == wrap_topei(i):
        break
    else:
      assert False, f"Timeout waiting for toCSR0_topeis_0 == wrap_topei({i})"
  else :
    for _ in range(10):
      await FallingEdge(dut.clock)
      await FallingEdge(dut.clock)
      if int(dut.toCSR0_topeis_0.value) == wrap_topei(i):
        break
    else:
      assert False, f"Timeout waiting for toCSR0_topeis_0 == wrap_topei({i})"

################################################################################
# IMSIC
################################################################################
imsic_m_base_addr   = 0x61000000
imsic_sg_base_addr  = 0x82900000
imsic_groups_num    = 2
imsic_members_num   = 2
imsic_geilen        = 7
imsic_imsic_num     = 2
imsic_int_file_size = 0x1000
imsic_m_stride      = imsic_int_file_size
imsic_sg_files_per_domain = 1 + imsic_geilen
imsic_sg_files_per_imsic = imsic_sg_files_per_domain
imsic_pooled_geilen = imsic_imsic_num * imsic_geilen
imsic_sg_hart_stride = imsic_sg_files_per_domain * imsic_int_file_size
imsic_sg_domain_stride = imsic_members_num * imsic_sg_hart_stride
imsic_group_stride  = max(
  imsic_members_num * imsic_m_stride,
  imsic_imsic_num * imsic_sg_domain_stride,
)
csr_addr_eidelivery = 0x70
csr_addr_eithreshold = 0x72
csr_addr_eip0 = 0x80
csr_addr_eip2 = 0x82
csr_addr_eie0 = 0xC0
csr_addr_vs_domain_bitmap = 0x78
imsic_dynamic_tag_offset = 0x800
# CSR operation codes
op_illegal = 0
op_csrrw = 1
op_csrrs = 2
op_csrrc = 3

def imsic_group_member(imsicID):
  return imsicID // imsic_members_num, imsicID % imsic_members_num

def imsic_m_file_addr(imsicID=1):
  group, member = imsic_group_member(imsicID)
  return imsic_m_base_addr + imsic_group_stride * group + imsic_m_stride * member

def imsic_sg_file_addr(imsicID=1, domain=0, guestID=0):
  group, member = imsic_group_member(imsicID)
  return (
    imsic_sg_base_addr
    + imsic_group_stride * group
    + imsic_sg_domain_stride * domain
    + imsic_sg_hart_stride * member
    + imsic_int_file_size * guestID
  )

def imsic_pooled_vs_file_addr(imsicID=1, vgein=1):
  """Return the SG address slot reinterpreted as a pooled logical VS file."""
  assert 1 <= vgein <= imsic_pooled_geilen
  slot = vgein
  domain = slot // imsic_sg_files_per_domain
  guestID = slot % imsic_sg_files_per_domain
  return imsic_sg_file_addr(imsicID, domain, guestID)

async def m_int(dut, intnum, imsicID=1):
  """Issue an interrupt to the M-mode interrupt file."""
  await a_put_full32(dut, imsic_m_file_addr(imsicID), intnum)
  await RisingEdge(dut.clock)

async def s_int(dut, intnum, imsicID=1, domain=0):
  """Issue an interrupt to the S-mode interrupt file."""
  await a_put_full32(dut, imsic_sg_file_addr(imsicID, domain, 0), intnum)
  await RisingEdge(dut.clock)

async def s_int_sec(dut, intnum, imsicID=1, domain=0):
  """Issue an interrupt to the confidential S-mode interrupt file."""
  await a_put_full32(dut, imsic_sg_file_addr(imsicID, domain, 0) + imsic_dynamic_tag_offset, intnum)
  await RisingEdge(dut.clock)

async def v_int_vgein(dut, intnum, imsicID=1, guestID=2, domain=0):
  """Issue an interrupt to the VS-mode interrupt file with vgein2."""
  await a_put_full32(dut, imsic_sg_file_addr(imsicID, domain, guestID), intnum)
  await RisingEdge(dut.clock)

async def v_int_vgein_sec(dut, intnum, imsicID=1, guestID=2, domain=0):
  """Issue an interrupt to a confidential VS-mode interrupt file."""
  await a_put_full32(dut, imsic_sg_file_addr(imsicID, domain, guestID) + imsic_dynamic_tag_offset, intnum)
  await RisingEdge(dut.clock)

async def pooled_vs_int_vgein(dut, intnum, imsicID=1, vgein=1):
  """Issue an interrupt to a pooled logical VS interrupt file."""
  await a_put_full32(dut, imsic_pooled_vs_file_addr(imsicID, vgein), intnum)
  await RisingEdge(dut.clock)

async def pooled_vs_int_vgein_sec(dut, intnum, imsicID=1, vgein=1):
  """Issue an interrupt to a confidential pooled logical VS interrupt file."""
  await a_put_full32(dut, imsic_pooled_vs_file_addr(imsicID, vgein) + imsic_dynamic_tag_offset, intnum)
  await RisingEdge(dut.clock)

async def claim(dut, imsicID=1):
  """Claim the highest pending interrupt."""
  fromCSRx_claims_0 = getattr(dut, f"fromCSR{imsicID}_claims_0")
  await FallingEdge(dut.clock)
  fromCSRx_claims_0.value = 1
  await FallingEdge(dut.clock)
  fromCSRx_claims_0.value = 0

def wrap_topei(in_):
  extract = in_ & 0x7ff
  out = extract | (extract << 16)
  return out

async def write_csr_op(dut, miselect, data, op, imsicID=1):
  fromCSRx_addr_valid      = getattr(dut, f"fromCSR{imsicID}_addr_valid"     )
  fromCSRx_addr_bits       = getattr(dut, f"fromCSR{imsicID}_addr_bits_addr"      )
  fromCSRx_wdata_valid     = getattr(dut, f"fromCSR{imsicID}_wdata_valid"    )
  fromCSRx_wdata_bits_op   = getattr(dut, f"fromCSR{imsicID}_wdata_bits_op"  )
  fromCSRx_wdata_bits_data = getattr(dut, f"fromCSR{imsicID}_wdata_bits_data")
  await FallingEdge(dut.clock)
  fromCSRx_addr_valid.value = 1
  fromCSRx_addr_bits.value = miselect
  fromCSRx_wdata_valid.value = 1
  fromCSRx_wdata_bits_op.value = op
  fromCSRx_wdata_bits_data.value = data
  await FallingEdge(dut.clock)
  fromCSRx_addr_valid.value = 0
  fromCSRx_wdata_valid.value = 0

async def write_csr(dut, miselect, data, imsicID=1):
  await write_csr_op(dut, miselect, data, op_csrrw, imsicID)

async def read_csr(dut, miselect, imsicID=1):
  fromCSRx_addr_valid = getattr(dut, f"fromCSR{imsicID}_addr_valid")
  fromCSRx_addr_bits  = getattr(dut, f"fromCSR{imsicID}_addr_bits_addr" )
  toCSRx_rdata_valid = getattr(dut, f"toCSR{imsicID}_rdata_valid")
  toCSRx_rdata_bits  = getattr(dut, f"toCSR{imsicID}_rdata_bits")
  await FallingEdge(dut.clock)
  fromCSRx_addr_valid.value = 1
  fromCSRx_addr_bits.value = miselect
  for _ in range(10):
    await FallingEdge(dut.clock)
    if int(toCSRx_rdata_valid.value) == 1:
      rdata = int(toCSRx_rdata_bits.value)
      fromCSRx_addr_valid.value = 0
      return rdata
  fromCSRx_addr_valid.value = 0
  assert False, "Timeout waiting for rdata_valid == 1"

async def select_m_intfile(dut, imsicID=1):
  fromCSRx_priv = getattr(dut, f"fromCSR{imsicID}_addr_bits_priv")
  fromCSRx_virt = getattr(dut, f"fromCSR{imsicID}_addr_bits_virt")
  await FallingEdge(dut.clock)
  fromCSRx_priv.value = 3
  fromCSRx_virt.value = 0

async def select_s_intfile(dut, imsicID=1):
  fromCSRx_priv = getattr(dut, f"fromCSR{imsicID}_addr_bits_priv")
  fromCSRx_virt = getattr(dut, f"fromCSR{imsicID}_addr_bits_virt")
  await FallingEdge(dut.clock)
  fromCSRx_priv.value = 1
  fromCSRx_virt.value = 0

async def select_vs_intfile(dut, vgein, imsicID=1):
  fromCSRx_priv = getattr(dut, f"fromCSR{imsicID}_addr_bits_priv")
  fromCSRx_vgein = getattr(dut, f"fromCSR{imsicID}_vgein")
  fromCSRx_virt = getattr(dut, f"fromCSR{imsicID}_addr_bits_virt")
  await FallingEdge(dut.clock)
  fromCSRx_priv.value = 1
  fromCSRx_vgein.value = vgein
  fromCSRx_virt.value = 1

async def set_sdicn(dut, sdicn, imsicID=1):
  fromSmmttx_sdicn = getattr(dut, f"fromSmmtt{imsicID}_sdicn")
  await FallingEdge(dut.clock)
  fromSmmttx_sdicn.value = sdicn

async def set_smmtt_enable(dut, enable, imsicID=1):
  fromSmmttx_smmttEnable = getattr(dut, f"fromSmmtt{imsicID}_smmttEnable")
  await FallingEdge(dut.clock)
  fromSmmttx_smmttEnable.value = enable

async def set_sec(dut, sec, imsicID=1):
  secx = getattr(dut, f"sec{imsicID}")
  await FallingEdge(dut.clock)
  secx.value = sec

async def set_msdeie(dut, msdeie, imsicID=1):
  fromSmmttx_msdeie = getattr(dut, f"fromSmmtt{imsicID}_msdeie")
  await FallingEdge(dut.clock)
  fromSmmttx_msdeie.value = msdeie

async def init_imsic(dut, imsicID=1):
  await set_sec(dut, 0, imsicID)
  await set_smmtt_enable(dut, 1, imsicID)
  await set_sdicn(dut, 0, imsicID)
  await set_msdeie(dut, 0, imsicID)
  await select_m_intfile(dut, imsicID)
  await write_csr(dut, csr_addr_eidelivery, 1, imsicID)
  for e in range(0,32):
    await write_csr(dut, csr_addr_eie0 + 2*e, -1, imsicID)
  for domain in range(0, imsic_imsic_num):
    await set_sdicn(dut, domain, imsicID)
    await select_s_intfile(dut, imsicID)
    await write_csr(dut, csr_addr_eidelivery, 1, imsicID)
    for e in range(0,32):
      await write_csr(dut, csr_addr_eie0 + 2*e, -1, imsicID)
    for i in range(1, imsic_geilen + 1):
      await select_vs_intfile(dut, i, imsicID)
      await write_csr(dut, csr_addr_eidelivery, 1, imsicID)
      for e in range(0,32):
        await write_csr(dut, csr_addr_eie0 + 2*e, -1, imsicID)
  await set_sdicn(dut, 0, imsicID)


################################################################################
# APLIC
################################################################################
aplic_m_base_addr   = 0x19960000
aplic_sg_base_addr  = aplic_m_base_addr + 0x4000
offset_domaincfg    = 0
offset_sourcecfg    = 0x0004
offset_readonly0    = 0x1000
offset_mmsiaddrcfg  = 0x1BC0
offset_mmsiaddrcfgh = 0x1BC4
offset_smsiaddrcfg  = 0x1BC8
offset_smsiaddrcfgh = 0x1BCC
offset_setips       = 0x1C00
offset_setipnum     = 0x1CDC
offset_in_clrips    = 0x1D00
offset_clripnum     = 0x1DDC
offset_seties       = 0x1E00
offset_setienum     = 0x1EDC
offset_clries       = 0x1F00
offset_clrienum     = 0x1FDC
offset_setipnum_le  = 0x2000
offset_setipnum_be  = 0x2004
offset_intsource_sec = 0x2800
offset_genmsi       = 0x3000
offset_targets      = 0x3004
sourcecfg_sm_inactive = 0
sourcecfg_sm_detached = 1
sourcecfg_sm_edge1    = 4
sourcecfg_sm_edge0    = 5
sourcecfg_sm_level1   = 6
sourcecfg_sm_level0   = 7
