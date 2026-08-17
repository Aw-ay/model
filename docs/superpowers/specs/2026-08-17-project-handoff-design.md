# RFSoC 工程无聊天记录交接包设计

日期：2026-08-17  
状态：已确认，待实施计划

## 1. 目标

将当前 RFSoC 工程从 Golden Model、Cycle Model、生成 Verilog、双极化连续反射、AMD IP 规范化一直到 connected RFDC Block Design 的完整工程演进，整理为仓库内可版本控制、可校验、可由全新 Codex 聊天读取的 Markdown 交接包。

迁移时只需要工程目录和 Git 数据，不复制 Codex session、SQLite、memory、代理消息或原始聊天记录。交接包必须让另一台电脑上的全新聊天在不访问旧聊天的情况下恢复当前工程状态、证据边界、阻塞原因和后续实施顺序。

## 2. 非目标

- 不保存或改写原始聊天记录。
- 不复制 `%USERPROFILE%\.codex`、认证令牌、OAuth 状态、审批记录或本机 secrets。
- 不把推测、未验证结论或代理的过程性讨论提升为工程事实。
- 不在本任务中修复 connected BD Task 5、运行 Task 6 Vivado、修改模型或生成 RTL。
- 不承诺迁移旧 Codex 侧边栏、线程索引或账号状态。

## 3. 证据优先级

交接包中的事实按以下优先级确定：

1. 当前 Git 文件、配置和提交；
2. 已通过独立复核的设计、计划、合同与验收文档；
3. 可复现的 Python、生成器和 Vivado 测试结果；
4. `.superpowers/sdd` 中与工程直接相关的实施和独立复核结论；
5. 聊天内容仅用于发现遗漏，不能作为交接包引用来源。

若来源冲突，必须保留较高优先级来源，并在交接包中明确指出旧结论已被替代。任何未能由工程文件、提交、测试输出、哈希或工具读回支持的内容都不得写为已确认事实。

## 4. 交接包结构

交接包固定放在 `docs/handoff/`：

```text
docs/handoff/
├─ README.md
├─ CURRENT_STATE.md
├─ ARCHITECTURE.md
├─ DECISIONS.md
├─ VERIFICATION_EVIDENCE.md
├─ IMPLEMENTATION_HISTORY.md
├─ OPEN_ISSUES.md
├─ NEXT_STEPS.md
├─ FILE_INDEX.md
└─ NEW_CHAT_PROMPT.md
```

### 4.1 `README.md`

作为唯一入口，定义交接包用途、证据优先级、推荐读取顺序和按任务类型读取其他文档的路由。新聊天不得要求一次性加载整个历史。

### 4.2 `CURRENT_STATE.md`

记录当前仓库、worktree、分支、HEAD、已完成任务、当前阻塞和未启动任务。必须区分主开发分支与 connected-BD 隔离分支，并说明 worktree 绝对路径只代表生成交接包时的本机状态。

### 4.3 `ARCHITECTURE.md`

说明完整系统边界：

- 2.8 GHz 信号发射与采集；
- 8 ADC/8 DAC 双极化物理映射；
- V/H 的高、中、低三量程与校准/主动对消通道；
- Golden → Cycle → generated Verilog 单向演进；
- RFDC 2.6、DDC/DUC、PL 抽取和采样域；
- 双极化连续反射主链；
- monitor 脉冲检测、粗 IQ、粗 PDW 和事件式上传；
- PS、RFDC、DMA、GEM3 与连接式 Block Design 的责任边界。

### 4.4 `DECISIONS.md`

记录已经冻结且会约束后续实现的决策，包括采样率、RFDC AXI 字格式、量程、舍入模式、内部延迟、PulseRecord 物理约束、RFDC 2.6、PS `pl_clk0=100 MHz`、RX/TX 数据域 250 MHz、只上传命中脉冲 IQ/PDW，以及 generated RTL 不得手工修改。

每项决策必须给出来源文件或 commit；若决定仍为 pending，不能写入已冻结区。

### 4.5 `VERIFICATION_EVIDENCE.md`

保存可复现证据摘要：

- Python 测试命令、解释器和结果；
- 生成器的确定性与哈希；
- Vivado 2025.2 与目标 part；
- RFDC probe 的 CONFIG、interface、scalar 计数；
- ADC/DAC AXIS 宽度、fabric 时钟与 2.8 GHz NCO；
- IP catalog、candidate 和 production lock 绑定；
- 明确尚未完成的 CDC、时序、实现、MTS runtime 和板级回环。

测试通过只能证明其实际覆盖的边界，不得把 Python/XSIM 结果描述为 Vivado 时序、CDC 或硬件验收。

### 4.6 `IMPLEMENTATION_HISTORY.md`

按阶段列出工程演进、关键 commit、实施结论、独立复核和已被替代的方案。至少覆盖：

1. Golden/common 合同；
2. 双极化连续反射 Golden；
3. Cycle 2SPC 与 legacy reference；
4. AMD IP schema、catalog evidence、production lock；
5. legacy RTL 隔离；
6. connected RFDC shell Task 1–5。

该文件是工程历史摘要，不复制代理对话或逐轮聊天文本。

### 4.7 `OPEN_ISSUES.md`

记录所有会阻止后续集成或 production-ready 判定的问题。当前必须包括：

- Task 5 报告到机器证据协议连续三次未闭环；
- `CDC_SAFE`、`CLOCK_SAFE`、`TIMING_CONSTRAINED` 为测试专用标记但生成 Tcl/Vivado 报告不产生；
- MTS 属性名称未由 Task 4 probe 权威证明；
- GEM3 board I/O、PHY 地址、reset 时序和 RGMII delay 尚未完整冻结；
- production 2SPC、monitor 事件链、DMA/UDP、CDC、时序、MTS runtime 与板级验证尚未完成。

每个问题必须说明影响、已有证据、不可宣称的结论和解除条件。

### 4.8 `NEXT_STEPS.md`

给出后续任务的有序执行链、依赖和检查点。默认从修订 Task 5 证据协议与真实 MTS property probe 开始，通过独立复核后才能进入 Task 6，之后依次接入 production 2SPC、monitor、事件 DMA/GEM3、CDC/时序和板级验收。

不得把未通过前置门的任务标为可并行实施。

### 4.9 `FILE_INDEX.md`

建立权威文件索引，使用仓库相对路径，覆盖：

- ModelConfig、architecture config、platform config 和 IP lock；
- Golden、Cycle、DSL、生成器和 generated/reference RTL；
- connected request/evidence、RFDC probe、Tcl 与 runner；
- 物理映射、接口格式、固定点、延迟、PDW 和 ownership 合同；
- 对应测试、设计、计划和验收文档。

必须依赖仓库外文件时，只记录其角色、SHA-256、预期相对定位规则和缺失时的 fail-closed 行为，不把旧电脑的绝对路径当作可移植权威。

### 4.10 `NEW_CHAT_PROMPT.md`

提供可直接复制到全新 Codex 聊天的启动提示，要求新聊天：

1. 先读取 `docs/handoff/README.md` 和 `CURRENT_STATE.md`；
2. 现场核对分支、HEAD、工作树和关键文件；
3. 不信任过时绝对路径或未复现的历史测试；
4. 不重复已完成且已复核的任务；
5. 不把模型测试等同于 Vivado、CDC、时序或板级验收；
6. 在修改前读取对应权威配置、合同、测试和计划；
7. 从 `OPEN_ISSUES.md` 与 `NEXT_STEPS.md` 指定的检查点继续。

## 5. 内容过滤与脱敏

允许写入的内容：

- 架构、物理映射和采样域；
- 技术决策及其依据；
- 仓库相对路径、分支、commit、哈希；
- 测试命令、测试结果、Vivado 读回与验收边界；
- 已知缺陷、失败尝试、停止原因与后续检查点。

禁止写入的内容：

- 原始用户或助手聊天文本；
- Codex session ID、SQLite、memory、代理消息和内部审批历史；
- `auth.json`、OAuth token、环境 secrets、账号信息；
- 与工程无关的本机用户名、临时路径或应用状态；
- 无工程证据支撑的推断。

仓库内已有的用户名或绝对路径若属于可复现命令，交接包应改写为变量或说明其不可移植性；不得为保持旧命令而泄露无必要的用户配置。

## 6. 新聊天读取流程

推荐读取顺序：

1. `docs/handoff/README.md`；
2. `docs/handoff/CURRENT_STATE.md`；
3. `docs/handoff/NEW_CHAT_PROMPT.md`；
4. 根据当前任务，从 README 路由到架构、决策、证据、问题或下一步文档；
5. 对准备修改的模块，再读取 FILE_INDEX 指向的源码、测试和合同。

该流程避免一次加载完整历史，同时保证新聊天知道哪些事实需要现场复验。

## 7. 一致性和质量检查

交接包生成后必须执行：

- 扫描 `TODO`、`TBD`、placeholder 和未决歧义；
- 扫描 `.codex`、session ID、聊天原文、认证文件名和 secrets；
- 验证 FILE_INDEX 中的仓库相对路径存在；
- 验证记录的 commit 可由 Git 解析；
- 验证关键 root/package 配置及 lock 镜像保持字节一致；
- 将测试数量、Vivado 版本、RFDC 读回和哈希与现有证据交叉核对；
- 执行 `git diff --check`；
- 由独立复核者仅依赖交接包和工程文件，判断是否能正确解释当前状态。

任何失败都必须在提交交接包前修正；不能用聊天补充缺失信息。

## 8. 迁移验收标准

在另一台电脑只恢复工程目录和 Git 数据后，全新聊天必须能够：

1. 从 `docs/handoff/README.md` 找到读取顺序；
2. 识别 connected-BD 分支和生成交接包时的 HEAD；
3. 解释 Task 5 的三次尝试及为什么不能直接进入 Task 6；
4. 找到 Golden/Cycle/Verilog、RFDC、双极化和物理映射权威文件；
5. 区分已验证事实、pending 责任和未执行验收；
6. 不依赖旧 Codex 聊天、memory 或本机数据库；
7. 给出与 `NEXT_STEPS.md` 一致的后续实施入口。

## 9. 交付边界

本设计完成后的下一阶段仅编写交接包实施计划。计划获确认后才生成 `docs/handoff/` 文件、执行检查、独立复核并提交。迁移压缩包和 Git bundle 可在交接包通过验收后单独创建，不纳入仓库源码提交。
