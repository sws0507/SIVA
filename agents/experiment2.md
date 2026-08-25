# DTID 硬件开销实验指南

## 1. 实验目标

本实验评估 DTID 相对于标准 AIA 的额外硬件开销，并与采用固定 bank 划分的跨域中断隔离方案进行比较。

主要回答以下问题：

1. DTID 的域标签和投递检查增加了多少面积？
2. 在 guest interrupt file 总数相同时，DTID 与 bank-based 方案的面积差异是多少？
3. 在不同机密域和非机密域资源需求下，各方案能够覆盖多少种分配组合？
4. 所有设计能否满足相同的目标时钟频率？

---

## 2. 实验配置

至少综合以下六组配置：

| 配置 | RTL 版本 | 每个 hart 的 guest interrupt file | 用途 |
| --- | --- | ---: | --- |
| AIA-4 | AIA | 4 | DTID-4 的面积基线 |
| DTID-4 | DTID | 4，可动态分配 | 测量 DTID 机制开销 |
| AIA-8 | AIA | 8 | DTID-8 的面积基线 |
| DTID-8 | DTID | 8，可动态分配 | 与 bank-based 方案进行等容量比较 |
| XiangshanAIA-2D | XiangshanAIA | 4+4 | 固定双域方案 |
| Smsdia-2B | 冻结的 Smsdia 实现 | 4+4 | 固定双 bank 方案 |

当前可使用的候选版本：

| 配置 | Commit |
| --- | --- |
| AIA | `5aba182` |
| DTID | `a1ae83a` |
| XiangshanAIA | `5a42a6b` |
| Smsdia-2B 候选 | `5bed587` |

每个最终结果必须记录完整 commit ID。若实验期间修改 RTL，应为修改后的版本创建新的固定 commit。

> 注意：当前 XiangshanAIA 顶层默认没有完整启用双域 IMSIC。只有在启用并验证 TEE 路径、确认每个 hart 确实包含 4+4 个 guest interrupt file 后，才能将其标记为 XiangshanAIA-2D。
>
> Smsdia-2B 也应在确认其确实实例化两个独立 bank 后再作为正式比较对象。

---

## 3. 固定参数

除 guest interrupt file 的数量和隔离机制外，其余参数必须保持相同：

- hart 数量：4
- APLIC interrupt source width：7
- IMSIC EIID width：9
- 总线接口：TileLink
- IMSIC asynchronous bridge：关闭
- 综合顶层：`TLAIA`
- 综合工具和版本：`TODO`
- 标准单元库：`TODO`
- 工艺节点：`TODO`
- 目标时钟周期：`TODO ns`
- 综合优化选项：所有配置完全相同

AIA 和 DTID 的 `geilen` 必须同时在 APLIC 和 IMSIC 参数中设置：

- AIA-4、DTID-4：`geilen = 4`
- AIA-8、DTID-8：`geilen = 8`
- 双 bank 方案：每个 bank 的 `geilen = 4`

功能测试可以只触发 8 个中断源，但硬件开销实验应报告 RTL 中实际综合的 source 和 EIID 数量。

---

## 4. RTL 生成

不要在同一个 `gen/` 目录中反复生成不同配置，以免残留文件被错误纳入综合。建议为每组配置建立独立的 Git worktree：

```sh
git worktree add --detach test_result/hardware_cost/worktrees/aia4 5aba182
git worktree add --detach test_result/hardware_cost/worktrees/aia8 5aba182
git worktree add --detach test_result/hardware_cost/worktrees/dtid4 a1ae83a
git worktree add --detach test_result/hardware_cost/worktrees/dtid8 a1ae83a
git worktree add --detach test_result/hardware_cost/worktrees/xiangshan2d 5a42a6b
git worktree add --detach test_result/hardware_cost/worktrees/smsdia2b 5bed587