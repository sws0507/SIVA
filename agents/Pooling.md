# PooledIMSIC Design

本文记录在 `MultiIMSIC` 外侧增加一层 `PooledIMSIC` wrapper 的设计想法。目标是在启用 Smmtt 时保持多 IMSIC bank 的隔离语义；在未启用 Smmtt 时，把多个 IMSIC bank 的 interrupt files 重新映射成一个统一的逻辑 IMSIC 视图，减少硬件闲置。

## Naming

本文采用 `PooledIMSIC` 作为代码模块名。这个名字表示对外呈现一个已经池化后的 IMSIC 视图，比 `PoolingIMSIC` 更像硬件模块名称，也更适合作为 RTL class/module 名。

论文中建议使用完整机制名 **Interrupt-File Pooling**。如果需要缩写，可以写作 **IFP**。相比 `IntFile Pooling`，这个名字更正式，也更容易让读者直接理解为 interrupt file 级别的资源复用。

## Module Position

`PooledIMSIC` 位于 `MultiIMSIC` 外侧：

```text
TLIMSIC / CSR path / MSI path
  -> PooledIMSIC
       -> MultiIMSIC
            -> IMSIC bank 0
            -> IMSIC bank 1
            -> ...
```

`MultiIMSIC` 仍然负责维护多套 IMSIC 硬件。`PooledIMSIC` 负责根据当前是否启用 Smmtt，决定这些 IMSIC banks 对外暴露为“多个 domain IMSIC”还是“一个 pooled IMSIC”。

## Smmtt Enabled

当 Smmtt 启用时，`PooledIMSIC` 不改写地址、CSR 请求或 MSI payload，只做透传：

```text
external domain / sdicn / address selection
  -> PooledIMSIC pass-through
  -> MultiIMSIC bank selection
```

这种模式下，每个 supervisor domain 仍然访问自己对应的 IMSIC bank。隔离语义由 `MultiIMSIC` 保持，pooling 逻辑不参与资源重映射。

## Smmtt Disabled

当 Smmtt 未启用时，`PooledIMSIC` 将多个 IMSIC banks 的 interrupt files 映射成一个逻辑 IMSIC。外部软件看到的是一个连续的 interrupt-file 空间，而不是多个 domain banks。

基本思想：

```text
logical file index
  -> decode to (bankId, localFileIndex)
  -> route CSR/MSI/claim to selected IMSIC bank
  -> mux rdata/topei/pending outputs back to one logical IMSIC view
```

推荐策略是保留单一 architectural M/S file 语义，将 bank 0 的 M/S file 作为逻辑 M/S file；其他 banks 的可复用容量主要作为扩展 VS interrupt files 使用。这样对外仍更像一个标准 AIA IMSIC，只是可用 guest interrupt files 增多。

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

如果后续确实需要把所有 bank 的 M/S files 也纳入池化，需要额外定义多个 M/S file 对 AIA CSR、claim、pending summary 的可见性规则；这会比 VS-only pooling 更偏离 AIA 原始模型。

## Interface Behavior

`PooledIMSIC` 需要处理三类接口：

- MSI path：根据 MSI 地址中的 logical file index 解码到目标 `bankId` 和 `localFileIndex`，再把改写后的 local payload 发给对应 bank。
- CSR path：根据当前 CSR 访问的 privilege、`vgein` 或 logical file selector 路由到对应 bank。
- Output path：把多个 bank 的 `pendings`、`notifies`、`topeis` 或 AIA-style pending summary 重新组合为一个逻辑 IMSIC 输出。

Smmtt enabled 时，这些逻辑应尽量退化为 wire pass-through，避免影响原有隔离路径。

## Open Questions

- 未启用 Smmtt 时，是否只池化 VS files，还是连额外 S files 也暴露出来。
- logical `vgein` 到 `(bankId, localVgein)` 的精确编码方式。
- pooled pending summary 的位宽是否等于 `1 M + 1 S + all pooled VS files`。
- 是否需要为软件暴露一个 capability CSR，报告当前处于 Smmtt mode 还是 pooled mode。
