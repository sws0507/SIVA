# Dynamic Tag Interrupt Isolation

本文记录一种基于 AIA 的轻量级中断域隔离方案。目标是在不复制整个 IMSIC 的情况下，实现机密域和非机密域之间的中断投递隔离。

## Design Goal

传统的多 IMSIC 方案可以通过复制 IMSIC bank 来隔离不同 supervisor domain，但硬件开销较高。Dynamic Tag 方案保留单套 IMSIC 结构，通过给中断文件和中断源增加域标签，在 MSI 地址侧携带动态 tag，从而区分机密域和非机密域的投递路径。

本方案暂定支持两个域：

- 非机密域：domain bit 为 `0`。
- 机密域：domain bit 为 `1`。

文中使用 `sec` 表示 IMSIC 当前所在的安全域：

```text
sec = 0 -> current domain is non-confidential
sec = 1 -> current domain is confidential
```

## IMSIC Side

IMSIC 的输入接口需要增加当前域信号 `sec`。该信号用于约束 CSR 配置路径，表示当前访问 IMSIC 的软件上下文属于机密域还是非机密域。

IMSIC 增加一个额外的 S-level interrupt file。这样每个 IMSIC 内部有两个 S `IntFile`，分别服务于非机密域和机密域：

```text
internal IntFile 1 -> non-confidential S file
internal IntFile 2 -> confidential S file
```

这两个 S `IntFile` 分别对应不同的 MSI 写入地址。非机密域仍使用原始 S file 地址，机密域使用增加 `0x800` tag 后的地址。IMSIC 在接收 MSI 写入时，先根据地址 tag 判断目标域，再把中断投递到对应的 S `IntFile`。

注意：虽然 IMSIC 内部增加了一个 S `IntFile`，但是外部 MSI 地址中的 guestID 编码不变。`guestID = 0` 仍然表示 S-level interrupt file slot，不会新增一个 guestID 来表示 confidential S file。

当前 SIVA 实现中的文件编号分为两层：

```text
external MSI-visible files:
  0 -> M file
  1 -> S slot, guestID = 0
  2 -> VS file for guestID = 1
  3 -> VS file for guestID = 2
  ...

internal IMSIC files:
  0 -> M file
  1 -> non-confidential S file
  2 -> confidential S file
  3 -> VS file for guestID = 1
  4 -> VS file for guestID = 2
  ...
```

每个 IMSIC 增加一个 `IntFile` bitmap，用于记录每个 VS-level interrupt file 所属的域。因为当前只支持两个域，所以每个 VS interrupt file 只需要 1 bit。

`IntFile` bitmap 是 IMSIC 内部寄存器，只允许 M-mode 访问和配置。S-mode/VS-mode 不能直接修改该 bitmap，避免普通 supervisor domain 改变自身或其他域的中断归属。

示例含义：

```text
IntFileBitmap[n] = 0  -> interrupt file n belongs to the non-confidential domain
IntFileBitmap[n] = 1  -> interrupt file n belongs to the confidential domain
```

In the current code this bitmap is exposed as a machine-mode implementation-defined indirect CSR at `0x78`. Bit `n` controls the VS file for `guestID = n + 1`.

## CSR Configuration Check

IMSIC 的配置接口是 `fromCSR`。通过 `fromCSR` 对 interrupt file 进行配置时，IMSIC 需要根据目标 interrupt file 所属的域检查当前 `sec`。

对机密域内 interrupt file 的配置必须满足：

```text
target interrupt file domain = confidential
sec = 1
```

如果 `sec = 0`，则不能通过 `fromCSR` 修改机密域内 interrupt file 的状态。该访问应被忽略、拒绝，或返回实现定义的非法访问结果；关键要求是不能改变机密域 interrupt file 的配置和 pending state。

非机密域 interrupt file 可以保持原 AIA 的配置行为。若后续希望做对称隔离，也可以要求非机密域 interrupt file 的配置必须满足 `sec = 0`。

## APLIC Side

APLIC 增加一个 `IntSource` bitmap，用于记录每个 interrupt source 所属的域。当前同样只支持两个域，所以每个 interrupt source 使用 1 bit。

示例含义：

```text
IntSourceBitmap[i] = 0  -> interrupt source i belongs to the non-confidential domain
IntSourceBitmap[i] = 1  -> interrupt source i belongs to the confidential domain
```

APLIC 在生成 MSI 地址和 MSI 数据后，根据 `IntSource` bitmap 对 MSI 地址进行域标记处理。

In the current code the `IntSource` bitmap is mapped at APLIC domain offset `0x2800`. Source 0 is read-only non-confidential.

## MSI Address Tagging

APLIC 生成标准 AIA MSI 地址和数据后，按照 interrupt source 的域属性修改 MSI 地址：

- 非机密域：MSI 地址保持不变。
- 机密域：MSI 地址增加 `0x800`，也就是在原 interrupt file 页内增加半页偏移。

因此，两个域的有效 MSI 投递地址形式为：

```text
non-confidential: page_base(n)
confidential:     page_base(n) + 0x800
```

这里 `n` 表示目标外部 interrupt file slot 的索引。SIVA 当前 IMSIC file page stride 是 `0x1000`，因此 `page_base(n)` 对应原 AIA 地址中的 `0x1000 * n` 页偏移。`0x800` 作为页内动态 tag，不改变 guestID 或 interrupt file slot 编码，但让 IMSIC 能在接收 MSI 写入时区分该写入来自哪个域。

IMSIC 内部的 MSI payload 扩展为：

```text
msiio.data = { addrSec, externalFileIndex, interruptId }
```

`externalFileIndex` 仍然按照原 AIA guestID 布局编码。`addrSec` 来自 MSI 写入地址是否带有 `+0x800` tag。

## IMSIC Receive Check

IMSIC 接收到 MSI 写入时，需要同时检查地址 tag 和 `IntFile` bitmap。

规则如下：

- 若目标是 S-level interrupt file，则根据 MSI 地址 tag 选择对应的 S `IntFile`：未带 tag 投递到非机密 S `IntFile`，带 `+0x800` tag 投递到机密 S `IntFile`。
- 若目标 VS interrupt file 属于非机密域，则只允许未带 tag 的 MSI 地址写入。
- 若目标 VS interrupt file 属于机密域，则只允许带 `+0x800` tag 的 MSI 地址写入。
- 如果 MSI 地址 tag 与 `IntFile` bitmap 不匹配，则丢弃该 MSI 写入，不能更新 pending bit。

该检查让错误域或恶意域生成的 MSI 无法投递到不属于自己的 interrupt file。

## Delivery Flow

一次 APLIC 到 IMSIC 的 MSI 投递流程如下：

```text
interrupt source
  -> APLIC checks IntSource bitmap
  -> APLIC generates MSI address and data
  -> APLIC adds 0x800 to the MSI address for confidential sources
  -> MSI write reaches IMSIC
  -> IMSIC decodes interrupt file index and address tag
  -> IMSIC checks IntFile bitmap
  -> matching domain: update pending bit
  -> mismatched domain: drop the MSI write
```

## CSR Outputs

因为 IMSIC 内部同时维护机密域和非机密域的 S/VS interrupt files，输出到 CSR 侧的 pending 信息需要区分当前域和另一域。

当前 SIVA 接口实现为：

```text
toCSR.pendings -> pending bitmap for the current sec domain
toCSR.notifies -> pending bitmap for the opposite sec domain
toCSR.topeis   -> top external interrupts for the current sec domain
```

`pendings` 和 `notifies` 都使用外部 AIA interrupt file 编号，而不是内部编号：

```text
bit 0 -> M intFile for pendings, constant 0 for notifies
bit 1 -> S intFile selected by sec
bit 2 -> VS intFile for guestID 1
bit 3 -> VS intFile for guestID 2
...
```

`pendings.bit1` 在 `sec = 1` 时表示 confidential S `IntFile`，在 `sec = 0` 时表示 non-confidential S `IntFile`；`notifies.bit1` 表示另一域的 S `IntFile`。VS bit 根据 `IntFile` bitmap 与当前 `sec` 的比较结果进入 `pendings` 或 `notifies`。M-level interrupt delivery 仍然是单一的，只属于当前 IMSIC 的本地状态，因此 `pendings.bit0` 表示 M pending，`notifies.bit0` 恒为 0。

`toCSR.topeis(priv)` 中 `priv = 0/1/2` 分别表示 M/S/VS。S topei 由当前 `sec` 选择对应的 S `IntFile`；VS topei 只在当前 `sec` 与 `vgein` 选中的 VS `IntFile` bitmap 一致时输出，否则为 0。

## Notes

Dynamic Tag 的核心思想是把域隔离信息压缩到 interrupt file/source 的 bitmap 和 MSI 地址页内偏移中。它不需要复制整个 IMSIC，但需要确保 `IntFile` bitmap 和 `IntSource` bitmap 都只能由可信的 M-mode 软件配置。

该方案目前只描述两个域。如果未来扩展到更多域，需要重新设计 MSI 地址中的 tag 编码方式，以及 IMSIC 侧的 bitmap 宽度和匹配规则。
