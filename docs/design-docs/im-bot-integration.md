# IM 平台 Bot 集成方案设计

## Metadata
- **Status**: draft
- **Created**: 2026-07-03
- **Package**: guineapig-backend
- **Related Docs**: `docs/ARCHITECTURE.md`, `docs/design-docs/backend-api-design.md`

## Overview

实现多渠道 IM 平台 Bot 集成（优先飞书），使得用户可以将 guineapig 的 AI Agent 能力以 Bot 形式接入飞书、企业微信、钉钉等即时通讯平台。在 IM 聊天框中，用户可以直接与 AI Agent 对话。

## Motivation

- 当前 AI Agent 只能通过 Electron 桌面客户端（WebSocket）交互，入口单一
- 飞书/企微/钉钉是企业用户日常高频使用的 IM 工具，接入后可大幅降低使用门槛
- 统一 Bot 框架设计，方便后续扩展新平台时低成本接入

## Design

### 核心概念

| 概念 | 说明 |
|------|------|
| **Bot Creator** | 系统的 user_id，在 client 中绑定 IM 平台 AppID+AppSecret 的用户 |
| **IM Chatter** | 在 IM 端与 Bot 对话的实际用户，无需在系统中有账号 |
| **Bot 框架** | 抽象 Bot 接口，每种 IM 平台一个实现 |
| **BotMessage** | 平台无关的统一消息结构 |

### 身份映射模型

一个 Bot Creator（系统 user_id）绑定一个 IM 平台应用。该应用（机器人）可以被任意 IM 用户对话，所有对话归属到 Bot Creator 的 user_id 下管理。

```
Bot Creator (系统 user_id=1)     ← 在 client 绑定飞书 App
    │
    └─ Feishu Bot (应用机器人)
        ├─ IM用户A 私聊  → conversation: user_id=1, source='feishu', ext_chat_id='oc_a1'
        ├─ IM用户B 私聊  → conversation: user_id=1, source='feishu', ext_chat_id='oc_b2'
        └─ 群聊 @Bot    → conversation: user_id=1, source='feishu', ext_chat_id='oc_c3'
```

### 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                    guineapig-backend                            │
│                                                                 │
│  ┌─────────────┐   ┌─────────────────────────────────────────┐  │
│  │ 绑定管理 API  │   │  BotManager                              │  │
│  │  /bot/bind   │   │  ┌──────────┐  ┌──────────┐  ┌───────┐ │  │
│  │  /bot/unbind │   │  │FeishuBot │  │WecomBot  │  │DingBot│ │  │
│  │  /bot/info   │   │  └────┬─────┘  └─────┬────┘  └──┬────┘ │  │
│  └──────┬──────┘   │       │               │          │       │  │
│         │          │       └───────────────┴──────────┘       │  │
│         ▼          │                  │                        │  │
│  ┌──────────────┐  │         normalizeMessage()               │  │
│  │chat_bot_     │  │                  │                        │  │
│  │binding 表    │  │                  ▼                        │  │
│  └──────────────┘  │          BotMessage (统一结构)            │  │
│                    │                  │                        │  │
│                    │                  ▼                        │  │
│  ┌──────────────┐  │  findOrCreateExtConversation()           │  │
│  │chat_conver-  │◄─┤  storeMessage() → chat_messages          │  │
│  │sations 表    │  │  callAiAgentSync() → 获取回复             │  │
│  │chat_messages │  │  sendMessage() → IM平台 API               │  │
│  └──────────────┘  └─────────────────────────────────────────┘  │
│                                                                 │
│                         │                                       │
│                         ▼                                       │
│              ┌──────────────────┐                               │
│              │ guineapig-aiagent│                               │
│              │  /llm/chat/stream│                               │
│              └──────────────────┘                               │
└─────────────────────────────────────────────────────────────────┘
```

### 完整消息流

```
[IM用户] 在飞书输入 "你好"
    │
    ▼ Feishu Server 推送 WebSocket 事件
    │ { sender.open_id, chat_id="oc_xxx", text="你好", tenant_key }
    │
    ▼ FeishuBot.client.handleMessage()
    │
    ├─ ① 查 chat_bot_binding
    │    WHERE platform='feishu' AND tenant_key=?
    │    → 得到 bot_creator 的 user_id
    │
    ├─ ② 查找/创建会话
    │    findOrCreateExtConversation(
    │      user_id=bot_creator, source='feishu', ext_chat_id='oc_xxx'
    │    ) → conversation_id
    │
    ├─ ③ 存储用户消息
    │    INSERT INTO chat_messages (conversation_id, role='user', content='你好')
    │
    ├─ ④ 调用 AiAgent
    │    a. buildLLMMessages(ctx, conversation) → 加载历史
    │    b. POST /guineapig-aiagent/llm/chat/stream
    │    c. 收集完整 SSE 回复
    │    d. 存储助手消息
    │
    └─ ⑤ Feishu SendMessage API 回复用户
```

### 数据模型

#### 1. 新增：`chat_bot_binding` 表

```sql
CREATE TABLE `chat_bot_binding` (
  `id`           bigint UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '主键id',
  `user_id`      bigint NOT NULL COMMENT '系统用户ID（Bot Creator）',
  `platform`     VARCHAR(32) NOT NULL COMMENT '平台标识: feishu-飞书, wechat-企业微信, dingtalk-钉钉',
  `app_id`       VARCHAR(128) NOT NULL COMMENT '平台应用AppID',
  `app_secret`   VARCHAR(512) NOT NULL COMMENT 'AppSecret（RSA加密存储）',
  `tenant_key`   VARCHAR(128) DEFAULT '' COMMENT '平台租户标识（飞书tenant_key/企微corp_id）',
  `bot_status`   TINYINT NOT NULL DEFAULT 0 COMMENT '连接状态: 0-未连接, 1-已连接, 2-连接失败',
  `bot_name`     VARCHAR(128) DEFAULT '' COMMENT '机器人别名',
  `extra_config` JSON NULL COMMENT '平台扩展配置（如AI模型ID等）',
  `description`  VARCHAR(512) DEFAULT '' COMMENT '绑定备注',
  `created_by`   VARCHAR(255) DEFAULT NULL,
  `created_at`   timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`   timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY `uk_user_platform` (`user_id`, `platform`),
  INDEX `idx_platform_tenant` (`platform`, `tenant_key`),
  INDEX `idx_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='IM平台Bot绑定表';
```

关键查询：
- **消息路由**：`SELECT user_id FROM chat_bot_binding WHERE platform=? AND tenant_key=?` — 根据 IM 事件中的租户标识找到 Bot Creator
- **绑定管理**：`SELECT * FROM chat_bot_binding WHERE user_id=? AND platform=?` — 查某个用户的绑定

#### 2. 修改：`chat_conversations` 表（加 2 列）

```sql
ALTER TABLE `chat_conversations`
  ADD COLUMN `source`      VARCHAR(32)  NOT NULL DEFAULT 'client'
    COMMENT '消息来源: client-客户端, feishu-飞书, wechat-企业微信, dingtalk-钉钉',
  ADD COLUMN `ext_chat_id` VARCHAR(128) NOT NULL DEFAULT ''
    COMMENT '外部IM平台会话ID（用于防重复创建会话）',
  ADD INDEX `idx_source_extchat` (`source`, `ext_chat_id`);
```

关键查询：
- **查找 IM 会话**：`SELECT id FROM chat_conversations WHERE source='feishu' AND ext_chat_id=?`
- **过滤客户端会话**：现有 `ListConversations` 可以默认追加 `AND source='client'`（或加参数控制）

#### 3. 不改动：`chat_messages` 表

完全复用，AiAgent 调用链路不变。

### Bot 接口设计

```go
// Bot 接口 — 每种 IM 平台一个实现
type Bot interface {
    Platform() string                                            // "feishu" | "wechat" | "dingtalk"
    Start(ctx context.Context, config BotConfig) error            // 建立连接
    Stop() error                                                  // 断开连接
    SendMessage(ctx context.Context, extChatID string, reply *BotReply) error  // 发消息到 IM
    EventChan() <-chan *BotMessage                                // 消息事件通道
    IsRunning() bool
}

type BotConfig struct {
    AppID     string
    AppSecret string
    BotUserID int64          // bot_creator 的 user_id
    Platform  string
    ExtraJSON string         // 各平台私有配置
}

// BotMessage 平台无关的统一消息
type BotMessage struct {
    Platform   string
    ExtChatID  string         // IM 平台会话 ID
    ExtSender  string         // IM 平台发送者 ID
    Content    string         // 文本内容
    Raw        any            // 原始事件（透传）
}

type BotReply struct {
    Text string
}
```

### API 设计

```
# Bot 绑定管理（统一的，通过 platform 区分）
POST   /api/v1/bot/bind        # {platform, app_id, app_secret, bot_name?, extra_config?}
POST   /api/v1/bot/unbind      # {platform}
GET    /api/v1/bot/info        # ?platform=feishu (不传返回全部)

# 内部 Bot 消息处理不走 API，Bot 模块直接调用 service 层
```

Bind 请求处理流程：
1. 校验：同一 user_id + platform 不能重复绑定
2. 如果已有绑定，更新 app_secret 后重建连接
3. 加密存储 app_secret
4. 用 AppID + AppSecret 调用 IM 平台接口获取 tenant_key
5. 启动 Bot 实例（建立 WebSocket 长连接）
6. 返回绑定信息

### BotManager 设计

```go
type BotManager struct {
    mu      sync.RWMutex
    bots    map[string]Bot   // key: "{platform}:{user_id}"
    msgCh   chan *BotMessage // 全局消息通道
}

func (m *BotManager) StartBot(config BotConfig) error    // 启动一个 Bot
func (m *BotManager) StopBot(platform string, userID int64) error  // 停止一个 Bot
func (m *BotManager) GetBot(platform string, userID int64) Bot     // 获取 Bot 实例
func (m *BotManager) Run(ctx context.Context)              // 启动消息分发循环

// 内部消息分发
func (m *BotManager) dispatchLoop(ctx context.Context) {
    for msg := range m.msgCh {
        switch msg.Platform {
        case "feishu":
            // 1. 处理消息 → 存储 → 调 AiAgent → 回复
        }
    }
}
```

### 厂商 Bot 实现

每种 IM 平台都实现 `Bot` 接口：

**FeishuBot**：使用飞书 SDK（`larksuite/oapi-sdk-go/v3`）
- `Start()`: 初始化 SDK Client + WebSocket 事件订阅
- 事件处理：`im.message.receive_v1` → 转为 `BotMessage`
- `SendMessage()`: `POST /open-apis/im/v1/messages` 发送文本

**WecomBot / DingtalkBot**：后续扩展，只需新增一个 .go 文件实现 Bot 接口

### 目录结构

```
guineapig-backend/internal/
├── bot/
│   ├── types.go                  # Bot 接口 + BotMessage + BotConfig + BotReply
│   ├── manager.go                # BotManager 多租户连接管理
│   ├── registry.go               # 平台工厂注册
│   ├── feishu.go                 # FeishuBot 实现
│   ├── wecom.go                  # 占位
│   └── dingtalk.go               # 占位
├── model/
│   └── chat_bot_binding.go       # GORM 模型
├── request/
│   └── chat_bot_binding.go       # 请求结构体
├── response/
│   └── chat_bot_binding.go       # 响应结构体
├── service/
│   ├── chat_bot_binding.go       # 绑定/解绑/查询业务逻辑
│   └── chat_sync.go              # 同步调用 AiAgent（新增）
└── router/
    ├── bot/
    │   └── bind.go               # 绑定管理 API 路由
    └── router.go                 # 注册路由 + 启动 BotManager
```

### Client 端交互

#### 入口位置

在 `SystemSettingsPage.vue`（系统设置页面）新增一个 Tab **「消息渠道」**，用于管理 IM 平台 Bot 的绑定。

```
SystemSettingsPage.vue
├── Tab: 本地日志 (LocalLogTab)
├── Tab: 指标 (MetricsTab)
└── Tab: 消息渠道 (BotChannelTab)    ← 新增
```

#### BotChannelTab 交互流程

**状态 1 — 未绑定**
```
┌─────────────────────────────────────────────┐
│  [消息渠道]                                   │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │  + 添加渠道                             │  │  ← 卡片/按钮
│  └────────────────────────────────────────┘  │
│                                              │
│  (点击"添加渠道" → 弹出绑定对话框)              │
└─────────────────────────────────────────────┘
```

**绑定对话框**
```
┌─ 绑定 IM 平台 ──────────────────────────────┐
│                                              │
│  平台:  [飞书 ▼]   ← Select (feishu/wechat/) │
│                     (dingtalk, 暂只做feishu)  │
│  AppID:  [________________________]          │
│  AppSecret: [________________________]       │
│  备注:  [________________________]           │
│                                              │
│  [取消]                    [确认绑定]         │
└──────────────────────────────────────────────┘
```

**状态 2 — 已绑定**
```
┌─────────────────────────────────────────────┐
│  [消息渠道]                                   │
│                                              │
│  ┌── 飞书 ───────────────────────────────┐   │
│  │  AppID: cli_xxxx                       │   │
│  │  状态: ● 已连接                         │   │
│  │  备注: 我的飞书 Bot                      │   │
│  │                                         │   │
│  │  [解除绑定]  [重新绑定]                   │   │
│  └─────────────────────────────────────────┘   │
│                                              │
│  ┌── 企业微信 ──────────────────────────┐   │
│  │  暂未绑定  [+ 绑定]                    │   │
│  └─────────────────────────────────────────┘   │
│  (灰色框，只显示"暂未绑定")                     │
└─────────────────────────────────────────────┘
```

#### 页面组件设计

| 文件 | 说明 |
|------|------|
| `BotChannelTab.vue` | **新建** — 消息渠道管理标签页 |
| `BotChannelDialog.vue` | **新建** — 绑定/重新绑定对话框 |

不改动 `SystemSettingsPage.vue` 以外的现有文件。

#### BotChannelTab API 调用

```typescript
// API 接口（与 backend 一致）
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:6880'
const userId = localStorage.getItem('user_id') || ''

// 查询绑定信息
async function fetchBindInfo(): Promise<BotBindingInfo[]> {
  const res = await fetch(`${API_BASE_URL}/api/v1/bot/info?user_id=${userId}`)
  const data = await res.json()
  return data.result || []
}

// 绑定
async function bindBot(params: { platform: string; app_id: string; app_secret: string; bot_name?: string }) {
  const res = await fetch(`${API_BASE_URL}/api/v1/bot/bind`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...params, user_id: userId }),
  })
  return await res.json()
}

// 解绑
async function unbindBot(platform: string) {
  const res = await fetch(`${API_BASE_URL}/api/v1/bot/unbind`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ platform, user_id: userId }),
  })
  return await res.json()
}
```

#### 数据模型（前端 TypeScript）

```typescript
interface BotBindingInfo {
  id: number
  user_id: number
  platform: 'feishu' | 'wechat' | 'dingtalk'
  app_id: string
  bot_name: string
  bot_status: number     // 0-未连接, 1-已连接, 2-连接失败
  tenant_key: string
  description: string
  created_at: string
}
```

#### 视觉规范

全部使用 PrimeVue 组件，遵循现有 overlay 页面的视觉风格：
- 背景色 `#f5f5f5`
- 卡片背景 `#fff`
- 圆角 10px
- 状态标签用 Tag 组件（绿色=已连接，灰色=未连接，红色=连接失败）

## Implementation Plan

### Phase 1 — 数据模型 + 绑定 API + FeishuBot 连接 + Client 绑定页面

#### Backend
1. SQL DDL: `chat_bot_binding` 表
2. SQL migration: `chat_conversations` 加 `source` + `ext_chat_id`
3. `model/chat_bot_binding.go` — GORM 模型 + CRUD
4. `request/chat_bot_binding.go` — 请求结构体
5. `response/chat_bot_binding.go` — 响应结构体
6. `bot/types.go` — Bot 接口定义
7. `bot/manager.go` — BotManager
8. `bot/feishu.go` — FeishuBot 实现（WebSocket 连接跑通）
9. `service/chat_bot_binding.go` — 绑定业务逻辑
10. `service/chat_sync.go` — 同步调用 AiAgent
11. `router/bot/bind.go` — 绑定管理 API
12. `router/router.go` — 注册路由 + 启动 BotManager

#### Client
13. `BotChannelTab.vue` — **新建** 消息渠道管理标签页
14. `BotChannelDialog.vue` — **新建** 绑定对话框
15. 修改 `SystemSettingsPage.vue` — 新增「消息渠道」Tab

### Phase 2 — 消息处理完整链路

1. FeishuBot 消息事件 → normalizeMessage() → BotMessage
2. dispatchLoop → findOrCreateExtConversation()
3. 存消息 → 调 AiAgent → 存回复
4. Feishu SendMessage 回复用户
5. 私聊场景跑通验证

### Phase 3 — 生产化

1. 多租户管理
2. 断线重连 + 心跳
3. 错误处理 + 日志
4. 群聊 @bot 触发
5. 速率限制

### Phase 4 — 新平台扩展

1. WecomBot 实现
2. DingtalkBot 实现

## Risks / Trade-offs

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 飞书 WebSocket 断连 | Bot 无法收发消息 | 自动重连机制，指数退避 |
| 绑定时 AppSecret 明文传输 | 凭据泄露 | 前端 JSEncrypt 公钥加密 + 后端私钥解密存储（参照现有 API Key 处理） |
| 同步调用 AiAgent 超时 | 飞书用户等待过长 | 设置超时 60s，超时后回复"请求超时请重试" |
| 多平台多租户资源消耗 | 大量 WebSocket 长连接 | 每个 Bot 单 goroutine，连接断开自动清理 |

## Open Questions

- [ ] `ListConversations` 是否需要默认过滤 `source='client'`？还是加一个参数让客户端选择？
- [ ] 是否需要给飞书会话设置自动标题（如"飞书-张三"）？还是统一叫"飞书对话"？
- [ ] 群聊场景中，Bot 回复是否需要 @提及发送者？

## Review Notes
