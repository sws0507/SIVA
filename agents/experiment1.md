本节将对前文分析的 AIA 跨域投递缺口进行演示，之后验证 DTID 能否在不可信 host 控制功能路由字段时，对测试配置中的所有允许输入执行跨域隔离？即保证安全不变量  $\operatorname{Commit}(e) \Longrightarrow D_{\mathrm{src}}(s_e)=D_{\mathrm{file}}(f_e)$。我们使用相同的测试环境和输入集合分别测试 AIA baseline 与 DTID，使两者的结果可以直接比较。

我们在 RTL 仿真器上实例化包含 2 个 hart、8 个 guest interrupt file 和 8 个 APLIC interrupt source 的系统。APLIC 的 RTL interrupt source 从 1 开始编号，source 0 是保留/只读 0，不能作为真实中断源使用。因此实验中的 logical source 0-7 分别映射到 RTL source 1-8，论文表述中可以继续使用 logical source 编号。guest interrupt file 也从 1 开始编号，guest identifier 0 不作为 guest interrupt file 使用。每个 hart 上一共运行 2 个机密 vhart 和 2 个非机密 vhart，每个 vhart 分别绑定一个 guest interrupt file 和一个 interrupt source。

对于每个测试事件，我们执行以下步骤：

1. 清空所有 guest interrupt file 的 pending 状态；
2. M-mode 软件设置 intrSource_bitmap 和 intrFile_bitmap，AIA baseline 中忽略这一步；
3. AIA baseline 中，由 VMM 配置每个中断源的目标 hart、guest identifier 和 EIID；DTID 中，由 VMM 配置非机密域中断源的目标 hart、guest identifier 和 EIID，TSM 配置机密域中断源的目标 hart、guest identifier 和 EIID；EIID 不影响中断投递的路由，可以设置为任何有效值；
4. 触发 APLIC interrupt source；
5. 记录 APLIC 生成的 MSI 地址及数据、IMSIC 解码得到的目标文件，以及投递后的 EIP、top interrupt 和 hart-visible pending 输出。

我们遍历两种中断源域与两种目标文件域的全部四种组合，并对测试配置中所有有效的 logical source ID、hart ID、guest identifier 执行测试。我们根据 EIP 的变化将结果分成三类，分别为引起了一个机密域中断，引起了一个非机密域中断和未发生中断。如图所示，在 AIA baseline 中，由于硬件本身不区分机密域和非机密域，只要修改中断源的 target 寄存器，就可以使 APLIC 将任意中断源生成的 MSI 投递到任意一个中断文件中。而 DTID 的结果展示了，机密域的中断源生成的 MSI 只能投递到机密域的 guest 中断文件中，非机密域同样。为了进一步解释，我们具体分析了其中一次投递，如表所示。Logical source 0，即 RTL source 1，是一个非机密域中断源，VMM 将其 target 设置为 hart 0，guest interrupt file 3，对应的是一个机密域的 guest 中断文件。然而 DTID 的 APLIC 扩展保证了生成的 MSI 地址是一个非机密域地址。IMSIC 端的 domain check 会自动过滤掉这次 MSI write。
