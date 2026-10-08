# Pi-Agent 可借鉴优化思路清单

## Metadata
- **Status**: draft
- **Created**: 2026-10-07
- **Author**: GuineaPig Team
- **Package**: guineapig-aiagent | guineapig-client
- **Related Docs**: [agent 设计](【04-02】详细设计-Agent思路.md)、[复杂任务编排](【04-03】完整解决方案-AI-Agent复杂任务编排.md)、[aiagent-llm-integration](aiagent-llm-integration.md)、[guineapig-client](guineapig-client.md)
- **来源**: 对 [Pi-Agent Book](https://dg-ai-notes.pages.dev/modules/ch01-overview)（v0.80.2 源码，10 章）的对比研读

## Overview

GuineaPig 的 Agent 采用 **Plan-then-Execute（Workflow 模式）**：服务端一次性做意图识别 + 生成 DAG，再由 `DAGExecutionEngine` 按拓扑序确定性执行；工具执行按信任边界拆分到 server（web/rag/memory）与 client（CLI/MCP-stdio/skill）。Pi-Agent 是 **ReAct Agent Loop（模式 3）**：模型在循环里逐轮决定下一步。

两者范式不同，**不建议全盘照搬**，但 Pi 在工程化细节上有大量成熟、低耦合、可独立迁移的设计。本文按「迁移价值 × 落地成本」整理为四档，供后续排期。

> 参考坐标：`packages/guineapig-aiagent/app/agent/*`、`packages/guineapig-aiagent/app/services/llm_pipeline.py`、`packages/guineapig-client/src/main/index.ts`

---

## 第一档 · 低成本高收益，建议直接抄

| # | 思路 | Pi 的精髓 | GuineaPig 现状 / 借鉴点 |
|---|------|-----------|------------------------|
| 1 | **错误即消息**（Error as Message） | 工具任何一步出错都不抛异常，统一编码成 `isError:true` 的 `ToolResultMessage` 发给模型，让模型自己纠错（重试/换路径/解释）。"错误信息是给模型的反馈，不是给框架的终止信号" | `CapabilityHandlers.execute` 失败返回 `{"error":...}` 只用于重试，从不回喂模型。引入"失败也回喂 planner 一次"可让 DAG 具备纠错能力 |
| 2 | **工具错误分层** | 工具**内部**主动识别已知错误、包装成"为什么错+怎么改"的具体描述；框架 catch 只在没识别时兜底透传 `err.message`。Bash 工具会把"已输出的内容+中止原因"打包 | 现有错误多为 `f"执行异常: {e}"` 这类笼统文案。改成"文件不存在，目录下有 X/Y"级别的具体描述，模型/用户都能自己修 |
| 3 | **五步工具管道** | `prepareArguments → Schema 验证 → beforeToolCall → execute → afterToolCall`，前 3 步失败都不执行 | 已有 client 白名单 + 参数注入校验（≈ beforeToolCall），但缺**参数 Schema 校验**（模型可能给错类型）和 **afterToolCall 脱敏/审计**钩子 |
| 4 | **agent_settled 收尾信号** | `message_end` 一轮会触发多次，不能当收尾；`agent_settled` 每 prompt 只发一次，是可靠的"整轮结束"信号 | `EXECUTION_COMPLETE` 基本对齐，但流式 chat pipeline 缺明确的"整轮落库/推 done"语义，值得统一 |
| 5 | **工具进度可观察**（onUpdate） | `execute` 可边跑边推 `tool_execution_update`（Bash 每行输出实时可见）；用 `acceptingUpdates` 标志防止结束后的孤儿回调污染 | 语音场景长任务尤其需要中间反馈，client delegate 执行 MCP/CLI 时可回推进度 |

---

## 第二档 · 架构借鉴，提升可维护性

| # | 思路 | Pi 的精髓 | GuineaPig 借鉴点 |
|---|------|-----------|-----------------|
| 6 | **内核 + 叠加** | 最简 Loop 仅 ~10 行，steering/followUp/钩子都是"可剥离的叠加层"。试金石：剥掉任一层里层仍能跑 | `DAGExecutionEngine`（803 行）把编排内核、重试、SSE、指标上报、MCP 注入、client 委托揉在一起。可拆为"内核执行器 + 可插拔中间件" |
| 7 | **协议 > 实现** | 不用 `BaseProvider` 继承，而是定义事件协议（12 种事件）+ 函数签名 `StreamFunction`。各家在"发消息"上无共性，继承找不到公共代码 | `Pipeline` Processor 链已是类似思路（好），但能力注册/执行层可再协议化，减少 `if capability.startswith("mcp_")` 类硬编码分支 |
| 8 | **三层类型递进** | `Tool`（能描述）→ `AgentTool`（能执行）→ `ToolDefinition`（能展示/扩展），每层只加本层能力，靠 wrapper 桥接 | `CapabilityInfo`/`DAGStep`/`TimelineEntry` 层次不错，但 `MCPToolInfo` 与 dict 混用（见 `_inject_conn_params`）是类型漏，值得统一 |
| 9 | **Operations 抽象** | 工具不直接调 `fs`/`child_process`，而依赖最小接口（`ReadOperations`/`BashOperations`），于是可 mock、可 SSH、可容器化 | MCP/CLI 执行分散在 client `main/index.ts` 直接 `spawn`。抽出 `CommandOperations` 接口后，测试与"远程执行"会简单很多 |
| 10 | **两套事件管道** | `subscribe`（不等、只读、丢弃返回值）vs 扩展 `pi.on`（等、读返回值、能拦截）。区分标准：**你的代码要不要改变 Agent 行为** | 目前只有"只读观察"（SSE），缺"可拦截改写"的扩展点。加一个 `beforeToolCall` 钩子式扩展机制，让客户自定义安全策略而无需改内核 |

---

## 第三档 · 上下文与记忆，长期价值最高

| # | 思路 | Pi 的精髓 | GuineaPig 借鉴点 |
|---|------|-----------|-----------------|
| 11 | **多层防护**（没有银弹） | 截断管"单条太大"、系统提示组装管"规范注入"、Compaction 管"长对话"、Branch Summary 管"分支遗忘"，四层互补、互不替代 | 已有 `memory_summarize` 和 pipeline 注入，但缺**单条工具结果截断**（一条大 RAG/MCP 结果就可能撑爆窗口）和**系统提示分层组装** |
| 12 | **双向截断 + 双限制** | `truncateHead`（读文件，保留开头）vs `truncateTail`（bash 输出，保留末尾）；行数(2000)+字节(50KB)双限制谁先触发谁赢；UTF-8 边界安全；截断后附"逃生通道"临时文件路径 | 成熟算法可直接抄。RAG 检索结果、MCP 返回、记忆摘要都应过这道关。参考 Pi `tools/truncate.ts` |
| 13 | **系统提示词动态组装** | 从 cwd 向上递归所有 `CLAUDE.md`，用 XML `<project_instructions path=...>` 包装，明确优先级和边界 | skill 注入可借鉴：用结构化 XML 而非裸拼文本，让模型分清"系统指令 vs 检索内容 vs 用户问题" |
| 14 | **Skills 懒加载（推 vs 拉）** | 系统提示只放 skill 清单（~500 token），LLM 按需用 read 拉全文（~50K token）。**用工具调用做按需上下文加载** | `SkillSelectionProcessor` 是"用 LLM 选技能再全文注入"（推模式）。可改成"清单常驻 + 需要时拉"，省大量 token |
| 15 | **结构化摘要 + 增量更新** | 压缩强制填 6 个 section（Goal/Constraints/Progress/Key Decisions/Next Steps/Critical Context），多次压缩用 `previousSummary` 增量更新 | 记忆摘要是自由的。固定模板能显著减少"忘了用户最初要什么"的漂移 |
| 16 | **文件跟踪累积** | 摘要末尾附 `<read-files>`/`<modified-files>`，跨多次压缩累积 | 可类比跟踪"本轮执行过的能力/步骤/涉及文件"，让摘要携带可验证的元信息 |
| 17 | **压缩时序：两轮之间** | 压缩不在对话中触发，而是每轮 `agent_end` 后检查阈值（`contextWindow - reserveTokens`），下一轮重建上下文 | 可在 `EXECUTION_COMPLETE` 后加上下文预算检查，而非等 backend 固定 15 天窗口 |

---

## 第四档 · 更大改造，视产品方向取舍

| # | 思路 | Pi 的精髓 | 何时该借鉴 |
|---|------|-----------|-----------|
| 18 | **ReAct 回环重规划** | 每轮把工具结果喂回模型再决策，`stopReason` 是唯一信号灯，"无 toolCall 即停" | 需要处理"计划外情况"（检索为空、步骤失败）时，在 DAG 上叠一层**受限 re-plan**，而非全盘 ReAct |
| 19 | **Session Tree（append-only）** | 对话是只追加的树，回退/分支只移动 `leafId` 指针，不删数据；"认父不认子"是 append-only 的必要条件 | 要做"走错路就分叉"的语音多分支探索时。目前线性 conversation 可先做只读的"历史分叉视图" |
| 20 | **节点化状态变量** | "切模型/切思考级别"也存成树节点，回退时状态自动回到当时的值 | 极优雅。会话中途切模型若也节点化，回退语义天然正确 |
| 21 | **prepareNextTurn 动态换模型** | 每轮结束可换模型/上下文/思考级别——简单任务用便宜模型，发现复杂再自动升级 | 现有 `is_small_model` 靠调用方预设，可改成"按当前任务复杂度动态选模型" |
| 22 | **steering 半双工插队** | 用户可在 Agent 工作时插队输入，在 Turn 之间注入 | 语音场景用户打断是刚需；`requires_confirmation` 目前是执行前一次性确认，可升级为运行中可插话 |
| 23 | **模型层统一协议** | `stream()` 查表派活 + `StreamFunction` 宪法 + 12 种统一事件；思考级别/缓存都用"统一枚举+映射表" | 现只支持 OpenAI 兼容协议。若接 Anthropic/Gemini 原生能力（thinking、cache），这套抽象是范本 |
| 24 | **缓存标记（cacheRetention）** | 语义枚举 none/short/long，各家翻译成 cache_control/cachePoint/prompt_cache_key；Anthropic rolling cache 打在 system+最后 tool+最后 user | 直接影响 API 成本（缓存命中约 1/10 输入价），长对话收益明显 |
| 25 | **上下文溢出三重检测** | `isContextOverflow` 用错误模式匹配 + token 对比 + 输出为零 + length 三种信号，统一各家溢出表现 | 目前若 API 静默截断，可能拿到空回复却不知原因 |

---

## 优先落地建议（Top 3）

1. **错误即消息 + 错误分层**（#1 #2）——让 DAG 具备自纠错能力，改动最小、收益最大。
2. **工具输出截断**（#12）——单条大结果撑爆窗口是现实风险，直接移植 `truncate.ts` 思路即可。
3. **内核+叠加 重构 + 可拦截扩展点**（#6 #10）——让 `engine.py` 可测试、可定制。

### 已编写实施计划

| 优化 | 计划文档 | 建议顺序 |
|------|----------|---------|
| #1 #2 错误即消息 + 错误分层 | [`docs/superpowers/plans/2026-10-07-agent-error-as-message.md`](../superpowers/plans/2026-10-07-agent-error-as-message.md) | 1 |
| #12 工具输出截断 | [`docs/superpowers/plans/2026-10-07-tool-output-truncation.md`](../superpowers/plans/2026-10-07-tool-output-truncation.md) | 2 |
| #6 #10 内核+叠加 重构 | [`docs/superpowers/plans/2026-10-07-engine-kernel-overlay.md`](../superpowers/plans/2026-10-07-engine-kernel-overlay.md) | 3（迁移前两者的内联实现为中间件） |

---

## 附录 · Pi-Agent 各章核心设计速查

| 章 | 主题 | 可带走的思路 |
|----|------|-------------|
| Ch01 | 开篇 | 减法哲学；扩展/技能/模板/主题/包 五根定制杠杆；三层堆栈 + 正交 UI 库 |
| Ch02 | 三层架构 | 每层可独立复用；依赖方向严格单向 |
| Ch03 | Agent Loop | Trace/Turn 两级语义；stopReason 单一信号灯；内核+叠加；steering/followUp；prepareNextTurn；shouldStopAfterTurn |
| Ch04 | 模型调用 | 协议 > 实现；12 种统一事件 + StreamFunction；统一枚举+映射表；语义统一、实现分散；缓存策略 |
| Ch05 | 工具系统 | 三层类型递进；五步管道；错误即消息；分层错误处理；并行/串行三阶段调度；onUpdate；Operations 抽象 |
| Ch06 | 消息系统 | 双层消息（AgentMessage vs LLM Message）+ convertToLlm 翻译边界 |
| Ch07 | 事件驱动 | 两套管道（不等 vs 等+返回值）；4 层嵌套事件；fail-closed；agent_settled 可靠收尾 |
| Ch08 | 上下文工程 | 多层防护；双向截断；系统提示动态组装；Skills 懒加载；加法+减法=塑形 |
| Ch09 | 压缩 | 两轮之间触发；向后遍历+合法切点；结构化摘要+增量更新；文件跟踪；turnPrefix |
| Ch10 | 会话管理 | 拆开"存哪里"和"长什么样"；Session Tree append-only；认父不认子；节点化状态；buildSessionContext 压扁；延迟写入 |

---

## Open Questions

- [ ] 第三档 #12 截断算法的阈值（行数/字节）需按语音场景调参
- [ ] 第二档 #6 内核重构是否与现有 SSE 事件契约冲突，需先做兼容性评估
- [ ] 第一档 #1 的错误回喂是否会引入 DAG 之外的模型调用，需评估延迟/成本
- [ ] 第四档 #18 受限 re-plan 与产品"低延迟语音"目标如何平衡

## Review Notes
- （待补充）
