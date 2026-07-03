# Interrupt-File Pooling Design and Implementation

本文记录 Interrupt-File Pooling 的设计和当前实现。目标是在启用 Smmtt 时保持多 IMSIC bank 的隔离语义；在未启用 Smmtt 时，把多个 IMSIC bank 中闲置的 VS interrupt files 重新映射成一个统一的逻辑 IMSIC 视图，减少硬件闲置。

当前代码没有单独新增一个 `PooledIMSIC` class，而是把这层 wrapper 逻辑折叠进 `IMSICMulti`。原因是 `IMSICMulti` 已经处在 MSI path、CSR path 和 output path 的汇合处，直接在这里实现可以复用原来的多 bank IMSIC 硬件，并让单个 `IMSIC` core 继续只理解本地 AIA interrupt-file 编号。

## Naming

文档中仍采用 `PooledIMSIC` 作为概念模块名。这个名字表示对外呈现一个已经池化后的 IMSIC 视图，比 `PoolingIMSIC` 更像硬件模块名称，也更适合作为 RTL class/module 名。

论文中建议使用完整机制名 **Interrupt-File Pooling**。如果需要缩写，可以写作 **IFP**。相比 `IntFile Pooling`，这个名字更正式，也更容易让读者直接理解为 interrupt file 级别的资源复用。

## Module Position

概念上，`PooledIMSIC` 位于 `MultiIMSIC` 外侧：

```text
TLIMSIC / CSR path / MSI path
  -> PooledIMSIC
       -> MultiIMSIC
            -> IMSIC bank 0
            -> IMSIC bank 1
            -> ...
```

`MultiIMSIC` 仍然负责维护多套 IMSIC 硬件。`PooledIMSIC` 负责根据当前是否启用 Smmtt，决定这些 IMSIC banks 对外暴露为“多个 domain IMSIC”还是“一个 pooled IMSIC”。

当前实现中，这个结构被简化为：

```text
TLIMSIC / AXI4IMSIC / CSR path / MSI path
  -> IMSICMulti
       runtime mode select:
         smmttEnable = 1: Smmtt isolated bank view
         smmttEnable = 0: pooled logical IMSIC view
       -> IMSIC bank 0
       -> IMSIC bank 1
       -> ...
```

这样没有增加新的实体层级，但保留了同样的架构语义。

## Runtime Mode Switch

新增 `fromSmmtt.smmttEnable` 作为运行时模式选择：

- `smmttEnable = 1`：Smmtt mode。`sdicn` 选择当前 supervisor domain 对应的 IMSIC bank。
- `smmttEnable = 0`：pooling mode。多个 bank 对外表现为一个 logical IMSIC。

测试初始化默认把 `smmttEnable` 置 1，以保持原有 Smmtt 测试语义。pooling 测试会显式把它置 0。

## Smmtt Enabled

当 Smmtt 启用时，wrapper 不重新解释 logical interrupt file。MSI 和 CSR 仍按 domain bank 隔离语义路由：

```text
external domain / sdicn / address selection
  -> IMSICMulti Smmtt routing
  -> selected physical IMSIC bank
```

这种模式下，每个 supervisor domain 仍然访问自己对应的 IMSIC bank。`sdicn` 无效时，S/VS CSR 访问仍然报 illegal。`toSmmtt.msdeip` 和 `toSmmtt.lsdeip` 也只在这个模式下有效。

## Smmtt Disabled

当 Smmtt 未启用时，wrapper 将多个 IMSIC banks 的 VS interrupt files 映射成一个逻辑 IMSIC。外部软件看到的是一个连续的 VS file 空间，而不是多个 domain banks。

基本思想：

```text
logical file index
  -> decode to (bankId, localFileIndex)
  -> route CSR/MSI/claim to selected IMSIC bank
  -> mux rdata/topei/pending outputs back to one logical IMSIC view
```

当前实现采用 VS-only pooling：保留单一 architectural M/S file 语义，将 bank 0 的 M/S file 作为逻辑 M/S file；所有 bank 的 VS files 组成连续 logical VS file 空间。额外 bank 的 S file 不作为第二个 S file 暴露，而是被重新解释成 pooled VS slot。

示例映射：

```text
logical M file       -> bank 0 M file
logical S file       -> bank 0 S file
logical VS file 1    -> bank 0 VS file 1
...
logical VS file N    -> bank 0 VS file N
logical VS file N+1  -> bank 1 VS file 1
...
```

对默认参数 `geilen = 7`、`imsicNum = 2`：

```text
logical M     -> bank 0 M
logical S     -> bank 0 S
logical VS1   -> bank 0 VS1
...
logical VS7   -> bank 0 VS7
logical VS8   -> bank 1 VS1
...
logical VS14  -> bank 1 VS7
```

原来 domain 1 的 `guestID = 0` 地址槽在 Smmtt mode 中表示 bank 1 S file；在 pooling mode 中它被重新解释为 logical VS8，而不是第二个 S file。

如果后续确实需要把所有 bank 的 M/S files 也纳入池化，需要额外定义多个 M/S file 对 AIA CSR、claim、pending summary 的可见性规则；这会比 VS-only pooling 更偏离 AIA 原始模型。

## Interface Behavior

Wrapper 处理三类接口：

- MSI path：根据 MSI 地址中的 logical file index 解码到目标 `bankId` 和 `localFileIndex`，再把改写后的 local payload 发给对应 bank。
- CSR path：根据当前 CSR 访问的 privilege、`vgein` 或 logical file selector 路由到对应 bank。
- Output path：把多个 bank 的 `pendings`、`notifies`、`topeis` 或 AIA-style pending summary 重新组合为一个逻辑 IMSIC 输出。

Smmtt enabled 时，这些逻辑应尽量退化为 wire pass-through，避免影响原有隔离路径。

## Current Implementation Details

### Parameters and Widths

`IMSICParams` 增加了 pooled 视图相关参数：

- `poolingView`：top-level `IMSICMulti` 使用 pooled CSR 视图，单个 physical `IMSIC` core 使用 local 视图。
- `localIntFilesNum = 2 + geilen`：单个 physical bank 内的 M/S/VS 数量。
- `pooledGeilen = imsicNum * geilen`：pooling mode 下可见的 logical VS 数量。
- `csrGeilen = poolingView ? pooledGeilen : geilen`。
- `intFilesNum = 2 + csrGeilen`：top-level `toCSR.pendings` 在 pooling 视图下变宽。
- `INTP_FILE_WIDTH = log2Ceil(localIntFilesNum)`：MSI payload 中的 file index 仍然保持本地 file index 宽度，不随 pooled pending 宽度扩大。

单个 `IMSIC` core 使用 `coreParams = params.copy(imsicNum = 1, poolingView = false)`，所以 core 内部合法性检查、gateway、CSR 选择仍按本地 `geilen` 工作。

### MSI Path

Smmtt mode：

```text
extFileIndex = 0 -> bank 0 M
extFileIndex > 0 -> extImsicIndex bank, local extFileIndex
```

Pooling mode：

```text
extFileIndex = 0 -> bank 0 M
otherwise:
  sgSlot = extImsicIndex * (1 + geilen) + (extFileIndex - 1)
  sgSlot = 0 -> bank 0 S
  sgSlot in 1..pooledGeilen:
    logicalVgein = sgSlot
    bankId = (logicalVgein - 1) / geilen
    localVgein = 1 + ((logicalVgein - 1) % geilen)
    localFileIndex = 1 + localVgein
```

如果 pooling mode 下访问未映射的尾部 SG slot，wrapper 会 ack 并 drop 这个 MSI，避免 FIFO 因为无人接收而卡住。

### CSR Path

Smmtt mode：

```text
M access  -> bank 0
S/VS access with valid sdicn -> sdicn-selected bank
S/VS access with invalid sdicn -> illegal
```

Pooling mode：

```text
M access  -> bank 0 M
S access  -> bank 0 S
VS access:
  valid logical vgein in 1..pooledGeilen
    -> decode to (bankId, localVgein)
    -> route CSR and claim to that bank
  invalid logical vgein
    -> illegal
```

Wrapper 会把 logical `fromCSR.vgein` 翻译成 core-local `vgein`，因此单个 `IMSIC` core 不需要知道 pooling。

### Output Path

Smmtt mode：

- `toCSR.pendings` 保持原有语义：bank 0 的 M pending 加上 `sdicn` 当前 bank 的 S/VS pending，高位补 0。
- `toCSR.topeis(0)` 来自 bank 0 M。
- `toCSR.topeis(1/2)` 来自 `sdicn` 当前 bank。
- `toSmmtt.msdeip/lsdeip` 继续报告各 bank 是否存在 S/VS pending。

Pooling mode：

- `toCSR.pendings` 重新拼成一个 logical IMSIC pending summary：

```text
bit 0                 -> bank 0 M
bit 1                 -> bank 0 S
bit 1 + logicalVgein  -> pooled logical VS logicalVgein
```

- `toCSR.topeis(0)` 来自 bank 0 M。
- `toCSR.topeis(1)` 来自 bank 0 S。
- `toCSR.topeis(2)` 根据 logical `vgein` 选择对应 bank 的 local VS `topei`。
- `toSmmtt.msdeip/lsdeip` 在 pooling mode 下置 0，因为此时不对外暴露 Smmtt domain pending summary。

## Tests

新增 `test/imsic/imsic_pooling.py`，并加入 `test/imsic/Makefile` 默认 IMSIC 回归：

- `imsic_pooling_vs_msi_test`：验证 logical VS 跨 bank pooling，例如 logical VS9 路由到 bank 1 VS2。
- `imsic_pooling_extra_s_slot_reinterpreted_as_vs_test`：验证额外 bank 的 S 地址槽不会作为第二个 S file，而会作为 pooled VS。
- `imsic_pooling_invalid_tail_slot_drops_msi_test`：验证未映射尾部 slot 会被 drop 且不会堵塞后续 MSI。

测试 helper 增加：

- `set_smmtt_enable()`：运行时切换 Smmtt/pooling mode。
- `imsic_pooled_vs_file_addr()`：把 logical VS file 转换成对应 SG 地址槽。
- `pooled_vs_int_vgein()`：向 pooled logical VS file 发送 MSI。

已验证：

```bash
.tools/bin/pixi run make -B gen/filelist.f
.tools/bin/pixi run make -B gen_axi/filelist.f
.tools/bin/pixi run make run-imsic
.tools/bin/pixi run make run-integration
.tools/bin/pixi run make run-axi
```

## Resolved and Remaining Questions

- 已确定：未启用 Smmtt 时只池化 VS files，不池化额外 S files。
- 已确定：logical `vgein` 从 1 开始连续编号，按 `bankId = (vgein - 1) / geilen`、`localVgein = 1 + ((vgein - 1) % geilen)` 解码。
- 已确定：pooled pending summary 宽度等于 `1 M + 1 S + all pooled VS files`。
- 暂未实现：软件可见 capability CSR。当前模式由 `fromSmmtt.smmttEnable` 外部输入控制。
