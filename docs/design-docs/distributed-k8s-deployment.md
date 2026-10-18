# 分布式 K8s 部署与最小影响升级方案

面向 guineapig 的 `backend` / `aiagent` / `ops-web` 三个组件。

## 1. 目标与约束

- **目标**：backend 与 aiagent 均可多副本部署；滚动升级时对在线用户的干扰降到最低（普通聊天连接断开后客户端自动重连并从 DB 恢复，**执行中的 Agent 任务允许丢失**）。
- **约束**：**只改 Helm/K8s 配置，不改任何 Go/Python 应用代码。**

## 2. 为什么需要特殊处理

client↔backend 是 WebSocket 长连接，backend↔aiagent 是 HTTP SSE + 多次控制 POST。这些长连接把**执行状态绑在了具体进程上**：

- backend `Hub`（`internal/service/chat_hub.go`）与 `aiAgentConns` 是**进程内内存态**。
- aiagent `AgentEventManager._sessions`（`app/agent/event_manager.py`）是**进程内 class dict**。

一旦多副本，状态跨进程不可见，必须靠**连接/路由粘性**保证「同一会话落在同一 Pod」。本方案用 K8s 原生能力实现，无需改代码。

## 3. 拓扑

```
client ──WS──> Ingress(nginx) ──> backend Svc(ClusterIP, sessionAffinity: None) ──> backend Pods ×N
                                        │   WS 为单 TCP 连接，kube-proxy 建立时钉一次 Pod
                                        │   HTTP: SSE(下行) + 控制 POST(上行)
                                        ▼
                                 aiagent Svc(ClientIP 亲和) ──> aiagent Pods ×M
ops-web (无状态) ──> Ingress ──> ops-web Pods ×N
```

## 4. 关键决策

| # | 决策 | 理由 |
|---|------|------|
| 1 | **aiagent Service `sessionAffinity: ClientIP`** | 同一条 WS 触发的 SSE 流与后续控制 POST（delegate-result / confirm / cancel）**同源于一个 backend Pod 的 IP**，ClientIP 亲和把它们钉到同一 aiagent Pod，命中内存 `_sessions`。这是 aiagent 敢多副本的关键。 |
| 2 | backend Service 保持 `sessionAffinity: None` | WS 是单 TCP 连接，天然钉 Pod；HTTP API 无状态。无需亲和。 |
| 3 | 滚动策略 `maxUnavailable: 0` + `maxSurge: 1` | 先拉起新 Pod、容量不降，逐 Pod 替换，把断连影响限制在单个 Pod。 |
| 4 | `preStop: sleep 8` | 让 k8s 先从 endpoints 摘除该 Pod，再发 SIGTERM，避免新连接打到正在退出的 Pod。 |
| 5 | `terminationGracePeriodSeconds`：backend 60s / aiagent 120s | 覆盖 preStop + 收尾；aiagent 放宽以容纳较长的 SSE。 |
| 6 | PDB `minAvailable` | 保护节点驱逐/维护等自愿中断。 |
| 7 | Ingress `proxy-read-timeout` / `proxy-send-timeout: 3600` | backend 心跳每 54s，超时必须远大于它；3600s 保证长连接稳定。nginx-ingress 默认支持 Upgrade 透传。 |

## 5. 各 Chart 改动

### backend (`deployment/backend/helm`)
- `templates/deployment.yaml`：新增 `lifecycle.preStop` 渲染（受 `.Values.deployment.container.lifecycle` 控制）。
- `templates/pdb.yaml`：**新增**，受 `.Values.podDisruptionBudget` 控制。
- `templates/ingress.yaml`：新增 `proxy-send-timeout` 注解。
- `values.yaml`：`terminationGracePeriodSeconds: 60`、`lifecycle`、`strategy 0/1`、`podDisruptionBudget`。
- `values-{dev,pre,test,release}.yaml`：`replicaCount`（dev 1→2）、`terminationGracePeriodSeconds: 60`、`strategy 0/1`、`podDisruptionBudget`；ingress 启用的环境 `proxyReadTimeout/proxySendTimeout: '3600'`。

### aiagent (`deployment/aiagent/helm`)
同 backend，另加：
- `values.yaml` 与所有环境：`service.sessionAffinity: ClientIP`。
- `terminationGracePeriodSeconds: 120`。
- `podDisruptionBudget`。

### ops-web
纯前端静态资源，无状态，多副本无额外要求。

## 6. 环境参数速查

| 环境 | backend 副本 | aiagent 副本 | backend PDB | aiagent PDB | ingress |
|------|------|------|------|------|------|
| dev | 2 | 2 | minAvailable 1 | minAvailable 1 | 关闭 |
| pre | 2 | 2 | minAvailable 1 | minAvailable 1 | 开启 |
| test | 2 | 2 | minAvailable 1 | minAvailable 1 | 关闭 |
| release | 3 | 3 | minAvailable 2 | minAvailable 2 | 开启 |

## 7. 升级流程

1. **先升 aiagent**：新副本 Ready 后旧副本按 `maxSurge:1/maxUnavailable:0` 逐个替换。ClientIP 亲和确保会话不跨 Pod；仅该 Pod 上正在执行的 Agent 任务会失败。
2. **再升 backend**：逐 Pod 替换，断连的客户端指数退避重连到其他 Pod，普通聊天从 DB 恢复历史。

> 一次只滚动一个组件，避免两个组件同时抖动导致客户端连续重连。

## 8. 已知缺口（超出「只改 Helm」范围）

1. **执行中的 Agent 任务在升级/断连时会丢失**：无优雅 drain（主动发 WS 1001 关闭帧）与任务断点续跑。彻底解决需将 `Hub`/`AgentEventManager` 状态外置（Redis）并实现可恢复执行，属较大重构。
2. **backend 多副本的重复副作用**（`main.go`）：
   - Asynq Scheduler（`main.go`）：每个副本都会注册定时任务 → `otel:sync` / `memory:summarize` 会**重复入队**。
     - **注意**：asynq 里分布式的是 **Server（worker）**（共享队列，任务只在一个节点执行一次）；**Scheduler 没有 leader 选举或分布式锁**。它写 Redis 心跳只是给 Web UI 展示，不代表协调——多实例会各自入队。
     - **已修复（代码）**：给两个定时任务加 `asynq.Unique(ttl)`（`main.go`），在**入队时**用 Redis 锁去重，保留多副本 HA、又保证全局只执行一次。TTL 取 `4m` / `11h`（必须 < 调度周期）。
   - `StartupBots()`（`main.go`）每个副本都会启动 IM Bot → 每副本各建一条飞书长连接，且绑定/解绑只在处理请求的副本生效。
     - **飞书长连接是"集群模式、不广播"**：同一事件只随机投给一个 client，所以**不会**重复回复；真正的问题是**每副本独立的内存 `BotManager`**（连接数放大、解绑只停本副本、状态不一致）。
     - **已修复（代码 + Helm）**：新增 `RUN_BOTS` 开关 + 专用 Bot Deployment（详见第 9 节）。
3. **客户端重连无 jitter**（客户端代码，不在范围）：靠 `maxSurge:1` 限制单次波及面缓解惊群。

## 9. 其它已修复的分布式问题

除 Scheduler、IM Bot 外，本次一并修复的分布式问题：

1. **aiagent PVC 访问模式 `ReadWriteOnce` → `ReadWriteMany`**（`deployment/aiagent/helm/values-*.yaml`）
   多副本共享同一个 PVC，RWO 在块存储下会导致第二个 Pod 无法挂载；`DATA_DIR=/app/data` 存的是 skills/task/rag/asr 文件，多副本必须共享，改用 RWX（NFS 天然支持）。

2. **Snowflake 节点 ID 从 Pod 派生**（`pkg/utils/snowflake.go`）
   原来所有副本硬编码 `node=1`，同一毫秒跨副本会生成相同 ID（用于建用户 `Id`，PK 冲突）。现改为 `hash(K8S_POD_NAME | hostname) % 1024`，保证各副本节点 ID 不同。测试见 `pkg/utils/snowflake_test.go`。

3. **IM Bot 单实例化**（`config.RunBots` + `internal/service/bot_control.go` + Helm `deployment-bots.yaml`）
   - `RUN_BOTS`（环境变量）控制本实例是否启动 IM Bot 长连接，默认 `true`。
   - Helm `bots.enabled=true` 时：主 Deployment `RUN_BOTS=false`；另建 1 副本的 `{name}-bots` Deployment（`RUN_BOTS=true`，`strategy: Recreate`）承载全部长连接。
   - **绑定/解绑跨副本生效**：任意副本处理 bind/unbind 后通过 Redis Pub/Sub（`bot:control`）广播指令，Bot 实例订阅并本地启停，解决"解绑只停本副本"。`bots.enabled=false` 时无专用实例，主 Deployment 自身 `RUN_BOTS=true`（单实例兼容）。

## 10. 验证

```bash
helm lint ./deployment/backend/helm -f ./deployment/backend/helm/values-dev.yaml
helm lint ./deployment/aiagent/helm -f ./deployment/aiagent/helm/values-dev.yaml

helm template ./deployment/aiagent/helm -f ./deployment/aiagent/helm/values-pre.yaml | \
  grep -E "PodDisruptionBudget|sessionAffinity|preStop|proxy-(read|send)-timeout"
```

升级前额外确认：
- aiagent Pod 之间**无 SNAT 到节点 IP**（保持 Pod IP 为亲和键；即便 SNAT 也只影响分布均衡，不影响正确性）。
- Ingress `/api/v1/chat/ws` 路径未被 `rewrite-target` 破坏。
