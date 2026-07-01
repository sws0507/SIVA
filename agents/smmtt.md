# Smmtt / Smsdia Notes for SIVA

本文从本仓库的 `reference/RISCV-Smmtt.pdf` 以及 RISC-V SmMTT GitHub 仓库当前 `chapter7.adoc`
整理和 SIVA simple Smmtt/Smsdia 原型相关的信息。PDF 标题为 `RISC-V Supervisor Domains Access
Protection`，版本为 `0.2.0, 2024-11-13: Draft`；GitHub `chapter7.adoc` 更新了 Supervisor Domain
Interrupt Assignment 的术语和 AIA 扩展细节。

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

## 3. `msdcfg` / `SDICN`

`msdcfg` 是 32-bit M-mode read/write CSR，用于描述当前 hart 上 supervisor domain 的活动配置。
当前 GitHub `chapter7.adoc` 将相关概念称为 Supervisor Interrupt Domain Number；SIVA 文档和后续实现
统一沿用本分支既有字段名 `SDICN`。

旧 PDF 中 `msdcfg` 位段如下，表中最后一行按本项目命名写作 `SDICN`：

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

本文最关心的是 `SDICN`。它选择当前 hart 上 active supervisor interrupt domain，用于
supervisor-level external interrupt 和 guest external interrupt。`SDICN` 是 WLRL 字段，必须能保存
`0` 到最大已实现 supervisor interrupt domain number 的值；若 hart 只连接一个 supervisor interrupt
domain，`SDICN` 可以只读为 0。

## 4. Smsdia: Supervisor Domain Interrupt Assignment

默认情况下，supervisor domain 执行期间产生的中断通常先 trap 到 M-mode RDSM，再由 RDSM 转发或注入虚拟中断。
如果某个 supervisor domain 被分配了设备，设备完成 IO 后产生的 external interrupt 也会走类似路径。为了降低
开销，`Smsdia` 允许把外部中断控制器直接关联到 supervisor domain。

当前 `chapter7.adoc` 把中断控制器扩展描述为多个 supervisor interrupt domain。每个实现的 supervisor
interrupt domain 编号为 `0..N-1`，可关联到一个 supervisor domain。中断控制器可以是：

- IMSIC；
- APLIC；
- APLIC + IMSIC，其中 APLIC 将线中断转成 MSI 并投递到 IMSIC；
- 其他实现定义的 interrupt controller。

重要边界：

- S/VS-level supervisor interrupt domain 可以有多个，并由 `msdcfg.SDICN` 选择当前 active domain。
- M-level external interrupt controller 仍然是单一的，并且始终 active。
- `Smsdia` 不影响 M-level external interrupt。

### IMSIC extension for supervisor domains

IMSIC 被扩展为支持多个 supervisor interrupt domain。一个 IMSIC supervisor interrupt domain 包含：

- 一个 supervisor-level interrupt file；
- 可选的一个或多个 guest interrupt files；
- 一个 supervisor interrupt domain number，也就是 `SDICN`。

当所有 hart 在单个 hart group 中时，SDICN `n`、hart `h` 的 supervisor-level interrupt file 地址为：

```text
Address = B + n * 2^I + h * 2^D
```

当存在 hart groups 时，group `g`、SDICN `n`、hart `h` 的地址为：

```text
Address = g * 2^E + B + n * 2^I + h * 2^D
```

其中 `B/C/D/E/k` 延续 AIA 的 IMSIC memory-region 术语，`I` 是 Smmtt 为 supervisor interrupt
domains 新增的 domain stride 常量。约束：

- `I >= k + D`，确保一个 SDICN bank 内能覆盖所有 harts；
- 若最大 SDICN 为 `n_max`，`q = ceil(log2(n_max + 1))`；
- `B` 必须按 `2^(q + I)` 对齐；
- 有 hart groups 时，`E >= max(k + C, q + I)`。

`msdcfg.SDICN` 选择 IMSIC supervisor interrupt domain 时：

- 选中 domain 的 S file pending signal 反映到 `mip.SEIP`；
- `siselect` / `sireg` / `stopei` 访问选中 domain 的 S file；
- 选中 domain 的 guest file pending signals 反映到 `hgeip`；
- `hstatus.VGEIN` 在选中 domain 内选择 guest file，`vsiselect` / `vsireg` / `vstopei` 访问该 guest file。

若实现 H extension，硬件需要为每个已实现 SDICN 维护一组内部 `hgeip/hgeie`，CSR `hgeip/hgeie`
按当前 `msdcfg.SDICN` 访问对应元素。

规范通过 64-bit `msideip/msideie` 直接支持最多 64 个 supervisor interrupt domains。更多 domain 可以由 RDSM 仿真，仿真时
可以利用 AIA state-enable bits 触发 illegal instruction trap 来模拟 IMSIC 行为。注意：当前 GitHub 文本中
`SDICN=0` 是一个合法 supervisor interrupt domain number，不再表示 “无 active controller”。

### APLIC extension for supervisor domains

APLIC 本来就支持多个 interrupt domains。为支持 supervisor domains，APLIC 必须支持多个 supervisor-level
interrupt domains。一个 APLIC supervisor-level interrupt domain 可以：

- 使用 direct delivery mode，直接作为某个 supervisor domain 的 interrupt controller；
- 使用 MSI delivery mode，在 hart 使用 IMSIC 时把线中断转成 MSI 投递到对应 IMSIC SDICN bank。

为了支持 MSI delivery mode，`smsiaddrcfgh` 扩展了两个字段：

| Bits | 字段 | 含义 |
| --- | --- | --- |
| `28:24` | `DXS` | Domain Index Shift，domain index 在 MSI 地址中的 bit shift。 |
| `22:20` | `LHXS` | Low Hart Index Shift，沿用 AIA 含义。 |
| `18:16` | `DXW` | Domain Index Width，来自 child index 的 domain index 位数。 |
| `11:0` | High Base PPN | MSI base 高位页号。 |

令 `CI` 为 `sourcecfg[i]` 中的 Child Index，则：

```text
n = CI & (2^DXW - 1)
MSI address =
  (Base PPN | (g << (HHXS + 12)) | (n << DXS) | (h << LHXS) | Guest Index) << 12
```

这里的 `n` 是目标 IMSIC supervisor interrupt domain number；`DXS = I - 12`，与 IMSIC 新增的 domain
stride 常量 `I` 对齐。

`msdcfg.SDICN` 选择 APLIC supervisor interrupt domain 时，该 APLIC domain 的 supervisor-level external
interrupt pending signal 反映到 `mip.SEIP`。

### `msideip` / `msideiph`

`msideip` 是 64-bit read-only M-mode CSR，CSR number 为 `0xF4F`。RV32 下 `msideiph` 是
`msideip[63:32]` 的只读别名，CSR number 为 `0xF5F`；RV64 下不存在 `msideiph`。

`msideip[i]` 汇总编号为 `i` 的 supervisor interrupt domain 是否有 external interrupt pending：

| Controller 类型 | `msideip[i]` 含义 |
| --- | --- |
| APLIC | 该 APLIC supervisor interrupt domain 的 S-level external interrupt pending signal。 |
| IMSIC | 该 IMSIC SDICN bank 的 SEIP 置位，或内部 `hgeip & hgeie` 非零，也就是该 bank 的 SGEIP 会置位。 |

如果后续实现 `Smgeien/Ssgeien`，`mgeien.A/GIF` 会进一步约束 `msideip` 汇总哪些 guest external
interrupts；simple 原型可以先不实现 `Smgeien`，但文档和命名应为后续扩展留出空间。

### `msideie` / `msideieh`

`msideie` 是 64-bit read-write M-mode CSR，CSR number 为 `0x74F`。RV32 下 `msideieh` 是
`msideie[63:32]` 的读写别名，CSR number 为 `0x75F`；RV64 下不存在 `msideieh`。

`msideie` 选择哪些 supervisor interrupt domains 会触发 machine supervisor domain external interrupt
(`MSDEI`)。它不会影响当前 `msdcfg.SDICN` 选中 domain 输出到 `mip.SEIP` 或 `hgeip` 的 pending signals。

### `MSDEI`

`Smsdia` 引入 machine supervisor domain external interrupt (`MSDEI`)：

- 位号为 14，出现在 `mip`、`mie`、`sip`、`sie`。
- `mip[14]` 和 `sip[14]` 称为 `MSDEIP`。
- `mie[14]` 和 `sie[14]` 称为 `MSDEIE`。
- `mideleg[14]` 控制是否委托给 S-mode。
- 不能委托给 VS-mode，`hideleg[14]` 只读为 0。
- `mip.MSDEIP = ((msideip & msideie) != 0)`。
- `sip.MSDEIP` 在 `mideleg[14]=0` 时为 0；委托后是 `mip.MSDEIP` 的 alias。
- 默认同 privilege 中断优先级中，`MSDEI` 位于 `MTI` 之后、`SEI` 之前。

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
2. `msdcfg.SDICN` 只选择 S/VS-level 的 active supervisor interrupt domain。
3. IMSIC 内部把 S/VS interrupt files 扩展为按 SDICN bank 分组：
   - M file 仍只有一个；
   - 每个 SDICN bank 含一个 S file 和若干 VS guest files；
   - 对一个 2-domain 原型，建议 `SDICN=0` 选择 bank 0，`SDICN=1` 选择 bank 1，与 GitHub 当前
     `0..N-1` 编号一致。
4. CSR 选择逻辑需要跟随 `SDICN`：
   - `siselect` / `sireg` / `stopei` 访问 active bank 的 S file；
   - `hstatus.VGEIN`、`vsiselect`、`vstopei` 访问 active bank 的 VS guest file；
   - 如需 RDSM emulation，不要把 `SDICN=0` 当作无效值；应通过 state-enable/访问权限机制制造 illegal trap。
5. MSI 地址解码需要携带 supervisor domain bank 信息：
   - M-level MSI 地址空间不变；
   - S/VS-level MSI 地址空间按 `B + SDICN * 2^I + hart * 2^D + guest * 4KiB` 定位到 bank + guest file；
   - `RegGen` / address decode 应从 SG region 中解析 `SDICN` bank，而不是只解析当前单一 S/VS file index。
6. APLIC SG MSI route 需要表达目标 SDICN：
   - 当前 `sourcecfg` 只有 delegation bit，没有 child index；为 Smmtt 应补上 AIA child index 语义；
   - MSI delivery mode 下，`sourcecfg[i].ChildIndex` 的低 `DXW` 位形成 `n`；
   - `Domain.getMSIAddr` 需要把 `(n << DXS)` 放入 SG MSI 地址；
   - `DXS` 应等于 `I - 12`，并和 IMSIC SG bank stride 保持一致；
   - 对 2-domain 原型可先固定 `DXW=1`，让 `ChildIndex[0]` 选择 SDICN bank。
7. `msideip` 应做成 pending summary：
   - 每个 bit 对应一个 supervisor domain interrupt controller/bank；
   - APLIC bank 的 summary 是该 APLIC supervisor-level pending；
   - IMSIC bank 的 summary 是 S file pending，或该 bank 内部 `hgeip & hgeie` 非零；
   - 即使某个 bank 不是 active bank，也应能被 `msideip` 观察。
8. `msideie` 只用于产生 `MSDEI`：
   - `MSDEIP = ((msideip & msideie) != 0)`；
   - 不应屏蔽 active bank 正常输出到 `mip.SEIP` / `hgeip` 的 pending。
9. APLIC 侧应继续保持 M domain 和 SG domain 的 AIA 模型：
   - M domain 仍投递到 M-level IMSIC file；
   - SG domain 通过 `sourcecfg.ChildIndex` + `smsiaddrcfgh.DXS/DXW` 选择目标 SDICN bank；
   - 不建议为 TEE/security domain 复制 legacy IMSIC path。
10. `Smgeien/Ssgeien` 可作为后续阶段：
    - simple 原型可先让 RDSM/M-mode 独占 bank 切换与 guest enables；
    - 若要让某个 supervisor domain 访问部分 guest files，再实现 `mgeien.A/GIF` 和 per-SDICN `hgeip/hgeie`
      alias 规则。

## 6. 建议测试点

后续实现 simple Smmtt/Smsdia 时，建议补充以下测试：

| 测试 | 期望 |
| --- | --- |
| 两个 `SDICN` 有效值切换 | `siselect/sireg/stopei/hgeip/vsiselect/vsireg/vstopei` 访问不同 SDICN bank。 |
| `SDICN=0` | 作为合法 bank 0 工作，而不是 no-controller。 |
| MSI 投递隔离 | 写入 domain bank 0 的 MSI 不影响 bank 1 的 S/VS pending，反之亦然。 |
| IMSIC 地址 decode | `B + n * 2^I + h * 2^D` 写入只影响 SDICN `n` 的 S file。 |
| APLIC DXS/DXW route | `sourcecfg.ChildIndex[DXW-1:0]` 选择的 SDICN bank 出现在 SG MSI 地址中。 |
| `msideip` summary | inactive bank 有 pending 时，active bank 不变，但 `msideip` 对应 bit 置位。 |
| `msideie` / `MSDEI` | 仅当 `(msideip & msideie) != 0` 时置 `MSDEIP`。 |
| `mideleg[14]` | 未委托时 `sip.MSDEIP/sie.MSDEIE` 为 0；委托后 alias 到 M-level 对应位。 |
| M-level delivery | 不受 `SDICN` 切换影响，M file 始终按原 AIA 行为工作。 |
| APLIC SG routing | 同一 wired interrupt 按目标配置投递到正确 supervisor domain bank。 |
| RDSM emulation path | 若实现 state-enable gating，禁用访问时 IMSIC indirect CSR trap 给 M-mode，且不依赖 `SDICN=0`。 |

## 7. 需要先定下来的实现选择

在写 RTL 前最好明确这些选择：

1. 2-domain 原型中 `SDICN` 编码：建议 `0=domain0`，`1=domain1`。
2. IMSIC SG region 的 `I` 取值：至少满足 `I >= k + D`，并让 `B` 按 `2^(q + I)` 对齐。
3. APLIC `DXS/DXW` 是否先 hardwire：2-domain 原型可 hardwire `DXW=1`、`DXS=I-12`。
4. `sourcecfg.ChildIndex` 如何补进当前 `Sourcecfg`：当前仅有 `D` 和 `SM`，需要兼容 delegation 语义。
5. `msdcfg.SDICN` 放在 IMSIC 模块内部，还是由上层 CSR block 管理并输入 IMSIC/APLIC glue。
6. `msideip/msideie/MSDEI` 在 IMSIC 内部生成，还是上移到 hart-local interrupt/CSR glue。
7. `hgeip/hgeie` per-SDICN array 放在 IMSIC 内，还是放在 CSR glue 并把 enable 结果输入 IMSIC summary。
8. simple 原型是否暂不实现 `Smgeien/Ssgeien`；如果暂不实现，需要避免把相关规则误写进 RTL。

## 8. 与当前代码的最小对应关系

| 规范概念 | SIVA 当前位置 | 原型改动方向 |
| --- | --- | --- |
| IMSIC S/VS interrupt controller | `IMSIC.scala` 中的 S file 和 guest files | 扩成按 supervisor domain bank 选择的 S/VS file 集合。 |
| `msdcfg.SDICN` | 当前未实现 | 新增 active bank 选择状态，只影响 S/VS，不影响 M。 |
| IMSIC CSR indirection | `fromCSR.addr`、`fromCSR.vgein`、`intFilesSelOH_*` | 在 S/VS 路径加入 `SDICN` bank offset；`SDICN=0` 是 bank 0。 |
| IMSIC file count | `IMSICParams.intFilesNum = 2 + geilen` | 改为 `1 + sdicnNum * (1 + geilen)` 一类布局，M file 仍为 index 0。 |
| MSI receive decode | `RegGen` 输出 `Cat(fileIndex, seteipnum)` | 让 SG MSI decode 产生 banked S/VS file index，解析 `SDICN` 和 guest file。 |
| Pending summary | `toCSR.pendings` | 增加 `msideip` 所需的 per-SDICN summary。 |
| `hgeip/hgeie` | 当前 CSR glue 未建 per-domain array | 每个 SDICN 一组内部状态，CSR 按 `msdcfg.SDICN` 选择。 |
| APLIC SG MSI route | `APLIC.Domain.getMSIAddr` 和 SG domain target | 加入 `sourcecfg.ChildIndex`、`smsiaddrcfgh.DXS/DXW`，让 target 表达目标 SDICN bank。 |
| APLIC register model | 当前 hardwire `*msiaddrcfg*` regs，`Sourcecfg` 无 ChildIndex | Smmtt 阶段至少 hardwire/暴露 `DXS/DXW`，并补全 child index 读写。 |

## 9. 当前 simple Smmtt 原型已经做过的改动

本节记录当前工作区为了实现 simple Smmtt/Smsdia 原型已经落到 RTL/测试里的改动。它是实现状态记录，
不是完整规范；后续若继续推进，应以这里为起点检查未完成项。

### IMSIC

`src/main/scala/IMSIC.scala` 已经从单个 S/VS interrupt-file bank 扩展为多 bank 原型：

- `IMSICParams` 新增 `imsicNum`，当前默认 2，用来表示每个 hart 内部的物理 IMSIC supervisor-domain banks。
- 保留单一 M file；S/VS file 按 bank 复制，每个 bank 包含 1 个 S file 和 `geilen` 个 VS guest files。
- 新增 SG 地址布局参数：`sgFilesPerDomain`、`sgHartStrideWidth`、`sgRegionWidth`、`imsicIndexWidth`、
  `sdicnWidth`、`msdeipWidth`，并提供 `sgDomainAddr`、`sgDomainIndex`、`sgAddressSets` 供 bus wrapper 使用。
- MSI 数据宽度扩展为携带 `(imsic bank, local interrupt-file index, interrupt id)`，`RegGen` 为每个 SG bank
  生成独立的 regmap region，并把地址写入解码为 banked MSI target。
- 新增 `SmmttToIMSICBundle` 和 `IMSICToSmmttBundle`，当前原型接口包含：
  - `fromSmmtt.sdicn`：选择 active S/VS bank；
  - `fromSmmtt.msdeie`：选择哪些 bank summary 产生 local summary interrupt；
  - `toSmmtt.msdeip`：每个 bank 的 pending summary；
  - `toSmmtt.lsdeip`：`(msdeip & msdeie).orR` 的本地 summary pending。
- 新增 `IMSICMulti` wrapper：内部实例化 `imsicNum` 个单 bank `IMSIC`，M-mode CSR/MSI 固定路由到 bank 0，
  S/VS CSR 和 claim 跟随 `SDICN` 路由到 active bank。
- `IMSICMulti` 对无效 `SDICN` 的 S/VS CSR 访问置 illegal；`SDICN=0` 是合法 bank 0。
- `toCSR.pendings`、`toCSR.topeis(1)`、`toCSR.topeis(2)` 输出 active bank 的 S/VS 视图，同时保留 bank 0 的
  M-level 输出。
- TL/AXI IMSIC wrapper 改为实例化 `IMSICMulti`，并把 `toSmmtt/fromSmmtt` 端口暴露到上层。
- TL/AXI IMSIC memory map 从原来的单一 SG region 改为 `params.sgAddressSets`，每个 SG bank 一个 address set。

注意：当前 RTL 原型的 summary CSR/interrupt 命名仍使用 `msdeip/msdeie/lsdeip`。若后续要完全贴近当前
GitHub `chapter7.adoc`，需要再决定是否统一改名为 `msideip/msideie/MSDEI`；本文件其他章节按规范语义解释。

### APLIC

`src/main/scala/APLIC.scala` 已经让 SG MSI target 可以表达目标 IMSIC bank：

- `APLICParams` 新增 `imsicNum`，并要求 `imsicNum >= 1`。
- SG 地址参数拆成 `sgHartStrideWidth` 和 `sgDomainStrideWidth`，`groupStrideWidth` 改为同时覆盖 M hart files
  和全部 Smmtt SG banks。
- SG base alignment 改为按 `2^(q+I)` 约束，其中 `q` 来自 bank/domain index width。
- `Domain` 新增 `imsicDomainStrideWidth` 和 `imsicNum` 参数。
- SG `target.GuestIndex` 由原来的 guest id 扩展为 flat guest index：`domain * (geilen + 1) + localGuest`。
- `getMSIAddr` 从 flat guest index 拆出 `domainID` 和 `localGuestID`，并把 `domainID << imsicDomainStrideWidth`
  编入 MSI 地址，从而把 APLIC SG 中断投递到目标 SDICN bank。
- M domain 仍使用原有 M-level IMSIC 地址模型，不参与 SDICN bank 选择。

### Example / 集成封装

`src/main/scala/Example.scala` 和 `src/main/scala/Example-axi.scala` 已同步 simple Smmtt 参数和地址映射：

- `APLICParams` 从 `IMSICParams` 继承 `geilen`、`imsicIntSrcWidth` 和 `imsicNum`，避免 APLIC/IMSIC 参数不一致。
- TL/AXI map 根据 `imsic_params.sgDomainIndex(base)` 识别 SG bank，并映射到
  `sgBaseAddr + domain * 2^sgDomainStrideWidth + member * 2^sgHartStrideWidth`。
- 每个 IMSIC instance 的 `toSmmtt/fromSmmtt` 端口向顶层导出，测试和后续 CSR glue 可以直接驱动 `SDICN`
  和读取 pending summary。

### 测试

IMSIC Cocotb 测试已经从一个大 `main.py` 拆成多个 focused test modules：

- `test/imsic/main.py` 变成入口说明，真实测试分散到 `imsic_m_mode.py`、`imsic_csr.py`、
  `imsic_supervisor.py`、`imsic_smmtt.py`、`imsic_illegal.py`、`imsic_readonly.py`。
- `test/imsic/imsic_common.py` 新增 IMSIC setup helper，统一 reset、初始化和选择 interrupt file。
- `test/common.py` 新增 Smmtt-aware IMSIC 地址 helper：`imsic_m_file_addr`、`imsic_sg_file_addr`，
  以及 `set_sdicn`、`set_msdeie`。
- `init_imsic` 会遍历所有 simple Smmtt banks 初始化 S/VS interrupt files，最后回到 `SDICN=0`。
- `imsic_smmtt_bank_selection_test` 覆盖：
  - `SDICN=0/1` bank 切换；
  - inactive bank pending 不影响 active bank `topei`；
  - VS guest file 按 bank 隔离；
  - `msdeip` per-bank summary；
  - `msdeie` 控制 `lsdeip`；
  - 无效 `SDICN=2` 的 S/VS CSR 访问 illegal。
- `test/aplic/main.py` 新增 SG flat guest index 测试，确认 APLIC 可把 MSI 投递到 domain 1 的 SG bank。
- `test/Makefile.common` 和 `test/imsic/Makefile` 支持按单个 IMSIC test 生成独立 FST waveform 和 XML result。

### 仍需继续完善

当前实现是 simple prototype，还没有完全覆盖规范层面的所有 Smsdia/Smmtt 细节：

- `msdcfg` 真实 CSR 尚未接入；目前测试通过 `fromSmmtt.sdicn` 直接驱动 active bank。
- `msdeip/msdeie/lsdeip` 的命名和当前 GitHub `chapter7.adoc` 的 `msideip/msideie/MSDEI` 仍需最终取舍。
- `hgeip/hgeie` 还不是完整 per-SDICN CSR array；当前 summary 主要来自各 bank S/VS pending。
- APLIC 还没有完整实现 `smsiaddrcfgh.DXS/DXW` 可编程寄存器，也没有真正补齐 `sourcecfg.ChildIndex` 字段；
  当前用 flat `GuestIndex` 表达目标 bank。
- RDSM emulation path、state-enable gating、`Smgeien/Ssgeien`、更多 domain 的软件仿真还未实现。
- APLIC direct delivery mode 的多 supervisor interrupt domains 尚未扩展；当前重点是 APLIC MSI delivery 到 IMSIC banks。
