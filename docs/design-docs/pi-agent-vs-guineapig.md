# Pi-Agent 与 GuineaPig 实现对比分析

## Metadata
- **Status**: draft
- **Created**: 2026-10-08
- **Author**: GuineaPig Team
- **Package**: guineapig-aiagent | guineapig-client
- **Related Docs**: [Pi-Agent 可借鉴优化思路](pi-agent-borrowable-ideas.md)、[Agent 思路](【04-02】详细设计-Agent思路.md)、[复杂任务编排](【04-03】完整解决方案-AI-Agent复杂任务编排.md)、[LangGraph 重构方案](langgraph-migration-design.md)、[aiagent-llm-integration](aiagent-llm-integration.md)
- **来源**: 对 [Pi-Agent Book](https://dg-ai-notes.pages.dev/modules/ch01-overview)（v0.80.2 源码，10 章）与当前 `packages/guineapig-aiagent/app/agent/*` 实现的对比研读

## Overview

本文对比 **Pi-Agent**（Mario Zechner 的终端编码 Agent）与 **GuineaPig 当前 Agent 实现**，说明两者的范式差异、逐维度区别以及各自的优缺点，作为后续借鉴排期的决策依据。

> 参考坐标：
> - GuineaPig：`packages/guineapig-aiagent/app/agent/executor/*`、`app/agent/dag/*`、`app/agent/intent/*`、`app/agent/capability_registry.py`、`app/services/llm_pipeline.py`、`app/routers/agent.py`、`packages/guineapig-client/src/main/index.ts`
> - Pi-Agent：`packages/coding-agent/src/core/tools/truncate.ts` 等（见章节速查表）

---

## 一、根本差异：范式不同

| | **Pi-Agent** | **GuineaPig 当前实现** |
|---|---|---|
| 范式 | **ReAct Agent Loop**（模式 3）：模型在循环里逐轮决定下一步 | **Plan-then-Execute**（Workflow）：一次性生成 DAG，再拓扑序确定性执行 |
| 决策者 | 模型（每轮） | 服务端编排（DAGGenerator）+ 引擎 |
| 循环粒度 | Trace → Turn → 工具调用，`stopReason` 单一信号灯 | 意图 Phase 0-3 → 生成 DAG → 逐步执行 |
| 工具位置 | 全本地（fs / child_process） | **信任边界拆分**：server（web/rag/memory/llm）vs client（CLI/MCP-stdio/skill） |
| 目标场景 | 本地长任务编码，单人，延迟可容忍 | 低延迟语音对话、多用户、Electron 客户端 |

这是最核心的区别：Pi 是"边想边做"的动态 Agent，GuineaPig 是"先规划后执行"的工作流引擎。二者**不应全盘照搬**，但 Pi 在工程化细节上有大量可迁移设计。

---

## 二、逐维度对比

| 维度 | Pi-Agent | GuineaPig 现状 |
|---|---|---|
| **Agent Loop** | 内核 ~10 行，steering/followUp/钩子都是可剥离叠加层 | `DAGExecutionEngine`（`executor/engine.py`，967 行，已抽出 middleware） |
| **编排** | 无 DAG，模型动态选工具 | `dag/generator.py` + `dag/validator.py` + 引擎 |
| **工具管道** | 五步：prepare → Schema 校验 → beforeToolCall → execute → afterToolCall | 白名单 + 参数注入校验 + 引擎重试；**缺参数 Schema 校验** |
| **错误处理** | 错误即消息（`isError:true` 回喂模型），工具内部识别、框架兜底 | ✅ 已实现：`executor/errors.py` 分层 + `handlers.py` 具体文案 + 有界自纠错 `replanner.py` |
| **输出截断** | 双向（head/tail）+ 行/字节双限制 + UTF-8 安全 | ✅ 已实现：`executor/truncate.py`（移植 `truncate.ts`） |
| **内核 + 叠加** | 最简内核 + 可插拔叠加层 | ✅ 已实现：`executor/middleware.py`（before/after/on_error 三钩子） |
| **模型层** | 协议 > 实现，12 种统一事件 + StreamFunction 抽象 | 仅 OpenAI 兼容协议，`AsyncOpenAI` 直连 |
| **事件管道** | 两套：只读 `subscribe` vs 可拦截 `pi.on` | 只读 SSE；middleware 提供了"可拦截改写"（部分对齐） |
| **上下文工程** | 多层防护：截断 / 系统提示组装 / Compaction / Branch Summary | memory_summarize + pipeline 注入；**缺系统提示分层 XML 组装** |
| **Skills** | 懒加载（清单常驻 ~500 token，按需 read 全文） | **推模式**：`SkillSelectionProcessor` LLM 选技能后全文注入（`llm_pipeline.py:75`） |
| **压缩** | 两轮之间触发、结构化 6-section 摘要、增量更新、文件跟踪 | Redis 15 天滚动窗口 + 自由文本摘要，**无结构化模板** |
| **会话模型** | Session Tree（append-only）、认父不认子、节点化状态 | 线性 conversation + `AgentEventManager`（asyncio.Event） |
| **HITL** | steering 半双工，运行中可插队 | 执行前一次性确认（`AWAITING_CONFIRMATION`） |
| **客户端委托** | 无（全本地） | SSE 下发 + HTTP 回调，SSE 双任务桥接 |
| **持久化** | 延迟写入文件、Session Tree | Redis task state + timeline（设计文档，部分未落地） |

---

## 三、Pi-Agent 的优缺点

**优点**
- **动态性强**：能处理"计划外情况"（检索为空、步骤失败），每轮用真实结果决策，没有"生成时上下文盲区"。
- **工程解耦极好**：内核 + 叠加，剥掉任一层里层仍能跑；协议 > 实现，各家模型在"发消息"上无共性，因此用事件协议而非继承。
- **上下文工程成熟**：多层防护（截断 / 组装 / 压缩 / 分支摘要）互补，结构化摘要抗漂移，Skills 懒加载省 token。
- **可观察性 / 可扩展**：`onUpdate` 实时进度、两套事件管道（只读 vs 可拦截）、Operations 抽象可 mock / 远程执行。
- **成本优化**：缓存标记（cacheRetention）、`prepareNextTurn` 按复杂度动态换模型。

**缺点**
- **延迟不确定**：每步可能多一次 LLM 调用，循环轮数不可预测，对语音低延迟不友好。
- **可控性弱**：模型每轮决策，难以做"执行前一次性总确认"，多用户 / 权限 / 审计难。
- **无信任边界**：假定工具全本地可信任执行，不适用于 client/server 分离。
- **单人本地定位**：无多租户、无分布式状态、无跨进程委托。

---

## 四、GuineaPig 当前实现的优缺点

**优点**
- **确定性执行**：DAG 拓扑序执行，SSE 事件可预测，天然适配低延迟语音与流式交互。
- **信任边界清晰**：server 直连执行 + client 委托（CLI/MCP-stdio/skill），适合 Electron 客户端与安全隔离。
- **HITL 与审计友好**：执行前展示完整计划让用户确认，Client 侧可弹确认框（设计已定义）。
- **已吸收 Pi 三项精华**：错误即消息 + 分层（`errors.py`）、有界自纠错（`replanner.py`）、双向输出截断（`truncate.py`）、内核 + 叠加（`middleware.py`），全量 236 passed。
- **多用户 / 分布式就绪**：Redis 会话、任务状态、指标上报、限流。

**缺点**
- **静态规划的上下文盲区**：DAGGenerator 生成时看不到每步真实产出，必须"猜"占位符与参数形状 → 偶发参数名错、output_key 对不上（见 `langgraph-migration-design.md` §10）。
- **自纠错仍是"事后补救"**：replan 只是把失败回喂一次生成修正步骤，不是真正每轮动态决策；且 client 端修正步骤被过滤，纠错范围受限。
- **上下文工程偏薄**：Skills 推模式全文注入（浪费 token）、无系统提示分层 XML、无结构化压缩模板、无多层上下文防护。
- **模型层单一**：只支持 OpenAI 兼容协议，无法用 Anthropic/Gemini 原生 thinking/cache，未做缓存标记。
- **事件管道单向**：只有只读 SSE，扩展点靠 middleware 硬接，未抽象成通用 `pi.on` 拦截协议。
- **会话线性**：无 Session Tree / 分支回退，语音"走错路分叉"难支持。

---

## 五、结论

两者**不是替代关系**，而是不同场景的取舍：

- **Pi 的长处**（动态决策、内核解耦、上下文工程、会话树、成本优化）在 **GuineaPig 的低延迟语音 + 多用户 + client/server 拆分**约束下，很多不能直接照搬。
- **GuineaPig 已经完成的**（错误即消息、截断、内核 + 叠加）正是 Pi 借鉴清单里"低成本高收益"的第一、二档，落地质量高、有测试覆盖。
- **剩余可借鉴的**按价值排序：
  1. 工具参数 Schema 校验 + `afterToolCall` 脱敏 / 审计（补五步管道缺口）
  2. Skills 懒加载（省 token）
  3. 系统提示分层 XML 组装
  4. 结构化压缩模板 + 增量更新
  5. 缓存标记降本
  6. 若要处理"计划外情况"，在 DAG 上叠一层受限 re-plan（已做一部分）而非全盘 ReAct

---

## 附录 · Pi-Agent 各章核心设计速查

| 章 | 主题 | 可带走的思路 |
|----|------|-------------|
| Ch01 | 开篇 | 减法哲学；扩展/技能/模板/主题/包 五根定制杠杆；三层堆栈 + 正交 UI 库 |
| Ch02 | 三层架构 | 每层可独立复用；依赖方向严格单向 |
| Ch03 | Agent Loop | Trace/Turn 两级语义；stopReason 单一信号灯；内核 + 叠加；steering/followUp；prepareNextTurn；shouldStopAfterTurn |
| Ch04 | 模型调用 | 协议 > 实现；12 种统一事件 + StreamFunction；统一枚举 + 映射表；语义统一、实现分散；缓存策略 |
| Ch05 | 工具系统 | 三层类型递进；五步管道；错误即消息；分层错误处理；并行/串行三阶段调度；onUpdate；Operations 抽象 |
| Ch06 | 消息系统 | 双层消息（AgentMessage vs LLM Message）+ convertToLlm 翻译边界 |
| Ch07 | 事件驱动 | 两套管道（不等 vs 等 + 返回值）；4 层嵌套事件；fail-closed；agent_settled 可靠收尾 |
| Ch08 | 上下文工程 | 多层防护；双向截断；系统提示动态组装；Skills 懒加载；加法 + 减法 = 塑形 |
| Ch09 | 压缩 | 两轮之间触发；向后遍历 + 合法切点；结构化摘要 + 增量更新；文件跟踪；turnPrefix |
| Ch10 | 会话管理 | 拆开"存哪里"和"长什么样"；Session Tree append-only；认父不认子；节点化状态；buildSessionContext 压扁；延迟写入 |

## Open Questions

- [ ] 参数 Schema 校验是否会与现有 DAGValidator 规则重叠，需评估归并方式
- [ ] Skills 懒加载（拉模式）与现有 `SkillSelectionProcessor`（推模式）如何灰度共存
- [ ] 事件管道是否引入 `pi.on` 式的通用拦截协议，还是继续沿用 middleware 扩展点

## Review Notes
- （待补充）
