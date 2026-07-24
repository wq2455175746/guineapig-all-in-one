## 人类沟通的完整要素

```
当一个人要办一件事时，会无意识使用的要素：

1. 我是谁？        → 角色身份
2. 我能干什么？    → 能力边界
3. 用户要干什么？  → 意图目标
4. 我以前做过吗？  → 经验记忆
5. 现在什么情况？  → 环境上下文
6. 我该怎么做？    → 工作流规划
7. 做完了吗？      → 结果验证

```

## 记忆分层

```mermaid
flowchart TD
    subgraph 人类记忆
        SM[语义记忆<br>常识/知识/规则]
        EM[ episodic记忆<br>具体经历/事件]
        WM[工作记忆<br>当前任务临时信息]
    end
    
    subgraph AI系统对应
        KB[知识库<br>RAG/向量数据库]
        EXP[经验存储<br>成功/失败案例]
        ST[对话状态<br>LangGraph State]
    end

```
**记忆和上下文不是可选项，而是必选项。** 没有记忆的系统每次都是"新手"，没有上下文的系统总是"眼盲"。
三层记忆体系
工作记忆（LangGraph State）：当前任务
情景记忆（数据库）：历史经验
语义记忆（知识库）：通用常识

## 完整的记忆和上下文件架构

```mermaid
flowchart TD
    subgraph 输入
        UI[用户输入]
        ENV[环境快照]
    end
    
    subgraph 记忆系统
        SM[语义记忆<br>知识库/RAG]
        EM[情景记忆<br>历史经验]
        WM[工作记忆<br>LangGraph State]
    end
    
    subgraph 上下文感知
        CE[上下文编码器<br>提取相关信息]
    end
    
    subgraph 决策层
        RE[角色识别]
        CI[意图澄清]
        PL[工作流规划]
    end
    
    UI --> CE
    ENV --> CE
    
    SM --> CE
    EM --> CE
    WM --> CE
    
    CE --> RE
    RE --> CI
    CI --> PL
    
    PL --> EX[执行]
    EX --> EM
    EX --> WM

```

## 架构图

```mermaid
flowchart TD
    A[用户输入] --> B[角色识别<br>我是谁？]
    B --> C[能力边界检查<br>我能干什么？]
    
    C -->|能力不足| D[委托给其他Agent]
    D --> A
    
    C -->|能力足够| E[意图理解与澄清<br>用户要干什么？]
    E -->|置信度低| F[主动澄清]
    F --> A
    
    E -->|置信度高| G[DAG生成器<br>编写工作流]
    G --> H[DAG验证器<br>检查正确性]
    
    H -->|无效| I[DAG修复]
    I --> G
    
    H -->|有效| J[执行引擎<br>逐节点执行]
    
    J -->|节点失败| K[错误恢复]
    K -->|可恢复| J
    K -->|不可恢复| L[请求人工介入]
    
    J -->|全部成功| M[结果验证]
    M -->|不完整| N[补救计划]
    N --> J
    
    M -->|完成| O[返回结果]

```


| 维度      | 传统方案            | 你的思路               | 完整方案         |
| ------- | --------------- | ------------------ | ------------ |
| 角色      | 固定system prompt | 动态识别               | + 角色切换       |
| 能力      | 静态工具列表          | 能力边界               | + Subagent路由 |
| 意图      | 单次理解            | 结构化提取              | + 交互式澄清      |
| 规划      | 静态DAG           | 动态生成               | + DAG验证      |
| **记忆**  | **无**           | **显式区分语义/情景/工作记忆** | + 经验学习       |
| **上下文** | **无**           | **环境快照**           | + 动态适应       |
| 执行      | 线性执行            | 逐节点                | + 容错恢复       |
| 验证      | 无               | 完成确认               | + 闭环学习       |

## langgraph 执行DAG图  
```mermaid  
graph TD
    START --> memory_retrieval[记忆检索]
    memory_retrieval --> context_gathering[环境上下文]
    context_gathering --> role_assert[角色断言]
    role_assert --> capability_check{能力检查}
    
    capability_check -->|continue| intent_recognition[意图识别]
    capability_check -->|stop| END
    
    intent_recognition --> plan_generation[计划生成]
    plan_generation --> execution[执行]
    execution --> verification{验证}
    
    verification -->|remediate| remediation[补救]
    verification -->|success| memory_update[记忆更新]
    verification -->|fail| END
    
    remediation --> execution
    memory_update --> END 
```

## 情景记忆类型

| 维度        | daily_summary                             | topic_summary                            | key_fact                                        | preference                                                        |
| --------- | ----------------------------------------- | ---------------------------------------- | ----------------------------------------------- | ----------------------------------------------------------------- |
| **驱动维度**  | 时间                                        | 主题/项目                                    | 用户属性                                            | 用户偏好                                                              |
| **内容性质**  | 叙事性、事件性                                   | 系统性、完整性                                  | 事实性、确定性                                         | 主观性、指导性                                                           |
| **时效性**   | 短期（7-30天）                                 | 长期（项目周期）                                 | 长期（永久）                                          | 长期（永久）                                                            |
| **更新频率**  | 每天                                        | 按需（讨论新进展时）                               | 很少更新                                            | 偶尔更新                                                              |
| **注入优先级** | 中（近期上下文）                                  | 中（相关主题时）                                 | 高（用户画像）                                         | 最高（行为指导）                                                          |
| **淘汰策略**  | 自动过期                                      | 项目结束后归档                                  | 几乎不淘汰                                           | 几乎不淘汰                                                             |
| 定义        | 对用户某一天（或某一段连续对话）的**整体概括**，记录当天聊了什么、发生了什么。 | 按**话题/项目/领域**聚合的记忆，跨时间维度归纳用户在某个主题下的所有讨论。 | 用户表达的**确定性信息**，包括身份、职业、技能、关系、偏好设置等**静态或半静态属性**。 | 用户明确表达的**喜好、风格要求、操作习惯**，通常以"I prefer..."、"下次请..."、"我不喜欢..."等形式出现。 |
