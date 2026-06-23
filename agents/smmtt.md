# Smmtt / Smsdia Notes for SIVA

本文从 `reference/RISCV-Smmtt.pdf` 提取和 SIVA 当前 simple Smmtt/Smsdia 原型相关的信息。该 PDF 标题为
`RISC-V Supervisor Domains Access Protection`，版本为 `0.2.0, 2024-11-13: Draft`，作者为
`RISC-V SmMTT Task Group`。

这里的 `Smmtt` 按项目语境理解为 Supervisor Domain Access Protection 这组机制，重点包括
`Smsdid`、`Smmpt` 和 `Smsdia`。SIVA 当前分支的目标不是实现完整内存保护表，而是先做一个简单的
Smmtt/Smsdia 中断域原型，因此本文最后专门整理了和 IMSIC/APLIC 实现相关的落点。

## 1. 总体模型

Supervisor Domain Access Protection 的目标是让一个平台支持多个 supervisor execution context，并让这些
supervisor domain 对物理内存、设备、中断、调试/trace、QoS 等资源具有差异化访问能力。

核心角色：

| 名称 | 含义 |
| --- | --- |
| Supervisor Domain, SD | 一个被隔离的 supervisor 执行域，可承载 OS、hypervisor、VM 或安全服务。 |
| RDSM | Root Domain Security Manager，运行在 M-mode，负责配置和调度 supervisor domain。 |
| SDSM | Supervisor Domain Security Manager，域内的 OS/hypervisor，负责域内工作负载隔离。 |
| SDID | Supervisor Domain Identifier。由 M-mode CSR 配置，是 hart-local 标识，不应作为全局下游事务标签。 |
| MPT | Machine-level Memory Protection Tables，为 supervisor domain 的物理地址访问提供 RWX 权限。 |

规范定义的相关扩展：

| 扩展 | 作用 |
| --- | --- |
| `Smsdid` | 提供 `mmpt` 和 `msdcfg` 等 M-mode CSR，用于描述当前 hart 关联的 supervisor domain 配置。 |
| `Smmpt` | 通过 MPT 为物理页/区域设置按 domain 区分的 RWX 权限。 |
| `IO-MPT` | 非 ISA 扩展，用于在 IO interconnect/IOMMU/设备侧施加 domain 访问控制。 |
| `Smsdia` | Supervisor Domain Interrupt Assignment，将 IMSIC interrupt files 或 APLIC domain 关联到 supervisor domain。 |
| `Smsdedbg` / `Smsdetrc` | 控制外部 debug/trace 是否允许访问某个 supervisor domain。 |
| `Smqosid` | 为 supervisor domain 管理 QoS/resource monitor 标识。 |

## 2. Smsdid / Smmpt 摘要

`Smsdid` 定义 hart 当前运行在哪个 supervisor domain 下。它的关键接口是 M-mode CSR `mmpt` 和 `msdcfg`。

### `mmpt`

`mmpt` 是 XLEN 位读写 CSR，只允许 M-mode 访问。它包含：

| 字段 | 作用 |
| --- | --- |
| `MODE` | 选择 MPT 模式。 |
| `SDID` | 当前 hart 的 supervisor domain 标识。该标识只在本 hart 局部唯一。 |
| `PPN` | MPT root table 的物理页号。 |

`MODE` 编码：

| XLEN | 模式 | 含义 |
| --- | --- | --- |
| RV32 | `Bare` | 不启用额外 MPT 保护，仅保留既有物理内存保护机制。 |
| RV32 | `Smmpt34` | 支持最多 34-bit 物理地址的 page-based RWX 权限。 |
| RV64 | `Bare` | 同上。 |
| RV64 | `Smmpt46` | 支持最多 46-bit 物理地址的 page-based RWX 权限。 |
| RV64 | `Smmpt56` | 支持最多 56-bit 物理地址的 page-based RWX 权限。 |

要点：

- `SDIDLEN` 的实现位数由实现决定，最大值 `SDIDMAX` 为 6。
- `mmpt` 对物理地址保护算法而言是 active 的，除非 effective privilege mode 是 M-mode。
- 写 `mmpt` 本身不隐含对页表/MPT 更新的排序，需要配合 `MFENCE.SPA` 或 `MINVAL.SPA`。

### `Smmpt`

`Smmpt` 的 MPT walk 使用 supervisor physical address 查表，得到目标物理页/区域对当前 domain 的权限。
权限只能进一步限制访问，不能授予页表/PMP 已拒绝的权限。

MPT 粒度和权限：

| 粒度 | 权限编码 |
| --- | --- |
| 1 GiB range | disallow / RX / RW / RWX |
| RV64 2 MiB page 或 RV32 4 MiB page | 每个子区域 2-bit 权限 |
| 4 KiB page | 每页 2-bit 权限 |

2-bit 权限编码：

| 编码 | 含义 |
| --- | --- |
| `00b` | no access |
| `01b` | read + execute |
| `10b` | read + write |
| `11b` | read + write + execute |

MPT 检查适用于 effective privilege mode 非 M 的所有物理内存访问，包括经过地址翻译后的访问和 S-mode
页表隐式访问。MPT violation 作为 instruction/load/store access-fault exception 报给 RDSM。

### `MFENCE.SPA` / `MINVAL.SPA`

`MFENCE.SPA` 是 M-mode fence，用于同步 supervisor domain access-permission 更新。它可按如下范围生效：

| `rs1` | `rs2` | 范围 |
| --- | --- | --- |
| `x0` | `x0` | 所有物理地址、所有 SDID |
| `x0` | 非零 SDID | 某个 SDID 的所有地址 |
| 非零 PADDR | `x0` | 某个物理地址范围、所有 SDID |
| 非零 PADDR | 非零 SDID | 某个 SDID 下的某个物理地址范围 |

`MINVAL.SPA` 是配合 `Svinval` 的细粒度 invalidation，需要和 `SFENCE.W.INVAL`、`SFENCE.INVAL.IR` 组合使用。

## 3. `msdcfg`

`msdcfg` 是 32-bit M-mode read/write CSR，用于描述当前 hart 上 supervisor domain 的活动配置。

位段如下：

| Bits | 字段 | 使用者 |
| --- | --- | --- |
| `31:28` | `SQRID` | `Smqosid` |
| `27:24` | `SML` | `Smqosid` |
| `23:20` | `SRL` | `Smqosid` |
| `19:9` | `WPRI` | 保留 |
| `8` | `SDETRCALW` | `Smsdetrc` |
| `7` | `SDEDBGALW` | `Smsdedbg` |
| `6` | `SSM` | `Smqosid` |
| `5:0` | `SDICN` | `Smsdia` |

本文最关心的是 `SDICN`。它选择当前 hart 上 active supervisor domain interrupt controller。

## 4. Smsdia: Supervisor Domain Interrupt Assignment

默认情况下，supervisor domain 执行期间产生的中断通常先 trap 到 M-mode RDSM，再由 RDSM 转发或注入虚拟中断。
如果某个 supervisor domain 被分配了设备，设备完成 IO 后产生的 external interrupt 也会走类似路径。为了降低
开销，`Smsdia` 允许把外部中断控制器直接关联到 supervisor domain。

规范允许每个 supervisor domain 关联一个 interrupt controller。这个 controller 可以是：

- IMSIC；
- APLIC；
- APLIC + IMSIC，其中 APLIC 将线中断转成 MSI 并投递到 IMSIC；
- 其他实现定义的 interrupt controller。

重要边界：

- S/VS-level external interrupt controller 可以有多个，并由 `msdcfg.SDICN` 选择当前 active controller。
- M-level external interrupt controller 仍然是单一的，并且始终 active。
- `Smsdia` 不影响 M-level external interrupt。

### `msdcfg.SDICN`

`SDICN` 是 WLRL 字段，必须能保存 `0` 到最大已实现 supervisor domain interrupt controller number 的值。

语义：

| `SDICN` 状态 | 行为 |
| --- | --- |
| `0` 或不是已实现 controller number | 视为没有可访问的 active S/VS interrupt controller。 |
| 非零且选择 IMSIC | S/VS-level interrupt pending 和 IMSIC CSR 访问都指向被选中的 IMSIC。 |
| 非零且选择 APLIC | `mip.SEIP` 反映被选中 APLIC 的 S-level external interrupt pending。 |

若 `SDICN` 为 `0` 或无效值：

- `mip.SEIP` 为 0。
- 非 custom 的 `siselect` IMSIC register 编号都表示 inaccessible register。
- M-mode 或 HS-mode 通过 `sireg` 访问 inaccessible register 时触发 illegal instruction exception。
- 访问 `stopei` 触发 illegal instruction exception。
- `hstatus.vgein` 只读为 0。
- `hgeip` 中的 VS-level external interrupt pending signals 为 0。

若 `SDICN` 选择 IMSIC：

- 被选 IMSIC 的 S-level pending signal 反映到 `mip.SEIP`。
- `siselect` / `stopei` 访问被选 IMSIC 的 S-level interrupt register file。
- 被选 IMSIC 的 VS-level pending signals 反映到 `hgeip`。
- `hstatus.VGEIN` 在被选 IMSIC 中选择 guest interrupt file，`vsiselect` / `vstopei` 访问相应 guest file。

若 `SDICN` 选择 APLIC：

- 被选 APLIC 的 S-level external interrupt pending signal 反映到 `mip.SEIP`。

规范直接支持最多 63 个 supervisor domain 与 interrupt controller 关联。更多 domain 可以由 RDSM 仿真，仿真时
可令 `SDICN=0`，并利用 CSR illegal instruction trap 来模拟 IMSIC 行为。

如果实现了 `Smsdia`，复位后 `msdcfg.SDICN` 应为非零，并保存一个已实现 supervisor domain interrupt
controller number。

### `msdeip` / `msdeiph`

`msdeip` 是 MXLEN-bit read-only CSR。RV32 下 `msdeiph` 是 `msdeip[63:32]` 的只读别名；RV64 下不存在
`msdeiph`。

`msdeip[i]` 汇总编号为 `i` 的 supervisor domain interrupt controller 是否有 external interrupt pending：

| Controller 类型 | `msdeip[i]` 含义 |
| --- | --- |
| APLIC | 该 APLIC 的 S-level external interrupt pending signal。 |
| IMSIC | 该 IMSIC 的 S-level pending 与所有 VS-level pending 的逻辑或。 |

`msdeip` 的可见性不依赖当前 `msdcfg.SDICN` 是否有效；即使 `SDICN=0` 或无效，其他 domain/controller 的
pending summary 仍可在 `msdeip` 中被 RDSM 看到。

### `msdeie` / `msdeieh`

`msdeie` 是 MXLEN-bit read-write CSR。RV32 下 `msdeieh` 是 `msdeie[63:32]` 的读写别名；RV64 下不存在
`msdeieh`。

`msdeie` 选择哪些 supervisor domain external interrupt summary 会触发 local supervisor domain external
interrupt (`LSDEI`)。它不会影响 `msdcfg.SDICN` 当前选中 controller 输出给 S/VS-level 的 pending signals。

### `LSDEI`

`Smsdia` 引入 local supervisor domain external interrupt (`LSDEI`)：

- 位号为 16，出现在 `mip`、`mie`、`sip`、`sie`。
- `mip[16]` 和 `sip[16]` 称为 `LSDEIP`。
- `mie[16]` 和 `sie[16]` 称为 `LSDEIE`。
- `mideleg[16]` 控制是否委托给 S-mode。
- 不能委托给 VS-mode，`hideleg[16]` 只读为 0。
- `mip.LSDEIP = ((msdeip & msdeie) != 0)`。
- `sip.LSDEIP` 在未委托给 S-mode 时为 0；委托后读出 `mip.LSDEIP`。

规范给出的同 privilege interrupt 默认优先级中，`LSDEI` 位于 `STI` 之后、`SGEI` 之前。

## 5. 对 SIVA simple Smmtt/Smsdia 原型的含义

当前 SIVA 已经有干净的 AIA baseline：

- `src/main/scala/IMSIC.scala` 中，一个 IMSIC 管理 M、S 和多个 VS interrupt files。
- `IMSICParams.intFilesNum = 2 + geilen`，当前文件布局是 M file、S file、VS guest files。
- `RegGen` 根据 IMSIC MSI 地址页把 MSI 写入转换为 `(interrupt-file index, seteipnum)`。
- `src/main/scala/APLIC.scala` 中已有两个 APLIC domain：M domain 和 SG domain。
- APLIC SG domain 可根据 target 中的 hart/guest index 生成 MSI 地址并投递到 IMSIC。

根据本分支的 simple scope，建议不要复制一整套 IMSIC/APLIC。应在现有 AIA programming model 上增加
supervisor domain 选择：

1. M-level interrupt delivery 保持单一且始终 active。
2. `msdcfg.SDICN` 只选择 S/VS-level 的 active supervisor domain interrupt-controller bank。
3. IMSIC 内部可把 S/VS interrupt files 扩展为按 domain bank 分组：
   - M file 仍只有一个；
   - 每个 supervisor domain bank 含一个 S file 和若干 VS guest files；
   - 对一个 2-domain 原型，可令 `SDICN=1` 选择 domain bank 0，`SDICN=2` 选择 domain bank 1，`SDICN=0`
     表示无直接 controller/仿真路径。
4. CSR 选择逻辑需要跟随 `SDICN`：
   - `siselect` / `sireg` / `stopei` 访问 active bank 的 S file；
   - `hstatus.VGEIN`、`vsiselect`、`vstopei` 访问 active bank 的 VS guest file；
   - `SDICN=0` 或无效时，按规范返回 zero 或 illegal。
5. MSI 地址解码需要携带 supervisor domain bank 信息：
   - M-level MSI 地址空间不变；
   - S/VS-level MSI 地址空间需要能定位到 domain bank + guest file；
   - 简单实现可以先固定两个 domain bank，并在 SG address region 中增加 bank decode，或给不同 bank 分配不同
     SG base/stride。
6. `msdeip` 应做成 pending summary：
   - 每个 bit 对应一个 supervisor domain interrupt controller/bank；
   - IMSIC bank 的 summary 是 S file pending 与所有 VS file pending 的 OR；
   - 即使某个 bank 不是 active bank，也应能被 `msdeip` 观察。
7. `msdeie` 只用于产生 `LSDEI`：
   - `LSDEIP = ((msdeip & msdeie) != 0)`；
   - 不应屏蔽 active bank 正常输出到 `mip.SEIP` / `hgeip` 的 pending。
8. APLIC 侧应继续保持 M domain 和 SG domain 的 AIA 模型：
   - M domain 仍投递到 M-level IMSIC file；
   - SG domain 可以根据 target/配置选择目标 supervisor domain bank；
   - 不建议为 TEE/security domain 复制 legacy IMSIC path。

## 6. 建议测试点

后续实现 simple Smmtt/Smsdia 时，建议补充以下测试：

| 测试 | 期望 |
| --- | --- |
| 两个 `SDICN` 有效值切换 | `siselect/stopei/hgeip/vsiselect/vstopei` 访问不同 domain bank。 |
| `SDICN=0` | `mip.SEIP=0`，`hstatus.vgein=0`，`hgeip=0`，IMSIC CSR 访问按规范 illegal。 |
| 无效 `SDICN` | 行为同 `SDICN=0`。 |
| MSI 投递隔离 | 写入 domain bank 0 的 MSI 不影响 bank 1 的 S/VS pending，反之亦然。 |
| `msdeip` summary | inactive bank 有 pending 时，active bank 不变，但 `msdeip` 对应 bit 置位。 |
| `msdeie` / `LSDEI` | 仅当 `(msdeip & msdeie) != 0` 时置 `LSDEIP`。 |
| M-level delivery | 不受 `SDICN` 切换影响，M file 始终按原 AIA 行为工作。 |
| APLIC SG routing | 同一 wired interrupt 按目标配置投递到正确 supervisor domain bank。 |

## 7. 需要先定下来的实现选择

在写 RTL 前最好明确这些选择：

1. 2-domain 原型中 `SDICN` 的编码：建议 `0=none/emulated`，`1=domain0`，`2=domain1`。
2. SG MSI address space 如何编码 domain bank：新增 bank bit、扩大 stride，还是分配两个 SG base。
3. `msdcfg` 是否先放在 IMSIC 模块内部，还是由上层 CSR block 管理并输入 IMSIC。
4. `msdeip/msdeie/LSDEI` 是否在 IMSIC 内部生成，还是上移到 hart-local interrupt/CSR glue。
5. reset 后 `SDICN` 的默认值：若实现 `Smsdia`，规范要求非零并指向一个已实现 controller；简单原型可默认 `1`。

## 8. 与当前代码的最小对应关系

| 规范概念 | SIVA 当前位置 | 原型改动方向 |
| --- | --- | --- |
| IMSIC S/VS interrupt controller | `IMSIC.scala` 中的 S file 和 guest files | 扩成按 supervisor domain bank 选择的 S/VS file 集合。 |
| `msdcfg.SDICN` | 当前未实现 | 新增 active bank 选择状态，只影响 S/VS，不影响 M。 |
| IMSIC CSR indirection | `fromCSR.addr`、`fromCSR.vgein`、`intFilesSelOH_*` | 在 S/VS 路径加入 `SDICN` bank offset 和 invalid handling。 |
| MSI receive decode | `RegGen` 输出 `Cat(fileIndex, seteipnum)` | 让 SG MSI decode 产生 banked S/VS file index。 |
| Pending summary | `toCSR.pendings` | 增加 `msdeip` 所需的 per-bank OR summary。 |
| APLIC SG MSI route | `APLIC.Domain.getMSIAddr` 和 SG domain target | 让 SG target 能表达目标 supervisor domain bank。 |

