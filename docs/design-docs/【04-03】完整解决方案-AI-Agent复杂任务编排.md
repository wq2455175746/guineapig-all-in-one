# AI Agent 复杂任务编排 — 完整解决方案

## 1. 现状与问题

### 1.1 当前架构

guineapig 已具备多种 AI 能力，但彼此独立，缺乏协作编排：

```
当前 Pipeline: 平面上下文注入模式
  用户输入 → [Skill注入] + [Search注入] + [RAG注入] → LLM → 命令解析
```

**能做什么**：
- RAG 知识库检索
- 联网搜索注入
- Skill 加载与执行
- MCP 工具调用
- CLI 命令行执行
- 情景记忆读写与总结
- LLM 流式对话

**做不了什么**：
- 多步骤协作（搜索→总结→保存，每步依赖上一步结果）
- 条件分支（搜索结果为空时不执行后续步骤）
- 步骤间数据传递（step1 的输出是 step2 的输入）
- 单步验证 + 重试/补救
- 可恢复执行（aiagent 重启后恢复未完成的任务）
- Human-in-the-Loop（某些步骤需用户确认后才执行）

### 1.2 核心矛盾

所有"行动类"能力（MCP stdio、CLI、Skill）在 **Client 端**（Electron），而"知识/思考类"能力（RAG、搜索、LLM、记忆）在 **Server 端**（AiAgent）。这意味着：

- 执行引擎不能是纯服务端线性流程
- 需要异步委托 + 回调机制
- 部分步骤需要用户确认（HITL）

---

## 2. 执行位置总图

```
┌─────────────────────────────────────────────────────────┐
│                    AiAgent (Server)                       │
│                                                           │
│  直连执行（同步/SSE）             委托执行（异步回调）       │
│  ┌─────────────────────┐       ┌──────────────────────┐  │
│  │ RAG 知识库检索       │       │ 意图引擎             │  │
│  │ 联网搜索             │       │ DAG 生成 + 验证      │  │
│  │ 情景记忆读写         │       │ 执行引擎（编排调度）   │  │
│  │ LLM 流式对话         │       │ 结果验证 + 决策       │  │
│  │ Memory 总结          │       │ Redis 状态管理       │  │
│  │ MCP SSE/HTTP 远程    │       └──────────────────────┘  │
│  └─────────────────────┘                                  │
│                    │ SSE push / HTTP callback              │
└────────────────────┼──────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                  Client (Electron)                        │
│                                                           │
│  ┌────────────┐  ┌──────────┐  ┌────────────┐           │
│  │ MCP stdio  │  │ CLI      │  │ Skill      │  ← 全部     │
│  │ Runtime    │  │ Runner   │  │ Loader     │     Client  │
│  └────────────┘  └──────────┘  └────────────┘     执行    │
│                                                           │
│  ┌────────────────────────────────────────────┐           │
│  │ Task Dispatcher + HITL Dialog (用户确认框) │           │
│  └────────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────┘
```

### 2.1 能力执行位置矩阵

| 能力        | 执行位置   | 通信方式                        | HITL 需要 |
|-----------|--------|-----------------------------|---------|
| RAG 检索    | Server | 直接调用                        | 否       |
| 联网搜索     | Server | 直接调用                        | 否       |
| 情景记忆     | Server | 直接调用                        | 否       |
| LLM 对话    | Server | SSE 流式                       | 否       |
| Memory 总结 | Server | 直接调用                        | 否       |
| MCP SSE    | Server | HTTP 直连远程 MCP Server        | 否       |
| MCP HTTP   | Server | HTTP 直连远程 MCP Server        | 否       |
| MCP stdio  | Client | Server SSE push → Client 执行 → HTTP 回调 | 是       |
| CLI        | Client | Server SSE push → Client 执行 → HTTP 回调 | 是       |
| Skill      | Client | Server SSE push → Client 执行 → HTTP 回调 | 可选     |

---

## 3. 核心工作流

```
我是谁 → 我能干啥 → 你要啥 → 我做过没 → 我能不能干 → 计划给你看 → 你确认 → 一步步干 → 干一步验证一步
```

```
用户输入
   │
   ▼
┌──────────────────────┐
│ 1. 角色认知           │ ← "我是 AI Agent"
│    "我是谁"           │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ 2. 能力盘点           │ ← 实时扫描可用能力清单（MCP/CLI/Skill/Search/RAG）
│    "我能干啥"          │    每个能力附带描述 + 参数 Schema
└──────────┬───────────┘
           ▼
┌──────────────────────┐          ┌─────────────────┐
│ 3. 意图识别 ⭐         │──模糊──→│ 反问澄清          │← 用户补充后重试
│    "你要我干啥"        │          └─────────────────┘
└──────────┬───────────┘
           │ 明确
           ▼
┌──────────────────────┐
│ 4. 经验检索           │ ← 情景记忆查历史相似任务
│    "以前做过没"        │    找到可复用的执行模式
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ 5. 能力匹配           │ ← 严格检查每个步骤是否可用
│    "能不能干"          │    不能 → 直接拒绝，不做死循环
│                       │    能   → DAG 生成 + 验证
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ 6. 计划展示           │ ← 给用户看完整 DAG
│    "我打算这样做"      │    展示步骤、调用的能力、风险
│                       │    等待用户确认/修改/取消
└──────────┬───────────┘
           │ 用户确认
           ▼
┌──────────────────────┐          ┌─────────────────┐
│ 7. 逐步执行 + 验证    │──失败──→│ 有限重试 → 降级   │
│    "一步一步来"        │          │  → 通知用户      │
│    Server 步骤直连     │          └─────────────────┘
│    Client 步骤委托     │
│    每步执行完验证才下一步│
└──────────┬───────────┘
           │ 全部完成
           ▼
┌──────────────────────┐
│ 8. 记忆更新           │ ← 记录执行经验到情景记忆
│    "我学到了"          │    提取用户偏好
│                       │    生成 topic summary
└──────────────────────┘
```

---

## 4. 意图识别（关键设计，Phase 0-3）

意图识别是整个系统的**最核心环节**，需要做到宁可多问一句、不要猜错。

### 4.1 四阶段架构

```
用户消息
   │
   ▼
┌──────────────────────┐
│ Phase 0: 快速筛选     │ ← 纯规则，<5ms，零 LLM 成本
│  trivial → 放行到对话  │
│  simple/complex → 进入深度分析
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ Phase 1: 规则预判     │ ← 关键词映射，<10ms
│  keyword → intent     │    给出候选意图 + 置信度
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ Phase 2: LLM 深度分析  │ ← 一次非流式 LLM 调用
│  输入: 用户消息 + 对话历史 + 可用能力 + 情景记忆
│  输出: 结构化意图 JSON（含置信度、实体、能力映射、可行性）
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ Phase 3: 置信度判定    │ ← 综合 Phase1 + Phase2
│  <0.4 → fallback 到普通对话
│  0.4-0.7 → 反问用户澄清
│  ≥0.7 → 进入 DAG 生成
└──────────────────────┘
```

### 4.2 Phase 0 — 快速筛选

通过纯规则判断当前消息是否需要进入复杂任务流程：

| 分类 | 判断依据 | 处理方式 |
|------|----------|----------|
| trivial | 纯问候、简单肯定/否定、身份询问 | 直接走现有普通对话 Pipeline |
| simple | 无多步关键词，可能涉及 1 个能力 | 进入 Phase 1 |
| complex | 含"先/然后/再"，或多个动词 | 跳转到 Phase 2 |

### 4.3 Phase 1 — 规则预判

关键词 → 意图类型映射表，快速提取候选意图：

```
单词              → 意图类型         基础置信度
─────────────────────────────────────────────
"搜索"/"查一下"   → web_search       0.6
"文档"/"资料"     → rag_search       0.4-0.7
"打开"/"读取"     → mcp_file_op      0.5-0.7
"运行"/"安装"     → cli_execute      0.5-0.7
"skill"/"技能"   → skill_execute    0.6-0.7
"我记得"/"之前"   → memory_retrieve  0.5-0.7
```

输出：按置信度排序的候选意图列表。如果列表为空 → 依赖 Phase 2。

### 4.4 Phase 2 — LLM 深度分析

一次非流式 LLM 调用，prompt 中包含三个关键上下文：

1. **当前可用能力清单**（实时扫描，不是硬编码）
   ```
   你可用的能力:
   - MCP [filesystem](stdio): read_file, write_file, list_directory
   - MCP [github](sse): list_issues, create_pr
   - CLI: 任意 shell 命令
   - Skill [数据分析模板]
   - 联网搜索
   - RAG [guineapig_docs]
   ```

2. **对话历史摘要**（最近几轮）

3. **情景记忆**（相似任务的历史经验）

输出结构化 JSON：

```json
// 正常多步任务
{
  "intent_type": "multi_step",
  "intent_summary": "搜索AI论文并保存到本地",
  "confidence": 0.85,
  "entities": { "keywords": ["AI", "最新论文"] },
  "required_capabilities": ["web_search", "cli_execute"],
  "feasible": true,
  "complexity": "multi_step",
  "estimated_steps": 3
}

// 能力不足
{
  "intent_type": "unknown",
  "confidence": 0.9,
  "required_capabilities": ["chart_drawing"],
  "feasible": false,
  "infeasible_reason": "当前没有绘图工具或 MCP",
  "complexity": "single",
  "estimated_steps": 0
}

// 意图模糊
{
  "intent_type": "ambiguous",
  "confidence": 0.3,
  "feasible": true,
  "complexity": "single",
  "estimated_steps": 0
}
```

### 4.5 Phase 3 — 置信度路由

| 综合置信度 | 策略 | 行为 |
|-----------|------|------|
| < 0.4 | fallback | 回退到普通 LLM 对话，不做任何编排 |
| 0.4-0.7 | ask_user | 反问用户确认意图，给出选择项 |
| ≥ 0.7 + feasible | proceed | 进入 DAG 生成 |
| ≥ 0.7 + !feasible | reject | 直接拒绝，说明缺少什么能力 |

### 4.6 反问用户的设计

不是简单地问"你是想这样吗"，而是展示能力让用户选择：

```
用户: "帮我想想办法"
Agent: 置信度 0.35
→ "你想做什么？我可以帮你：
    1. 搜索互联网信息
    2. 操作本地文件
    3. 执行命令行
    4. 查询知识库文档
   你想试试哪个？"
```

---

## 5. DAG 生成与验证

### 5.1 DAG 步骤模型

```json
{
  "step_id": "s1",
  "capability": "web_search",
  "action": "search",
  "params": {
    "query": "{{user_input.keywords}}",
    "max_results": 5
  },
  "output_key": "search_result",
  "execution_location": "server",
  "depends_on": [],
  "fallback": {
    "max_retries": 2,
    "alternative_capability": "rag_search",
    "timeout_seconds": 30
  },
  "requires_confirmation": false
}
```

### 5.2 步骤间的数据引用

后续步骤通过 `{{step_id.output_key.field}}` 引用前序步骤的结果：

```json
[
  {
    "step_id": "s1",
    "capability": "web_search",
    "params": {"query": "2026 AI论文"},
    "output_key": "raw_results"
  },
  {
    "step_id": "s2",
    "capability": "llm_chat",
    "params": {
      "prompt": "请总结以下内容：{{s1.raw_results.content}}"
    },
    "output_key": "summary",
    "depends_on": ["s1"]
  },
  {
    "step_id": "s3",
    "capability": "cli_execute",
    "params": {
      "command": "cat > /tmp/ai_summary.md",
      "stdin": "{{s2.summary.text}}"
    },
    "output_key": "save_result",
    "depends_on": ["s2"],
    "execution_location": "client",
    "requires_confirmation": true
  }
]
```

### 5.3 DAG 验证规则

DAG 生成后立即验证，不通过则请求 LLM 修复：

| 验证项 | 规则 |
|--------|------|
| 循环依赖 | DAG 中不存在环 |
| 能力存在性 | `step.capability` 必须在当前能力清单中 |
| 参数完整性 | `params` 中的 `{{key}}` 引用的上游 step 必须存在 |
| 执行位置 | 根据 capability 自动推导 server/client |
| HITL 标记 | cli_execute/skill/mcp_stdio 必须标记 `requires_confirmation` |

### 5.4 拒绝策略

如果 LLM 评估后确认当前能力不足以完成任务，**直接拒绝**，不尝试自己编造不存在的工具：

```
Agent: "抱歉，我当前无法完成绘图任务。
预期能力: 图表绘制工具或 MCP
当前可用: [文件操作、搜索、CLI、数据分析Skill]

你可以考虑安装一个与图表相关的 MCP 工具或 Skill 来获得这个能力。"
```

---

## 6. DAG 执行引擎

### 6.1 执行位置路由

```
select_executor(step):
  if step.capability in [rag, web_search, memory, llm_chat]:
    → 直连执行（server 侧，直接调用）
  elif step.capability in [mcp] and server_type == "sse" or "http":
    → 直连执行（server 侧，HTTP 调用远程 MCP Server）
  elif step.capability in [mcp_stdio, cli_execute, skill_execute]:
    → 委托执行（打包指令 → SSE push → Client 执行 → HTTP 回调）
```

### 6.2 直连执行流程

```
1. 更新 Redis: step_status = "running"
2. 执行能力（同步或 SSE 流式）
3. 验证执行结果
4. 成功 → 写入 dataflow，更新 timeline
5. 失败 → 进入重试逻辑
6. 通知依赖该步骤的其他步骤（如果有并行）
```

### 6.3 委托执行流程

```
1. 更新 Redis: step_status = "dispatched"
2. 构造委托指令包
   {
     "task_id": "t_xxx",
     "step_id": "s3",
     "idempotency_key": "t_xxx_s3_v1",
     "capability": "cli_execute",
     "action": "run_command",
     "params": { "command": "python3 analyze.py" },
     "human_readable": "将要运行命令: python3 analyze.py --input data.csv",
     "requires_confirmation": true
   }
3. 通过 SSE 通道推送指令给 Client
4. 当前的 execution_loop 退出（释放资源）
5. Client 收到指令后：
   a. 如果需要确认 → 弹 HITL 对话框
   b. 用户确认/修改参数后 → 执行
   c. POST /agent/callback 回传结果
6. Server 收到回调 → 恢复 execution_loop
```

### 6.4 验证机制

每步执行完后，按步骤类型做验证：

| 步骤类型 | 验证方式 |
|----------|----------|
| web_search | 结果不为空，与查询关键词相关 |
| llm_chat | 内容非空，无错误信息 |
| cli_execute | 退出码=0，不含 stderr |
| mcp | 返回数据格式匹配工具定义 |
| skill | Skill 执行成功回调 |

验证失败后：

```
第1次失败 → 自动重试（最多 2 次）
第2次失败 → 尝试降级能力（如有 alternative_capability）
第3次失败 → 通知用户：步骤 xxx 失败，原因：xxx
            → 提供选项：跳过/取消整个任务/修改后重试
```

---

## 7. 可观测性与持久化（Redis）

### 7.1 Redis Key 设计

```
Key                                         类型        TTL         说明
─────────────────────────────────────────────────────────────────────────────
task:{task_id}:state                        String     7d          任务整体状态
task:{task_id}:timeline                     List       7d          步骤执行流水账
task:{task_id}:dataflow                     String     7d          步骤间数据传递
task:{task_id}:vars                         Hash       7d          中间变量引用
task:{task_id}:step:{step_id}:status        String     7d          单步状态
```

### 7.2 任务状态字段

```json
{
  "task_id": "t_abc123",
  "user_id": 1000001,
  "session_id": "sess_xyz",
  "status": "running",
  // pending | running | awaiting_client | completed | failed | user_canceled
  "dag_definition": [...],
  "original_input": "用户原始消息",
  "current_step": "s3",
  "error": null,
  "created_at": "2026-06-26T17:00:00+08:00",
  "updated_at": "2026-06-26T17:01:30+08:00"
}
```

### 7.3 Timeline 条目

```json
{
  "step_id": "s1",
  "capability": "web_search",
  "status": "success",
  "started_at": "17:00:05",
  "completed_at": "17:00:08",
  "duration_ms": 3200,
  "params": {"query": "2026 AI papers"},
  "result_summary": "找到5篇相关论文",
  "token_cost": 520,
  "error": null,
  "logs": [
    {"ts": "17:00:05.100", "level": "info", "msg": "开始搜索..."},
    {"ts": "17:00:08.300", "level": "info", "msg": "搜索完成，获取5条结果"}
  ]
}
```

### 7.4 中断恢复

```
AiAgent 重启:
  1. SCAN task:*:state WHERE status = running | awaiting_client
  2. 对每个未完成任务:
     a. 读取 timeline，获取最后一步状态
     b. 如果最后一步是 awaiting_client:
        - 不处理（Client 恢复后会重新回调）
        - 或者重新 dispatch（带幂等 key，由 Client 去重）
     c. 如果最后一步是 running (异常中断):
        - 标记为 failed，进入重试逻辑
        - 用 dataflow 重建上下文后重试
```

### 7.5 幂等性

每次委托给 Client 时携带 `idempotency_key`：

```
idempotency_key = {task_id}_{step_id}_v{retry_version}
```

Client 侧维护已执行的 `idempotency_key` 列表，收到重复 key 时直接返回上次结果。

---

## 8. Human-in-the-Loop

### 8.1 触发条件

| 能力 | 执行位置 | 默认需要确认 | 用户可配置 |
|------|----------|-------------|-----------|
| MCP stdio | Client | 是 | 可设为"始终允许" |
| CLI | Client | 是 | 可设为"始终允许" |
| Skill | Client | 否（按 Skill 声明） | 可覆盖 |
| MCP SSE/HTTP | Server | 否 | 否（远程服务） |

### 8.2 HITL 交互流程

```
Server → Client (SSE): 委托指令
Client 弹出确认框:

┌─────────────────────────────────────────────┐
│ 🔍 AI 想要执行以下操作:                       │
│                                              │
│   操作: 运行命令行                            │
│   命令: python3 analyze.py --input data.csv  │
│   说明: 分析 CSV 数据并生成报告               │
│                                              │
│   ┌──────────────────────────────────┐       │
│   │ python3 analyze.py --input       │       │  ← 用户可编辑
│   │ data.csv                         │       │
│   └──────────────────────────────────┘       │
│                                              │
│   安全风险: 🟡 中 — 会修改本地文件             │
│                                              │
│   [执行]  [修改参数后执行]  [拒绝]  [以后自动允许]
└─────────────────────────────────────────────┘

用户选择:
  - 执行 → Client 执行 → 回调 Server
  - 修改参数后执行 → 用户编辑 → 执行修改版 → 回调
  - 拒绝 → 回调 {status: "user_canceled"}, Server 标记取消
  - 以后自动允许 → 记录到本地白名单，本次执行 → 回调
```

### 8.3 用户拒绝后的处理

```
用户拒绝步骤 s3 (cli_execute)
  → Client 回调 {status: "user_canceled", reason: "用户拒绝"}
  → Server 收到回调
  → 检查 DAG 中 s3 是否有 is_optional 标记
    → 如果是可选步骤 → 跳过，继续
    → 如果是必需步骤 → 通知用户整体任务无法完成
      "步骤'保存文件'被取消，整个任务无法完成。需要重新尝试吗？"
```

---

## 9. 三层渐进式上下文加载

### 9.1 分层策略

```
Layer 0: 快速判别（25-50 tokens，纯逻辑）
  判断: 新会话 vs 延续会话, 问候 vs 指令

Layer 1: 核心上下文（必加载，~200 tokens）
  - 用户偏好（preference 记忆）
  - 关键事实（key_fact 记忆）
  - 当前会话工作记忆

Layer 2: 按需加载（意图驱动，~1000-3000 tokens）
  - 情景记忆: daily_summary（最近3天全量，4-7天只摘要）
  - 情景记忆: topic_summary（匹配当前消息主题）
  - 语义记忆: RAG 检索结果（意图驱动检索）
  - 联网搜索结果（如开启）

Layer 3: 惰性加载（执行时才加载）
  - Skill 内容（S3 下载）
  - MCP 工具定义
  - 完整参考文档
```

### 9.2 无记忆条目时的策略

当用户无情景记忆（从未总结过）时：

```
Layer 1:
  偏好 → 空，跳过
  关键事实 → 空，跳过
  工作记忆 → 从当前对话历史提取

Layer 2:
  情景记忆 → 空，跳过
  RAG 检索 → 正常执行（知识库有内容），成为主要上下文来源
  → 用对话历史优化检索 query（多轮对话时）
  → 第一轮对话直接用用户消息检索
```

---

## 10. 模块结构（新增代码）

```
app/
├── agent/                               # 新增：Agent 编排模块
│   ├── __init__.py
│   ├── models.py                        # 数据模型
│   ├── capability_registry.py           # 能力注册表（实时扫描可用能力）
│   │
│   ├── intent/                          # 意图识别
│   │   ├── __init__.py
│   │   ├── quick_filter.py              # Phase 0: 快速筛选
│   │   ├── intent_scanner.py            # Phase 1: 规则预判
│   │   ├── deep_analyzer.py             # Phase 2: LLM 深度分析
│   │   ├── decision.py                  # Phase 3: 置信度判定
│   │   └── prompts.py                   # LLM Prompt 模板
│   │
│   ├── dag/                             # DAG 生成与执行
│   │   ├── __init__.py
│   │   ├── generator.py                 # DAG 生成（LLM 调用）
│   │   ├── validator.py                 # DAG 验证
│   │   └── executor.py                  # DAG 执行引擎
│   │
│   ├── execution/                       # 步骤执行器
│   │   ├── __init__.py
│   │   ├── direct_executor.py           # Server 侧直连执行器
│   │   ├── delegate_executor.py         # Client 侧委托执行器
│   │   └── verifier.py                  # 步骤验证器
│   │
│   ├── state/                           # Redis 状态管理
│   │   ├── __init__.py
│   │   ├── task_store.py                # 任务状态读写
│   │   ├── timeline.py                  # Timeline 记录
│   │   └── recovery.py                  # 中断恢复
│   │
│   └── context/                         # 上下文加载
│       ├── __init__.py
│       ├── loader.py                    # 三层上下文加载器
│       └── memory_loader.py             # 情景记忆加载
│
├── routers/
│   ├── agent.py                         # 新增：Agent 入口路由
│   ├── llm.py (现有)                    # 保持不变
│   ├── ...
│
└── main.py (现有)                        # 增加 agent.router 注册
```

---

## 11. 新增路由 + 通信协议

### 11.1 Server 端路由

```
POST /guineapig-aiagent/agent/chat
  → Agent 入口，复杂任务走编排，简单任务转发到现有 Pipeline
  → SSE 流式返回执行状态

POST /guineapig-aiagent/agent/callback
  → Client 执行完成后回调
  → 参数: {task_id, step_id, status, result, execution_log}
```

### 11.2 Client 端的 SSE 事件

```
Server → Client (SSE):

# 委托执行指令
data: {"type": "delegate", "task_id": "t_001", "step_id": "s3",
       "idempotency_key": "t_001_s3_v1",
       "capability": "cli_execute",
       "params": {"command": "python3 analyze.py --input data.csv"},
       "requires_confirmation": true,
       "human_readable": "准备运行命令: python3 analyze.py"}

# 执行状态更新
data: {"type": "status", "task_id": "t_001",
       "step_id": "s2", "status": "running"}

data: {"type": "status", "task_id": "t_001",
       "step_id": "s2", "status": "success",
       "result_summary": "搜索完成，获取到5条结果"}

# 计划展示（等待用户确认）
data: {"type": "plan", "task_id": "t_001",
       "plan": [
         {"step": 1, "action": "搜索AI论文", "capability": "联网搜索"},
         {"step": 2, "action": "总结论文", "capability": "LLM"},
         {"step": 3, "action": "保存到文件", "capability": "CLI"}
       ],
       "awaiting_confirmation": true}

# 任务完成
data: {"type": "completed", "task_id": "t_001", "summary": "..."}

# 执行失败
data: {"type": "failed", "task_id": "t_001", "step_id": "s3",
       "error": "..."}
```

---

## 12. 场景走查

### 场景：搜索 AI 论文并保存

```
用户: "在互联网上搜索2026年最新的AI论文，总结后保存到summary.md"

1. 角色认知: "我是 AI Agent"
2. 能力盘点:
   可用: [联网搜索✓, CLI✓, LLM✓]
   不可用: [无]
3. 意图识别:
   Phase 0: "complex"（搜索+保存，多步协作）
   Phase 1: web_search(0.6), cli_execute(0.6)
   Phase 2: LLM 深度分析
     → intent_type: multi_step, confidence: 0.88
     → required_capabilities: [web_search, llm_chat, cli_execute]
     → feasible: true, estimated_steps: 3
   Phase 3: confidence ≥ 0.7, feasible → proceed_to_planning

4. 经验检索:
   情景记忆: 找到 2 次类似的"搜索→总结→保存"模式
   复用上一次的 DAG 结构

5. 能力匹配: ✓ 所有步骤都在能力清单内

6. 计划展示 (SSE push):
   步骤1: 联网搜索 "2026年AI论文" → Server
   步骤2: LLM 总结搜索结果 → Server
   步骤3: CLI 写入文件 summary.md → Client (需确认)

   [用户点击确认]

7. 执行:
   步骤1: Server 联网搜索 → 成功
     → 验证: 返回 5 条结果 ✓
     → 写入 Redis timeline + dataflow
   步骤2: Server LLM 总结搜索结果 → 成功
     → 验证: 内容非空 ✓
     → 写入 Redis timeline + dataflow
   步骤3: 委托 Client → 弹 HITL 确认框
     → 用户确认 → Client 执行 cat > summary.md
     → 回调 {status: "success"}
     → 验证: 退出码 0 ✓

8. 记忆更新:
   → 记录执行经验到情景记忆
   → 提取偏好: "用户喜欢用 summary.md 命名"
   → 标记"搜索→总结→保存"模式

Agent 回复: "已完成！搜索到 5 篇 2026 年 AI 论文，总结已保存到 summary.md"
```

### 场景：能力不足 → 拒绝

```
用户: "把这篇文章翻译成英文"

1. 角色认知: "我是 AI Agent"
2. 能力盘点: [文件操作MCP, 搜索, CLI, RAG, LLM]
   没有翻译专用 MCP 或 Skill
3. 意图识别:
   Phase 2: required_capabilities: [translation_service]
   Phase 3: feasible: false

4. 拒绝: "抱歉，我当前没有安装翻译服务相关的 MCP 工具或 Skill，无法完成翻译任务。你可以考虑添加一个翻译 MCP 服务来获得这个能力。不过如果你只是需要逐句翻译，我可以尝试用 LLM 帮你，但不保证术语准确性。要试试吗？"
```

---

## 13. 实施顺序

```
Phase 1 — 基础能力层
  ├── agent/models.py（数据模型）
  ├── agent/capability_registry.py（能力注册表）
  ├── agent/state/（Redis 状态管理）
  └── agent/context/（上下文加载器）

Phase 2 — 意图识别
  ├── intent/quick_filter.py（Phase 0）
  ├── intent/intent_scanner.py（Phase 1）
  ├── intent/deep_analyzer.py（Phase 2, LLM 调用）
  ├── intent/decision.py（Phase 3）
  └── intent/prompts.py

Phase 3 — DAG 生成与执行（Server 直连部分）
  ├── dag/generator.py
  ├── dag/validator.py
  ├── dag/executor.py（先实现 server 直连步骤执行）
  └── execution/direct_executor.py + verifier.py

Phase 4 — Client 端委托 + HITL
  ├── execution/delegate_executor.py
  ├── routers/agent.py + SSE 通信
  └── Client 端 Task Dispatcher + HITL Dialog

Phase 5 — 中断恢复 + 完整流程
  ├── state/recovery.py
  └── 端到端联调
```
