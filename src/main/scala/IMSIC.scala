package aia

import chisel3._
import chisel3.IO
import chisel3.util._
import freechips.rocketchip.amba.axi4._
import freechips.rocketchip.amba.axi4.AXI4Xbar
import freechips.rocketchip.devices.tilelink._
import freechips.rocketchip.diplomacy._
import freechips.rocketchip.prci.ClockSinkDomain
import freechips.rocketchip.regmapper._
import freechips.rocketchip.tilelink._
import freechips.rocketchip.util._
import org.chipsalliance.cde.config.Parameters
import utility._

object RegMapDV {
  def Unwritable = null
  def apply(addr: Int, reg: UInt, wfn: UInt => UInt = (x => x)) = (addr, (reg, wfn))
  def generate(
      default: UInt,
      mapping: Map[Int, (UInt, UInt => UInt)],
      raddr:   UInt,
      rvld:    Bool,
      rdata:   UInt,
      rvalid:  Bool,
      waddr:   UInt,
      wen:     Bool,
      wdata:   UInt,
      wmask:   UInt,
      illegal_priv: Bool,
      illegal_op:   Bool
  ): Unit = {
    val chiselMapping = mapping.map { case (a, (r, w)) => (a.U, r, w) }
    when(rvld) {
      rdata := LookupTreeDefault(
        raddr,
        Cat(default),
        chiselMapping.map { case (a, r, _) => (a, r) }
      )
      rvalid := true.B
    }.otherwise {
      rdata  := 0.U((rdata.getWidth).W)
      rvalid := illegal_priv | illegal_op
    }

    chiselMapping.foreach { case (a, r, w) =>
      if (w != null) {
        when(wen && waddr === a && !illegal_priv && !illegal_op) {
          r := w(MaskData(r, wdata, wmask))
        }
      }
    }
  }
  def generate(
      default: UInt,
      mapping: Map[Int, (UInt, UInt => UInt)],
      addr:    UInt,
      rvld:    Bool,
      rdata:   UInt,
      rvalid:  Bool,
      wen:     Bool,
      wdata:   UInt,
      wmask:   UInt,
      illegal_priv: Bool,
      illegal_wdata_op:   Bool
  ): Unit = generate(default, mapping, addr, rvld, rdata, rvalid, addr, wen, wdata, wmask, illegal_priv, illegal_wdata_op)
}

// Based on Xiangshan NewCSR
object OpType extends ChiselEnum {
  val ILLEGAL = Value(0.U)
  val CSRRW   = Value(1.U)
  val CSRRS   = Value(2.U)
  val CSRRC   = Value(3.U)
}
object PrivType extends ChiselEnum {
  val U = Value(0.U)
  val S = Value(1.U)
  val H = Value(2.U)
  val M = Value(3.U)
}
class MSITransBundle(params: IMSICParams) extends Bundle {
  val vld_req = Input(Bool()) // request from axireg
  val data = Input(UInt(params.MSI_INFO_WIDTH.W))
  val vld_ack = Output(Bool())  // ack for axireg from imsic. which indicates imsic can work actively.
}
class AddrBundle(params: IMSICParams) extends  Bundle {
  val valid = Bool()                      // 表示 addr 是否有效
  val bits  = new Bundle {
    val addr = UInt(params.iselectWidth.W) // 存储实际地址值
    val virt  = Bool()
    val priv  = PrivType()
  }
}
class CSRToIMSICBundle(params: IMSICParams) extends Bundle {
  val addr  = new AddrBundle(params)
  val vgein = UInt(params.vgeinWidth.W)
  val smmttEnable = Bool()
  val sdicn = UInt(params.sdicnWidth.W)
  val msdeie = UInt(params.msdeipWidth.W)
  val wdata = ValidIO(new Bundle {
    val op   = OpType()
    val data = UInt(params.xlen.W)
  })
  val claims = Vec(params.privNum, Bool())
}
class IMSICToCSRBundle(params: IMSICParams) extends Bundle {
  val rdata    = ValidIO(UInt(params.xlen.W))
  val illegal  = Bool()
  val pendings = UInt(params.intFilesNum.W)
  val topeis   = Vec(params.privNum, UInt(32.W))
  val msdeip   = UInt(params.msdeipWidth.W)
  val lsdeip   = Bool()
}
case class IMSICParams(
    // MC IMSIC中断源数量的对数，默认值8表示IMSIC支持最多512（2^9）个中断源

    // MC （Logarithm of number of interrupt sources to IMSIC.
    // MC The default 9 means IMSIC support at most 256 (2^9) interrupt sources）:
    // MC{visible}
    imsicIntSrcWidth: Int = 9,
    // MC 👉 本IMSIC的机器态中断文件的地址（Address of machine-level interrupt files for this IMSIC）：
    mAddr: Long = 0x00000L,
    // MC 👉 本IMSIC的监管态和客户态中断文件的地址（Addr for supervisor-level and guest-level interrupt files for this IMSIC）:
    sgAddr: Long = 0x10000L,
    // MC 👉 客户中断文件的数量（Number of guest interrupt files）:
    geilen: Int = 7,
    // MC vgein信号的位宽（The width of the vgein signal）:
    vgeinWidth: Int = 6,
    // MC iselect信号的位宽(The width of iselect signal):
    iselectWidth:           Int = 12,
    // Number of supervisor-domain interrupt-controller banks. A 2-domain
    // prototype maps SDICN 1 to bank 0 and SDICN 2 to bank 1.
    supervisorDomains:      Int = 2,
    EnableImsicAsyncBridge: Boolean = true
    // MC{hide}
) {
  lazy val xlen: Int = 64 // currently only support xlen = 64
  lazy val xlenWidth = log2Ceil(xlen)
  require(
    imsicIntSrcWidth <= 11 && imsicIntSrcWidth >= 6,
    f"imsicIntSrcWidth=${imsicIntSrcWidth}, must not greater than log2(2048)=11, as there are at most 2048 eip/eie bits" +
      "must not be less than log2(64)=6, as there must be at least 64 eip/eie bits"
  )
  require(supervisorDomains >= 1 && supervisorDomains <= 63)
  lazy val privNum:     Int = 3          // number of privilege modes: machine, supervisor, virtualized supervisor
  lazy val sgFilesPerDomain: Int = 1 + geilen // one S file plus VS guest files
  lazy val sgIntFilesNum: Int = supervisorDomains * sgFilesPerDomain
  lazy val intFilesNum: Int = 1 + sgIntFilesNum // m, then banked s/vs files

  lazy val eixNum: Int = pow2(imsicIntSrcWidth).toInt / xlen // number of eip/eie registers
  lazy val intFileMemWidth: Int = 12 // interrupt file memory region width: 12-bit width => 4KB size
  lazy val sgRegionWidth: Int = intFileMemWidth + log2Ceil(sgIntFilesNum)
  lazy val domainIndexWidth: Int = log2Ceil(supervisorDomains max 2)
  lazy val sdicnWidth: Int = 6
  lazy val msdeipWidth: Int = supervisorDomains + 1
  require(vgeinWidth >= log2Ceil(geilen))
  require(
    iselectWidth >= 8,
    f"iselectWidth=${iselectWidth} needs to be able to cover addr [0x70, 0xFF], that is from CSR eidelivery to CSR eie63"
  )
  lazy val INTP_FILE_WIDTH = log2Ceil(intFilesNum)
  lazy val MSI_INFO_WIDTH  = imsicIntSrcWidth + INTP_FILE_WIDTH
}

class IMSIC(
    params:    IMSICParams,
    beatBytes: Int = 4
)(implicit p: Parameters) extends Module {
  println(f"IMSICParams.geilen:            ${params.geilen}%d")

  class IMSICGateWay extends Module {
    // === io port define ===
    val msiio = IO(new MSITransBundle(params))
    val msi_data_o  = IO(Output(UInt(params.imsicIntSrcWidth.W)))
    val msi_valid_o = IO(Output(UInt(params.intFilesNum.W)))

    // === main body ===
    val msi_in = Wire(UInt(params.MSI_INFO_WIDTH.W))
    msi_in := msiio.data
    val msi_vld_req_cpu = WireInit(false.B)
    when(params.EnableImsicAsyncBridge.B) {
      msi_vld_req_cpu := AsyncResetSynchronizerShiftReg(msiio.vld_req, 3, 0)
    }.otherwise {
      msi_vld_req_cpu := msiio.vld_req
    }
    val msi_vld_ack_cpu = RegInit(false.B)
    when(msi_vld_req_cpu)(
      msi_vld_ack_cpu := true.B
    ).otherwise(
      msi_vld_ack_cpu := false.B
    )
    // generate the msi_vld_ack,to handle with the input msi request.
    msiio.vld_ack := msi_vld_ack_cpu
    val msi_vld_ris_cpu = msi_vld_req_cpu & (~msi_vld_ack_cpu) // rising of msi_vld_req
    val msi_data_catch  = RegInit(0.U(params.imsicIntSrcWidth.W))
    val msi_intf_valids = RegInit(0.U(params.intFilesNum.W))
    msi_data_o  := msi_data_catch(params.imsicIntSrcWidth - 1, 0)
    msi_valid_o := msi_intf_valids // multi-bis switch vector
    when(msi_vld_ris_cpu) {
      msi_data_catch := msi_in(params.imsicIntSrcWidth - 1, 0)
      msi_intf_valids := 1.U << msi_in(params.MSI_INFO_WIDTH - 1,params.imsicIntSrcWidth)
    }.otherwise {
      msi_intf_valids := 0.U
    }
  }
  class IntFile extends Module {
    override def desiredName = "IntFile"
    val fromCSR = IO(Input(new Bundle {
      val seteipnum = ValidIO(UInt(params.imsicIntSrcWidth.W))
      val addr      = ValidIO(UInt(params.iselectWidth.W))
      val virt      = Bool()
      val priv      = PrivType()
      val vgein     = UInt(params.vgeinWidth.W)
      val wdata = ValidIO(new Bundle {
        val op   = OpType()
        val data = UInt(params.xlen.W)
      })
      val claim = Bool()
    }))
    val toCSR = IO(Output(new Bundle {
      val rdata   = ValidIO(UInt(params.xlen.W))
      val illegal = Bool()
      val pending = Bool()
      val topei   = UInt(params.imsicIntSrcWidth.W)
    }))
    val illegal_io = IO(new Bundle {
      val illegal_priv = Input(Bool())
    })
    val illegal_priv = illegal_io.illegal_priv
  
    /// indirect CSRs
    val eidelivery  = RegInit(0.U(params.xlen.W))
    val eithreshold = RegInit(0.U(params.xlen.W))
    val eips        = RegInit(VecInit.fill(params.eixNum)(0.U(params.xlen.W)))
    val eies        = RegInit(VecInit.fill(params.eixNum)(0.U(params.xlen.W)))

    val illegal_wdata_op = WireDefault(false.B)
    locally { // scope for xiselect CSR reg map
      val wdata = WireDefault(0.U(params.xlen.W))
      val wmask = WireDefault(0.U(params.xlen.W))
      when(fromCSR.wdata.valid) {
        switch(fromCSR.wdata.bits.op) {
          // is(OpType.ILLEGAL) {
          //   illegal_wdata_op := true.B
          // }
          is(OpType.CSRRW) {
            wdata := fromCSR.wdata.bits.data
            wmask := Fill(params.xlen, 1.U)
          }
          is(OpType.CSRRS) {
            wdata := Fill(params.xlen, 1.U)
            wmask := fromCSR.wdata.bits.data
          }
          is(OpType.CSRRC) {
            wdata := 0.U
            wmask := fromCSR.wdata.bits.data
          }
        }
      }
      def bit0ReadOnlyZero(x: UInt): UInt = x & ~1.U(x.getWidth.W)
      def fixEIDelivery(x: UInt): UInt = x & 1.U
      RegMapDV.generate(
        0.U,
        Map(
          RegMapDV(0x70, eidelivery, fixEIDelivery),
          RegMapDV(0x72, eithreshold),
          RegMapDV(0x80, eips(0), bit0ReadOnlyZero),
          RegMapDV(0xc0, eies(0), bit0ReadOnlyZero)
        ) ++ eips.drop(1).zipWithIndex.map { case (eip: UInt, i: Int) =>
          RegMapDV(0x82 + i * 2, eip)
        } ++ eies.drop(1).zipWithIndex.map { case (eie: UInt, i: Int) =>
          RegMapDV(0xc2 + i * 2, eie)
        },
        /*raddr*/  fromCSR.addr.bits,
        /*rvld */  fromCSR.addr.valid,
        /*rdata*/  toCSR.rdata.bits,
        /*rvalid*/ toCSR.rdata.valid,
        /*waddr*/  fromCSR.addr.bits,
        /*wen  */  fromCSR.wdata.valid,
        /*wdata*/  wdata,
        /*wmask*/  wmask,
        /*priv*/   illegal_priv,
        /*op*/     illegal_wdata_op
      )
      val illegal_csr = WireDefault(false.B)
      when(fromCSR.addr.bits >= 0x80.U && fromCSR.addr.bits <= 0xFF.U &&
        fromCSR.addr.bits(0) === 1.U) {
          illegal_csr := true.B
      }
      toCSR.illegal := illegal_csr
    }
    locally {
      val index  = fromCSR.seteipnum.bits(params.imsicIntSrcWidth - 1, params.xlenWidth)
      val offset = fromCSR.seteipnum.bits(params.xlenWidth - 1, 0)
      when(fromCSR.seteipnum.valid) {
        // set eips bit
        eips(index) := eips(index) | UIntToOH(offset)
      }
    }

    locally { // scope for xtopei
      // The ":+ true.B" trick explain:
      //  Append true.B to handle the cornor case, where all bits in eip and eie are disabled.
      //  If do not append true.B, then we need to check whether the eip & eie are empty,
      //  otherwise, the returned topei will become the max index, that is 2^intSrcWidth-1
      // Noted: the support max interrupt sources number = 2^intSrcWidth
      //              [0,     2^intSrcWidth-1] :+ 2^intSrcWidth
      val eipBools = Cat(eips.reverse).asBools :+ true.B
      val eieBools = Cat(eies.reverse).asBools :+ true.B
      
      def xtopei_filter(xeidelivery: UInt, xeithreshold: UInt, xtopei: UInt): UInt = {
        val tmp_xtopei = Mux(xeidelivery(params.xlen - 1, 1) === 0.U, Mux(xeidelivery(0), xtopei, 0.U) , 0.U)
        // {
        //   all interrupts are enabled, when eithreshold == 1;
        //   interrupts, when i < eithreshold, are enabled;
        // } <=> interrupts, when i <= (eithreshold -1), are enabled
        Mux(tmp_xtopei <= (xeithreshold - 1.U), tmp_xtopei, 0.U)
      }
      toCSR.topei := xtopei_filter(
        eidelivery,
        eithreshold,
        ParallelPriorityMux(
          (eipBools zip eieBools).zipWithIndex.map {
            case ((p: Bool, e: Bool), i: Int) => (p & e, i.U)
          }
        )
      )
    } // end of scope for xtopei
    toCSR.pending := toCSR.topei =/= 0.U

    when(fromCSR.claim) {
      val index  = toCSR.topei(params.imsicIntSrcWidth - 1, params.xlenWidth)
      val offset = toCSR.topei(params.xlenWidth - 1, 0)
      // clear the pending bit indexed by xtopei in xeip
      eips(index) := eips(index) & ~UIntToOH(offset)
    }
  }
  val toCSR   = IO(Output(new IMSICToCSRBundle(params)))
  val fromCSR = IO(Input(new CSRToIMSICBundle(params)))
  val msiio   = IO(new MSITransBundle(params))
  val illegal_priv = WireInit(false.B)

  private val sdicnValid =
    fromCSR.sdicn >= 1.U && fromCSR.sdicn <= params.supervisorDomains.U(params.sdicnWidth.W)
  private val activeDomain =
    (fromCSR.sdicn - 1.U)(params.domainIndexWidth - 1, 0)
  private val vgeinValid =
    fromCSR.vgein >= 1.U && fromCSR.vgein <= params.geilen.U(params.vgeinWidth.W)
  private def sFileIndex(domain: UInt): UInt =
    (1.U + domain.pad(params.INTP_FILE_WIDTH) * params.sgFilesPerDomain.U)(params.INTP_FILE_WIDTH - 1, 0)
  private def vsFileIndex(domain: UInt, vgein: UInt): UInt =
    (sFileIndex(domain) + vgein.pad(params.INTP_FILE_WIDTH))(params.INTP_FILE_WIDTH - 1, 0)

  private val intFilesSelOH_r = WireDefault(0.U(params.intFilesNum.W))
  private val intFilesSelOH_w = WireDefault(0.U(params.intFilesNum.W))
  locally {
    val pv = Cat(fromCSR.addr.bits.priv.asUInt, fromCSR.addr.bits.virt)
    val mAccess  = pv === Cat(PrivType.M.asUInt, false.B)
    val sAccess  = pv === Cat(PrivType.S.asUInt, false.B)
    val vsAccess = pv === Cat(PrivType.S.asUInt, true.B)
    val selectedFile = WireDefault(0.U(params.INTP_FILE_WIDTH.W))

    when(mAccess) {
      selectedFile := 0.U
    }.elsewhen(sAccess) {
      selectedFile := sFileIndex(activeDomain)
    }.elsewhen(vsAccess) {
      selectedFile := vsFileIndex(activeDomain, fromCSR.vgein)
    }

    when(fromCSR.addr.valid) {
      when(mAccess) {
        illegal_priv := false.B
      }.elsewhen(sAccess) {
        illegal_priv := !sdicnValid
      }.elsewhen(vsAccess) {
        illegal_priv := !sdicnValid || !vgeinValid
      }.otherwise {
        illegal_priv := true.B
      }
    }
    when (fromCSR.addr.valid && !illegal_priv) // read
    {
      intFilesSelOH_r := UIntToOH(selectedFile, params.intFilesNum)
    }
    when (fromCSR.addr.valid && fromCSR.wdata.valid && !(fromCSR.wdata.bits.op.asUInt === 0.U) && !illegal_priv) // write
    {
      intFilesSelOH_w := UIntToOH(selectedFile, params.intFilesNum)
    }
  }

  private val topeis_forEachIntFiles   = Wire(Vec(params.intFilesNum, UInt(params.imsicIntSrcWidth.W)))
  private val illegals_forEachIntFiles = Wire(Vec(params.intFilesNum, Bool()))
  // instance and connect IMSICGateWay.
  val imsicGateWay = Module(new IMSICGateWay)
  imsicGateWay.msiio <> msiio
  val pendings = Wire(Vec(params.intFilesNum,Bool()))
  val vec_rdata = Wire(Vec(params.intFilesNum, ValidIO(UInt(params.xlen.W))))
  Seq(1, params.sgIntFilesNum).zipWithIndex.map {
    case (intFilesNum: Int, i: Int) => {
      // j: index for S intFile: S, G1, G2, ...
      val maps = (0 until intFilesNum).map { j =>
        val flati = i + j
        val sgOffset = if (flati == 0) 0 else (flati - 1) % params.sgFilesPerDomain

        def sel_addr(old: AddrBundle): AddrBundle = {
          val new_ = Wire(new AddrBundle(params))
          new_.valid := old.valid & intFilesSelOH_r(flati)
          new_.bits.addr := old.bits.addr
          new_.bits.virt := old.bits.virt
          new_.bits.priv := old.bits.priv
          new_
        }
        def sel_wdata[T <: Data](old: Valid[T]): Valid[T] = {
          val new_ = Wire(Valid(chiselTypeOf(old.bits)))
          new_.bits  := old.bits
          new_.valid := old.valid & intFilesSelOH_w(flati)
          new_
        }

        val intFile = Module(new IntFile)
        // Preventing overflow
        when(sgOffset.U((params.vgeinWidth + 1).W) === fromCSR.vgein.pad(params.vgeinWidth + 1)) {
          intFile.fromCSR.vgein := fromCSR.vgein
        } .otherwise {
          intFile.fromCSR.vgein := 0.U
        }
        val intfile_rdata_d = RegNext(intFile.toCSR.rdata)
        val msi_valid_delayed = RegNext(imsicGateWay.msi_valid_o(flati), false.B)
        intFile.fromCSR.seteipnum.bits  := imsicGateWay.msi_data_o
        intFile.fromCSR.seteipnum.valid := imsicGateWay.msi_valid_o(flati) | msi_valid_delayed
        intFile.fromCSR.addr.valid      := sel_addr(fromCSR.addr).valid
        intFile.fromCSR.addr.bits       := sel_addr(fromCSR.addr).bits.addr
        intFile.fromCSR.virt            := sel_addr(fromCSR.addr).bits.virt
        intFile.fromCSR.priv            := sel_addr(fromCSR.addr).bits.priv
        intFile.fromCSR.wdata           := sel_wdata(fromCSR.wdata)
        val mClaim = if (flati == 0) fromCSR.claims(0) else false.B
        val sClaim = if (flati != 0 && sgOffset == 0) {
          sdicnValid && (flati.U === sFileIndex(activeDomain)) && fromCSR.claims(1)
        } else {
          false.B
        }
        val vsClaim = if (flati != 0 && sgOffset != 0) {
          sdicnValid && vgeinValid && (flati.U === vsFileIndex(activeDomain, fromCSR.vgein)) && fromCSR.claims(2)
        } else {
          false.B
        }
        intFile.fromCSR.claim           := mClaim || sClaim || vsClaim
        intFile.illegal_io.illegal_priv := illegal_priv
        vec_rdata(flati)                := intfile_rdata_d
        pendings(flati)                 := intFile.toCSR.pending
        topeis_forEachIntFiles(flati)   := intFile.toCSR.topei
        illegals_forEachIntFiles(flati) := intFile.toCSR.illegal
      }
    }
  }
  toCSR.rdata.valid   := vec_rdata.map(_.valid).reduce(_|_)
  toCSR.rdata.bits    := vec_rdata.map(_.bits).reduce(_|_)
  toCSR.pendings := (pendings.zipWithIndex.map{case (p,i) => p << i.U}).reduce(_ | _) //vector -> multi-bit
  locally {
    // Format of *topei:
    // * bits 26:16 Interrupt identity
    // * bits 10:0 Interrupt priority (same as identity)
    // * All other bit positions are zeros.
    // For detailed explainations of these memory region arguments,
    // please refer to the manual *The RISC-V Advanced Interrupt Architeture*: 3.9. Top external interrupt CSRs
    def wrap(topei: UInt): UInt = {
      val zeros = 0.U((16 - params.imsicIntSrcWidth).W)
      Cat(zeros, topei, zeros, topei)
    }
    toCSR.topeis(0) := wrap(topeis_forEachIntFiles(0)) // m
    toCSR.topeis(1) := wrap(Mux(
      sdicnValid,
      ParallelMux(UIntToOH(sFileIndex(activeDomain), params.intFilesNum).asBools.zip(topeis_forEachIntFiles)),
      0.U
    )) // s
    toCSR.topeis(2) := wrap(Mux(
      sdicnValid && vgeinValid,
      ParallelMux(UIntToOH(vsFileIndex(activeDomain, fromCSR.vgein), params.intFilesNum).asBools.zip(topeis_forEachIntFiles)),
      0.U
    )) // vs
  }  
  private val msdeipBits = Wire(Vec(params.msdeipWidth, Bool()))
  msdeipBits(0) := false.B
  for (domain <- 0 until params.supervisorDomains) {
    val base = 1 + domain * params.sgFilesPerDomain
    msdeipBits(domain + 1) := pendings.slice(base, base + params.sgFilesPerDomain).reduce(_ | _)
  }
  val msdeipValue = msdeipBits.asUInt
  toCSR.msdeip := msdeipValue
  toCSR.lsdeip := (msdeipValue & fromCSR.msdeie).orR
  val toCSR_illegal_d = RegNext((fromCSR.addr.valid | fromCSR.wdata.valid) & Seq(
    illegals_forEachIntFiles.reduce(_ | _),
    (fromCSR.wdata.valid && fromCSR.wdata.bits.op.asUInt === 0.U),
    illegal_priv
  ).reduce(_ | _))
  toCSR.illegal := toCSR_illegal_d
}

class IMSICMulti(
    params:    IMSICParams,
    beatBytes: Int = 4
)(implicit p: Parameters) extends Module {
  private val coreParams = params.copy(supervisorDomains = 1)

  val toCSR   = IO(Output(new IMSICToCSRBundle(params)))
  val fromCSR = IO(Input(new CSRToIMSICBundle(params)))
  val msiio   = IO(new MSITransBundle(params))

  private val smmttEnable = fromCSR.smmttEnable
  private val sdicnValid =
    fromCSR.sdicn >= 1.U && fromCSR.sdicn <= params.supervisorDomains.U(params.sdicnWidth.W)
  private val activeDomain =
    (fromCSR.sdicn - 1.U)(params.domainIndexWidth - 1, 0)
  private val activeDomainOH = UIntToOH(activeDomain, params.supervisorDomains) &
    Fill(params.supervisorDomains, sdicnValid)

  private val pv = Cat(fromCSR.addr.bits.priv.asUInt, fromCSR.addr.bits.virt)
  private val mAccess  = pv === Cat(PrivType.M.asUInt, false.B)
  private val sAccess  = pv === Cat(PrivType.S.asUInt, false.B)
  private val vsAccess = pv === Cat(PrivType.S.asUInt, true.B)
  private val svAccess = sAccess || vsAccess

  private def asExtFileIndex(value: UInt): UInt =
    value.pad(params.INTP_FILE_WIDTH)(params.INTP_FILE_WIDTH - 1, 0)
  private def asCoreVgein(value: UInt): UInt =
    value.pad(coreParams.vgeinWidth)(coreParams.vgeinWidth - 1, 0)
  private def decodePooledSgOffset(offset: UInt): (UInt, UInt) = {
    val domainOH = WireDefault(0.U(params.supervisorDomains.W))
    val localOffset = WireDefault(0.U(coreParams.INTP_FILE_WIDTH.W))
    for (domain <- 0 until params.supervisorDomains) {
      for (offsetInDomain <- 0 until params.sgFilesPerDomain) {
        val pooledOffset = domain * params.sgFilesPerDomain + offsetInDomain
        when(offset === pooledOffset.U(params.INTP_FILE_WIDTH.W)) {
          domainOH := (BigInt(1) << domain).U(params.supervisorDomains.W)
          localOffset := offsetInDomain.U(coreParams.INTP_FILE_WIDTH.W)
        }
      }
    }
    (domainOH, localOffset)
  }

  private val pooledVgeinValid = fromCSR.vgein >= 1.U && fromCSR.vgein < params.sgIntFilesNum.U
  private val pooledAccessSgOffset = WireDefault(0.U(params.INTP_FILE_WIDTH.W))
  when(vsAccess) {
    pooledAccessSgOffset := asExtFileIndex(fromCSR.vgein)
  }
  private val (pooledAccessDomainOH, pooledAccessLocalOffset) =
    decodePooledSgOffset(pooledAccessSgOffset)
  private val pooledAccessValid = sAccess || (vsAccess && pooledVgeinValid)
  private val (pooledVsDomainOH, pooledVsLocalOffset) =
    decodePooledSgOffset(asExtFileIndex(fromCSR.vgein))

  private val domainIMSICs = Seq.fill(params.supervisorDomains) {
    Module(new IMSIC(coreParams, beatBytes))
  }

  private val extFileIndex = msiio.data(params.MSI_INFO_WIDTH - 1, params.imsicIntSrcWidth)
  private val extIntId     = msiio.data(params.imsicIntSrcWidth - 1, 0)
  private val targetDomain = WireDefault(0.U(params.domainIndexWidth.W))
  private val targetFile   = WireDefault(0.U(coreParams.INTP_FILE_WIDTH.W))

  when(extFileIndex === 0.U) {
    targetDomain := 0.U
    targetFile   := 0.U
  }
  for (domain <- 0 until params.supervisorDomains) {
    for (offset <- 0 until params.sgFilesPerDomain) {
      val externalFile = 1 + domain * params.sgFilesPerDomain + offset
      val localFile = 1 + offset
      when(extFileIndex === externalFile.U(params.INTP_FILE_WIDTH.W)) {
        targetDomain := domain.U
        targetFile   := localFile.U(coreParams.INTP_FILE_WIDTH.W)
      }
    }
  }
  private val targetDomainOH = UIntToOH(targetDomain, params.supervisorDomains)
  private val coreMsiData = Cat(targetFile, extIntId)

  private val csrRouteOH = WireDefault(0.U(params.supervisorDomains.W))
  when(mAccess) {
    csrRouteOH := 1.U
  }.elsewhen(smmttEnable && svAccess && sdicnValid) {
    csrRouteOH := activeDomainOH
  }.elsewhen(!smmttEnable && svAccess && pooledAccessValid) {
    csrRouteOH := pooledAccessDomainOH
  }

  for ((imsic, domain) <- domainIMSICs.zipWithIndex) {
    val domainSelected = sdicnValid && activeDomain === domain.U
    val pooledSelected = !smmttEnable && pooledAccessValid && pooledAccessDomainOH(domain)
    val pooledLocalIsS = pooledAccessLocalOffset === 0.U
    val mRoute = if (domain == 0) mAccess else false.B
    val smmttRoute = smmttEnable && svAccess && domainSelected
    val pooledRoute = svAccess && pooledSelected
    val svRoute = smmttRoute || pooledRoute
    val csrRoute = mRoute || svRoute

    val coreFromCSR = WireDefault(0.U.asTypeOf(new CSRToIMSICBundle(coreParams)))
    coreFromCSR.addr.valid := fromCSR.addr.valid && csrRoute
    coreFromCSR.addr.bits.addr := fromCSR.addr.bits.addr
    coreFromCSR.addr.bits.virt := Mux(pooledRoute, !pooledLocalIsS, fromCSR.addr.bits.virt)
    coreFromCSR.addr.bits.priv := fromCSR.addr.bits.priv
    coreFromCSR.vgein := Mux(
      pooledRoute,
      Mux(pooledLocalIsS, 0.U(coreParams.vgeinWidth.W), asCoreVgein(pooledAccessLocalOffset)),
      fromCSR.vgein
    )
    coreFromCSR.smmttEnable := smmttEnable
    coreFromCSR.sdicn := 1.U
    coreFromCSR.msdeie := 0.U
    coreFromCSR.wdata.bits.op := fromCSR.wdata.bits.op
    coreFromCSR.wdata.bits.data := fromCSR.wdata.bits.data
    coreFromCSR.wdata.valid := fromCSR.wdata.valid && csrRoute
    coreFromCSR.claims(0) := (if (domain == 0) fromCSR.claims(0) else false.B)
    coreFromCSR.claims(1) := (smmttEnable && domainSelected && fromCSR.claims(1)) ||
      (pooledSelected && pooledLocalIsS && (
        (sAccess && fromCSR.claims(1)) || (vsAccess && fromCSR.claims(2))
      ))
    coreFromCSR.claims(2) := (smmttEnable && domainSelected && fromCSR.claims(2)) ||
      (pooledSelected && !pooledLocalIsS && vsAccess && fromCSR.claims(2))
    imsic.fromCSR := coreFromCSR

    imsic.msiio.vld_req := msiio.vld_req && targetDomainOH(domain)
    imsic.msiio.data := coreMsiData
  }

  msiio.vld_ack := Mux1H(targetDomainOH.asBools.zip(domainIMSICs.map(_.msiio.vld_ack)))

  private def muxRouted[T <: Data](values: Seq[T]): T = {
    Mux(csrRouteOH.orR, Mux1H(csrRouteOH.asBools.zip(values)), 0.U.asTypeOf(chiselTypeOf(values.head)))
  }
  private def muxActive[T <: Data](values: Seq[T]): T = {
    Mux(sdicnValid, Mux1H(activeDomainOH.asBools.zip(values)), 0.U.asTypeOf(chiselTypeOf(values.head)))
  }
  private def muxPooledVs[T <: Data](values: Seq[T]): T = {
    Mux(pooledVgeinValid, Mux1H(pooledVsDomainOH.asBools.zip(values)), 0.U.asTypeOf(chiselTypeOf(values.head)))
  }

  toCSR.rdata.valid := muxRouted(domainIMSICs.map(_.toCSR.rdata.valid))
  toCSR.rdata.bits  := muxRouted(domainIMSICs.map(_.toCSR.rdata.bits))

  private val pendingBits = Seq(domainIMSICs.head.toCSR.pendings(0)) ++ domainIMSICs.flatMap { imsic =>
    (1 until coreParams.intFilesNum).map(i => imsic.toCSR.pendings(i))
  }
  toCSR.pendings := Cat(pendingBits.reverse)

  toCSR.topeis(0) := domainIMSICs.head.toCSR.topeis(0)
  toCSR.topeis(1) := Mux(
    smmttEnable,
    muxActive(domainIMSICs.map(_.toCSR.topeis(1))),
    domainIMSICs.head.toCSR.topeis(1)
  )
  toCSR.topeis(2) := Mux(
    smmttEnable,
    muxActive(domainIMSICs.map(_.toCSR.topeis(2))),
    muxPooledVs(domainIMSICs.map(imsic =>
      Mux(pooledVsLocalOffset === 0.U, imsic.toCSR.topeis(1), imsic.toCSR.topeis(2))
    ))
  )

  private val msdeipBits = Wire(Vec(params.msdeipWidth, Bool()))
  msdeipBits.foreach(_ := false.B)
  for (domain <- 0 until params.supervisorDomains) {
    msdeipBits(domain + 1) := domainIMSICs(domain).toCSR.pendings(coreParams.intFilesNum - 1, 1).orR
  }
  private val msdeipValue = msdeipBits.asUInt
  toCSR.msdeip := Mux(smmttEnable, msdeipValue, 0.U(params.msdeipWidth.W))
  toCSR.lsdeip := smmttEnable && (msdeipValue & fromCSR.msdeie).orR

  private val invalidPrivAccess =
    (fromCSR.addr.valid || fromCSR.wdata.valid) && !mAccess && !svAccess
  private val invalidSdicnAccess =
    (fromCSR.addr.valid || fromCSR.wdata.valid) && smmttEnable && svAccess && !sdicnValid
  private val invalidPooledVgeinAccess =
    (fromCSR.addr.valid || fromCSR.wdata.valid) && !smmttEnable && vsAccess && !pooledVgeinValid
  private val wrapperIllegal = RegNext(
    invalidPrivAccess || invalidSdicnAccess || invalidPooledVgeinAccess,
    false.B
  )
  toCSR.illegal := muxRouted(domainIMSICs.map(_.toCSR.illegal)) || wrapperIllegal
}

//generate TLIMSIC top module:including TLRegIMSIC_WRAP and IMSIC
class TLIMSIC(
    params:    IMSICParams,
    beatBytes: Int = 4
//  asyncQueueParams: AsyncQueueParams
)(implicit p: Parameters) extends LazyModule {
  val axireg      = LazyModule(new TLRegIMSIC_WRAP(params, beatBytes))
  lazy val module = new Imp

  class Imp extends LazyModuleImp(this) {
    val toCSR         = IO(Output(new IMSICToCSRBundle(params)))
    val fromCSR       = IO(Input(new CSRToIMSICBundle(params)))
    private val imsic = Module(new IMSICMulti(params, beatBytes))
    toCSR := imsic.toCSR
    imsic.fromCSR := fromCSR
    axireg.module.msiio <> imsic.msiio // msi_req/msi_ack interconnect
    /* code on when imsic has two clock domains.*/
    // --- define soc_clock for imsic bus logic ***//
    val soc_clock = IO(Input(Clock()))
    val soc_reset = IO(Input(Reset()))
    axireg.module.clock := soc_clock
    axireg.module.reset := soc_reset
    imsic.clock         := clock
    imsic.reset         := reset
  }
}

class AXI4IMSIC(
    params:    IMSICParams,
    beatBytes: Int = 4
)(implicit p: Parameters) extends LazyModule {
  val axireg      = LazyModule(new AXIRegIMSIC_WRAP(params, beatBytes))
  lazy val module = new Imp
  class Imp extends LazyModuleImp(this) {
    val toCSR         = IO(Output(new IMSICToCSRBundle(params)))
    val fromCSR       = IO(Input(new CSRToIMSICBundle(params)))
    private val imsic = Module(new IMSICMulti(params, beatBytes))
    toCSR := imsic.toCSR
    imsic.fromCSR := fromCSR
    axireg.module.msiio <> imsic.msiio // msi_req/msi_ack interconnect
    /* code on when imsic has two clock domains.*/
    // --- define soc_clock for imsic bus logic ***//
    val soc_clock = IO(Input(Clock()))
    val soc_reset = IO(Input(Reset()))
    axireg.module.clock := soc_clock
    axireg.module.reset := soc_reset
    imsic.clock         := clock
    imsic.reset         := reset
  }
}

class TLRegIMSIC_WRAP(
    params:    IMSICParams,
    beatBytes: Int = 4,
    seperateBus: Boolean = false
)(implicit p: Parameters) extends LazyModule {
  require(seperateBus == false,
    f"seperateTLBus is true inside TLRegIMSIC_WRAP !!")
  val axireg = LazyModule(new TLRegIMSIC(params, beatBytes)(Parameters.empty))
  val imsic_xbar1to2 = TLXbar()
  private val sNode = TLManagerNode(Seq(TLSlavePortParameters.v1(
      managers = Seq(TLSlaveParameters.v1(
        address = Seq(
          AddressSet(params.mAddr, pow2(params.intFileMemWidth) - 1),
          AddressSet(params.sgAddr, pow2(params.sgRegionWidth) - 1)),
        regionType = RegionType.UNCACHED,
        executable = false,
        supportsGet = TransferSizes(1, beatBytes),
        supportsPutPartial = TransferSizes(1, beatBytes),
        supportsPutFull = TransferSizes(1, beatBytes),
        //          fifoId = Some(0)
      )),
      beatBytes = beatBytes
    )))

  sNode := imsic_xbar1to2
  val mNode = TLClientNode(
    Seq(TLMasterPortParameters.v1(
      Seq(TLMasterParameters.v1("s_tl_", IdRange(0, 65536)))
    )))
  axireg.fromMem.head := mNode
  lazy val module = new TLRegIMSICImp(this)
  class TLRegIMSICImp(outer: LazyModule) extends LazyModuleImp(outer) {
    val msiio = IO(Flipped(new MSITransBundle(params)))
    msiio <> axireg.module.msiio

    mNode.out.head._1 <> sNode.in.head._1
  }
}

class AXIRegIMSIC_WRAP(
    params:    IMSICParams,
    beatBytes: Int = 4,
    seperateBus: Boolean = false
)(implicit p: Parameters) extends LazyModule {
  val imsic_xbar1to2 = AXI4Xbar()
  val sNode = {
    AXI4SlaveNode(Seq(AXI4SlavePortParameters(
      slaves = Seq(AXI4SlaveParameters(
        address = Seq(
        AddressSet(params.mAddr, pow2(params.intFileMemWidth) - 1),
        AddressSet(params.sgAddr, pow2(params.sgRegionWidth) - 1)),
        supportsWrite = TransferSizes(1, beatBytes),
        supportsRead = TransferSizes(1, beatBytes),
        interleavedId = Some(0)
      )),
      beatBytes = beatBytes
    )))
  }
  sNode := imsic_xbar1to2
  val axireg = LazyModule(new AXIRegIMSIC(params, beatBytes)(Parameters.empty))
  val mNode = AXI4MasterNode(Seq(AXI4MasterPortParameters(
    Seq(AXI4MasterParameters(
      name = "s_axi_",
      id = IdRange(0, 65536)
    ))
  )))
  axireg.axi4tolite.head.node := mNode
  lazy val module = new AXIRegIMSICImp(this)

  class AXIRegIMSICImp(outer: LazyModule) extends LazyModuleImp(outer) {
    val msiio = IO(Flipped(new MSITransBundle(params))) // backpressure signal for axi4bus, from imsic working on cpu clock
    msiio <> axireg.module.msiio
    mNode.out.head._1 <> sNode.in.head._1
  }
}

class TLRegIMSIC(
    params:      IMSICParams,
    beatBytes:   Int = 4,
    seperateBus: Boolean = false
)(implicit p: Parameters) extends LazyModule {
  val fromMem = Seq.fill(if (seperateBus) 2 else 1)(TLXbar())
  // val fromMem = LazyModule(new TLXbar).node
  private val intfileFromMems = Seq(
    AddressSet(params.mAddr, pow2(params.intFileMemWidth) - 1),
    AddressSet(params.sgAddr, pow2(params.sgRegionWidth) - 1)
  ).zipWithIndex.map { case (addrset, i) =>
    val intfileFromMem = TLRegMapperNode(
      address = Seq(addrset),
      beatBytes = beatBytes
    )
    intfileFromMem := (if (seperateBus) fromMem(i) else fromMem.head)
    intfileFromMem
  }

  lazy val module = new TLRegIMSICImp(this)
  class TLRegIMSICImp(outer: LazyModule) extends LazyModuleImp(outer) {
    val msiio = IO(Flipped(new MSITransBundle(params)))  // backpressure signal for axi4bus, from imsic working on cpu clock
    private val reggen = Module(new RegGen(params, beatBytes))
    // ---- instance sync fifo ----//
    // --- fifo wdata: {vector_valid,setipnum}, fifo wren: |vector_valid---//
    val FifoDataWidth = params.MSI_INFO_WIDTH
    val fifo_wdata    = Wire(Valid(UInt(FifoDataWidth.W)))

    // depth:8, data width: FifoDataWidth
    private val fifo_sync = Module(new Queue(UInt(FifoDataWidth.W), 8))
    // define about fifo write
    fifo_wdata.bits        := reggen.io.seteipnum
    fifo_wdata.valid       := reggen.io.valid
    fifo_sync.io.enq.valid := fifo_wdata.valid
    fifo_sync.io.enq.bits  := fifo_wdata.bits
    // fifo rd,controlled by msi_vld_ack from imsic working on csr clock.
    // msi_vld_ack_soc: sync result with soc clock
    val msi_vld_ack_soc = WireInit(false.B)
    val msi_vld_ack_cpu = msiio.vld_ack
    val msi_vld_req     = RegInit(false.B)
    when(params.EnableImsicAsyncBridge.B) {
      msi_vld_ack_soc := AsyncResetSynchronizerShiftReg(msi_vld_ack_cpu, 3, 0)
    }.otherwise {
      msi_vld_ack_soc := msi_vld_ack_cpu
    }
    fifo_sync.io.deq.ready := ~msi_vld_req
    // generate the msi_vld_req: high if ~empty,low when msi_vld_ack_soc
    msiio.vld_req := msi_vld_req
    val msi_vld_ack_soc_1f  = RegNext(msi_vld_ack_soc)
    val msi_vld_ack_soc_ris = msi_vld_ack_soc & (~msi_vld_ack_soc_1f)
    //    val fifo_empty = ~fifo_sync.io.deq.valid
    // msi_vld_req : high when fifo empty is false, low when ack is high. and io.deq.valid := ~empty
    when(msi_vld_ack_soc_ris) {
      msi_vld_req := false.B
    }.elsewhen(fifo_sync.io.deq.valid === true.B) {
      msi_vld_req := true.B
    }.otherwise {
      msi_vld_req := msi_vld_req
    }

    // get the msi interrupt ID info
    val msi_id_data = RegInit(0.U(params.MSI_INFO_WIDTH.W))
    val rdata_vld   = fifo_sync.io.deq.fire // assign to fifo rdata
    when(rdata_vld) { // fire: io.deq.valid & io.deq.ready
      msi_id_data := fifo_sync.io.deq.bits(params.MSI_INFO_WIDTH - 1, 0)
    }.otherwise {
      msi_id_data := msi_id_data
    }
    // port connect: io.valid is interrupt file index info.
    msiio.data := msi_id_data
    val backpress = fifo_sync.io.enq.ready
    (intfileFromMems zip reggen.regmapIOs).map {
      case (intfileFromMem, regmapIO) => intfileFromMem.regmap(regmapIO._1, regmapIO._2, backpress)
    }
  }
}


//generate axi42reg for IMSIC
class AXIRegIMSIC(
    params:      IMSICParams,
    beatBytes:   Int = 4,
    seperateBus: Boolean = false
)(implicit p: Parameters) extends LazyModule {
  val fromMem = Seq.fill(if (seperateBus) 2 else 1)(AXI4Xbar())
  val axi4tolite = Seq.fill(if (seperateBus) 2 else 1)(LazyModule(new AXI4ToLite()(Parameters.empty)))
  fromMem zip axi4tolite.map(_.node) foreach (x => x._1 := x._2)
  private val intfileFromMems = Seq(
    AddressSet(params.mAddr, pow2(params.intFileMemWidth) - 1),
    AddressSet(params.sgAddr, pow2(params.sgRegionWidth) - 1)
  ).zipWithIndex.map { case (addrset, i) =>
    val intfileFromMem = AXI4RegMapperNode(
      address = addrset,
      beatBytes = beatBytes
    )
    intfileFromMem := (if (seperateBus) fromMem(i) else fromMem.head)
    intfileFromMem
  }
  
  lazy val module = new AXIRegIMSICImp(this)
  class AXIRegIMSICImp(outer: LazyModule) extends LazyModuleImp(outer) {
    val msiio          = IO(Flipped(new MSITransBundle(params))) // backpressure signal for axi4bus, from imsic working on cpu clock
    private val reggen = Module(new RegGen(params, beatBytes))
    // ---- instance sync fifo ----//
    val FifoDataWidth = params.MSI_INFO_WIDTH

    // depth:8, data width: FifoDataWidth
    private val fifo_sync = Module(new Queue(UInt(FifoDataWidth.W), 8))
    val stageValid = RegInit(false.B)
    val stageBits = Reg(UInt(FifoDataWidth.W))
    val stageReady = !stageValid || fifo_sync.io.enq.ready
    fifo_sync.io.enq.valid := stageValid
    fifo_sync.io.enq.bits := stageBits
    when(stageReady) {
      stageValid := reggen.io.valid
      when(reggen.io.valid) {
        stageBits := reggen.io.seteipnum
      }
    }
    // fifo rd,controlled by msi_vld_ack from imsic working on csr clock.
    // msi_vld_ack_soc: sync result with soc clock
    val msi_vld_ack_soc = WireInit(false.B)
    val msi_vld_ack_cpu = msiio.vld_ack
    val msi_vld_req     = RegInit(false.B)
    val s_idle :: s_waitAckSet :: s_waitAckClr :: Nil = Enum(3)
    val handshakeState = RegInit(s_idle)
    when(params.EnableImsicAsyncBridge.B) {
      msi_vld_ack_soc := AsyncResetSynchronizerShiftReg(msi_vld_ack_cpu, 3, 0)
    }.otherwise {
      msi_vld_ack_soc := msi_vld_ack_cpu
    }
    fifo_sync.io.deq.ready := handshakeState === s_idle
    msiio.vld_req := msi_vld_req
    switch(handshakeState) {
      is(s_idle) {
        when(fifo_sync.io.deq.fire) {
          msi_vld_req := true.B
          handshakeState := s_waitAckSet
        }
      }
      is(s_waitAckSet) {
        when(msi_vld_ack_soc) {
          msi_vld_req := false.B
          handshakeState := s_waitAckClr
        }
      }
      is(s_waitAckClr) {
        when(!msi_vld_ack_soc) {
          handshakeState := s_idle
        }
      }
    }

    // get the msi interrupt ID info
    val msi_id_data = RegInit(0.U(params.MSI_INFO_WIDTH.W))
    val rdata_vld   = fifo_sync.io.deq.fire // assign to fifo rdata
    when(rdata_vld) { // fire: io.deq.valid & io.deq.ready
      msi_id_data := fifo_sync.io.deq.bits(params.MSI_INFO_WIDTH - 1, 0)
    }.otherwise {
      msi_id_data := msi_id_data
    }
    // port connect: io.valid is interrupt file index info.
    msiio.data := msi_id_data
    val backpress = stageReady
    (intfileFromMems zip reggen.regmapIOs).map {
      case (intfileFromMem, regmapIO) => intfileFromMem.regmap(regmapIO._1, regmapIO._2, backpress)
    }
  }
}

//integrated for async clock domain,kmh,zhaohong
class RegGen(
    params:    IMSICParams,
    beatBytes: Int = 4
) extends Module {
  val regmapIOs = Seq(
    params.intFileMemWidth,
    params.sgRegionWidth
  ).map { width =>
    val regmapParams = RegMapperParams(width - log2Up(beatBytes), beatBytes)
    (IO(Flipped(Decoupled(new RegMapperInput(regmapParams)))), IO(Decoupled(new RegMapperOutput(regmapParams))))
  }
  // define the output reg: seteipnum is the MSI id,vld[],valid flag for interrupt file domains: m,s,vs1~vsgeilen
  val io = IO(Output(new Bundle {
    val seteipnum = UInt(params.MSI_INFO_WIDTH.W)
    val valid     = Bool()
  }))
  val valids       = WireInit(VecInit(Seq.fill(params.intFilesNum)(false.B)))
  val seteipnums   = WireInit(VecInit(Seq.fill(params.intFilesNum)(0.U(params.imsicIntSrcWidth.W))))
  val outseteipnum = RegInit(0.U(params.MSI_INFO_WIDTH.W))
  val outvalids    = RegInit(VecInit(Seq.fill(params.intFilesNum)(false.B)))

  (regmapIOs zip Seq(1, params.sgIntFilesNum)).zipWithIndex.map { // seq[0]: m interrupt file, seq[1]: banked s&vs interrupt files
    case ((regmapIO: (DecoupledIO[RegMapperInput], DecoupledIO[RegMapperOutput]), intFilesNum: Int), i: Int) =>
      {
        // j: index is 0 for m file for seq[0],index is 0~params.geilen for S intFile for seq[1]: S, G1, G2, ...
        val maps = (0 until intFilesNum).map { j =>
          val flati = i + j // seq[0]:0+0=0;seq[1]:(0~geilen)+1
          val seteipnum = WireInit(0.U.asTypeOf(Valid(UInt(params.imsicIntSrcWidth.W))));
          dontTouch(seteipnum)
          valids(flati)     := seteipnum.valid
          seteipnums(flati) := seteipnum.bits
          j * pow2(params.intFileMemWidth).toInt -> Seq(RegField(
            32,
            0.U,
            RegWriteFn { (valid, data) =>
              when(valid) { seteipnum.bits := data(params.imsicIntSrcWidth - 1, 0); seteipnum.valid := true.B }; true.B
            }
          ))
        }
        regmapIO._2 <> RegMapper(beatBytes, 1, true, regmapIO._1, maps: _*)
      }
      for (i <- 0 until params.intFilesNum) {
        when(valids(i)) {
          outseteipnum := Cat(i.U, seteipnums(i))
        }
      }
      outvalids    := valids
      io.seteipnum := outseteipnum
      io.valid     := outvalids.reduce(_ | _)
  }
}
