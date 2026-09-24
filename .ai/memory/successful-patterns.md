# Successful Patterns

## SP-001: Echo Router Group 注册模式
```go
// internal/router/user/list_user.go
func init() {
    router.AddGetRouter("/api/v1/users", listUser)
}

// internal/router/router.go
func Register(e *echo.Echo) {
    // init() 自动注册所有路由
}
```
**适用**：backend 所有 API 端点

## SP-002: GORM Model 定义模式
```go
type User struct {
    ID        uint      `gorm:"primarykey" json:"id"`
    CreatedAt time.Time `json:"created_at"`
    UpdatedAt time.Time `json:"updated_at"`
    Email     string    `gorm:"uniqueIndex;not null" json:"email"`
}
```
**适用**：backend 所有数据库模型

## SP-003: Request/Response 分离
```
internal/request/user.go   -> CreateUserReq, UpdateUserReq
internal/response/user.go  -> UserResp, UserListResp
```
**适用**：backend API 契约定义

## SP-004: Plugin 初始化模式
```go
// pkg/plugin/plugin.go
func Init(conf *config.Config, log *zap.Logger) {
    initDB(conf, log)
    initRedis(conf, log)
}
// main.go 中调用 plugin.Init(conf, log)
```
**适用**：backend 外部服务初始化

## SP-005: FastAPI Router 组织模式
```python
# api/v1/tasks.py
router = APIRouter(prefix="/api/v1/tasks")

@router.post("/")
async def create_task(request: TaskCreateRequest):
    ...
```
**适用**：aiagent API 端点

## SP-006: 中间件链式注册
```go
e.Use(middleware.RequestID())
e.Use(middleware.Logger())
e.Use(middleware.Recover())
e.Use(middleware.CORS())
```
**适用**：backend Echo 中间件

## SP-007: RSA 非对称加密工具模式
```go
// pkg/utils/rsa.go
func Encrypt(plaintext string, publicKey []byte) (string, error)
func Decrypt(ciphertext string, privateKey []byte) (string, error)
func GenerateKeyPair(bits int) (privateKey, publicKey []byte, err error)
```
- 前端用 JSEncrypt（公钥加密），后端用 crypto/rsa（私钥解密）
- 密钥文件放在各 package 的 `config/` 或 `public/` 目录下
- 列表 API 返回 `***` 掩码，编辑时前端不自动回填密钥
- **适用**：敏感字段（API Key、密码等）的前后端安全传输

## SP-008: GORM 选择性字段更新（map 模式）
```go
func (m *UserAiModel) Update(id uint, updates map[string]any) error {
    return plugin.GetDB(nil).Model(&UserAiModel{}).
        Where("id = ?", id).
        Updates(updates).Error
}
```
- 使用 `map[string]any` 替代 struct 传递给 GORM `Updates()`
- 避免 struct 零值字段被 GORM 忽略的问题（status=0, api_key="" 等）
- 可空字段（如 api_key）条件性包含，非空时才加入 map
- **适用**：任何需要精确控制哪些字段被 UPDATE 的场景

## SP-009: 前端 Service 层封装模式
```typescript
// src/api/aimodel.ts
export const aimodelService = {
  async list(params?: AiModelQuery): Promise<AiModelListResp> { ... },
  async create(data: AiModelCreateReq): Promise<void> { ... },
  async update(id: number, data: AiModelUpdateReq): Promise<void> { ... },
  async remove(id: number): Promise<void> { ... },
}
```
- 每个资源一个 service 文件，API 调用集中管理
- 使用 `native fetch()` 而非 axios，保持轻量
- 响应式数据通过 store (Pinia) 管理，与 service 分离
- 错误处理在 service 层统一包装
- **适用**：guineapig-client 前端所有 API 调用

## SP-010: 字段掩码脱敏模式
```go
// 后端在 List/Get 接口返回前对敏感字段脱敏
if resp.ApiKey != "" {
    resp.ApiKey = "***"
}
```
- 列表/查询 API 对敏感字段（api_key, password, secret）进行掩码
- 编辑/详情 API 同样返回掩码，前端不自动回填真实值
- 仅在创建/更新 API 接收真实值
- 前端编辑表单显示掩码 + "更换密钥"选项区分新建和编辑场景
- **适用**：所有敏感数据展示场景

## SP-011: WebSocket + SSE 代理模式
```go
// Go 后端代理 Python SSE 流到客户端 WebSocket
func (h *Hub) proxyAiAgentStream(ctx context.Context, ...) {
    // 1. 从 HTTP Response.Body 读取 SSE 事件
    // 2. 解析 event/data 字段
    // 3. 按事件类型转发 WSEnvelope 到客户端
    // 4. 闭包跟踪状态（如 commandsForwardedAsEvent）
}
```
- Go 后端作为 SSE 消费者 + WebSocket 生产者，桥接 AiAgent 和客户端
- 使用闭包变量跟踪流状态（commandsForwardedAsEvent 防重标志）
- 不同事件类型映射到不同 WSEnvelope.EventType
- **适用**：Go 后端代理 Python AI Agent 流式输出的所有场景

## SP-012: BLPOP/LPUSH 实现 Pipeline Session 恢复
```python
# pipeline_session.py
def _wait_for_command_result(self, cmd_id: str, timeout: int = 300):
    result = self.redis.blpop(f"cmd:{cmd_id}", timeout=timeout)
    return json.loads(result[1])

# 命令执行完成时：
self.redis.lpush(f"cmd:{cmd_id}", json.dumps(result))
```
- BLPOP 阻塞等待命令执行结果，不需要轮询或 Pub/Sub
- LPUSH 写入结果后 BLPOP 立即返回，延迟极低
- 比 Pub/Sub 更简单：无需管理 channel 订阅和取消
- 自带超时机制，防止死等
- **适用**：aiagent 中需要等待异步操作结果的场景

## SP-013: RAG Embedding 三阶段流水线模式
```python
# 分块 -> 向量化 -> 写入
chunks = TextChunker().chunk(document_text)
vectors = embedding_model.encode(chunks)
milvus_client.insert(collection, vectors)
```
- 每个阶段独立可测试，可替换
- TextChunker 支持多种策略（按段落、按 token 数、按语义边界）
- embedding 模型可热插拔
- Milvus 批量写入优于逐条写入
- 配合 WebSocket 事件展示实时进度
- **适用**：知识库文件处理、文档嵌入、大规模文本向量化

## SP-014: SSE 事件类型转发映射模式
```
Python SSE 事件类型 -> Go WSEnvelope 映射:
  "chunk"      -> WSEnvelope.EventType = "chat.chunk"
  "message"    -> WSEnvelope.EventType = "chat.message"
  "commands"   -> WSEnvelope.EventType = "chat.commands"
  "tool_call"  -> WSEnvelope.EventType = "chat.tool_call"
  "tool_result"-> WSEnvelope.EventType = "chat.tool_result"
  "done"       -> WSEnvelope.EventType = "chat.done"
```
- Go 后端不解析业务数据，只做事件类型映射和透传
- 客户端根据 EventType 分发到不同 handler
- 新增 SSE 事件类型只需要在映射表加一项
- **适用**：所有后端代理流式 AI 响应的场景

## SP-015: ParentMessageId 消息树模型
```typescript
interface ChatMessage {
  id: string;
  parentMessageId?: string;  // 指向父消息，形成消息树
  conversationId: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
}
```
- 每条消息有唯一 ID，通过 parentMessageId 串联多轮对话
- 支持分支对话（同一 parent 有多个 child）
- 适用于 multi-message 架构：每个 ReAct 轮次是一条独立消息
- 消息树拓扑便于前端 UI 展示
- **适用**：多轮对话、分支对话、ReAct Agent 消息展示

## SP-016: Agent 意图分类 Pipeline（QuickFilter + 阶段路由）
```python
# agent.py _run_intent_pipeline
filter_result = QuickFilter().classify(query)  # Phase 0: TRIVIAL/SIMPLE/COMPLEX

if filter_result.intent_type == "TRIVIAL":
    return await _direct_llm_stream(query, ...)  # 短路，跳过后续阶段

capabilities = await CapabilityRegistry.scan(session_id)  # 仅非 TRIVIAL 执行
scanner_result = IntentScanner(intent_type, query).scan(capabilities)  # Phase 1
deep_result = await DeepAnalyzer(query, ...).analyze(...)  # Phase 2
decision = IntentDecision(intent_type, scanner_result, deep_result).decide()  # Phase 3
dag = await DAGGenerator(...).generate(decision)  # DAG 生成
async for event in DAGExecutionEngine(dag, ...).execute(...):  # DAG 执行
    yield event
```
- TRIVIAL 在最前短路，IMCOMPLEXLLM 调用开销
- 每个 Phase 独立可测试、可跳过
- DAG 执行引擎产生 SSE 事件流，与 `_direct_llm_stream()` 格式一致
- **适用**：所有 Agent 对话请求路由

## SP-017: SSE 流式 Short-circuit 模式（_direct_llm_stream）
```python
async def _direct_llm_stream(query: str, ...) -> AsyncGenerator[StreamEvent, None]:
    stream = client.chat.completions.create(
        model=model, messages=messages, stream=True
    )
    full_content = ""
    for chunk in stream:
        content = chunk.choices[0].delta.content or ""
        full_content += content
        yield StreamEvent(type=StreamEventType.CHUNK, data={"content": content})

    yield StreamEvent(type=StreamEventType.DONE, data={"content": full_content})
    # 在 generator 外部返 report_metrietrics 和 ...token 统计
```
- 跳过整个Pipeline直接调用 LLM 流式 API
- Generator 内部只 yield，不处理 metrics 等副作用（避免 GeneratorExit）
- metrics report 由外层调用者负责
- **适用**：TRIVIAL 路径、fallback 降级路径、`/llm/chat/stream` 端点

## SP-018: DAG 执行引擎模式（拓扑排序 + 逐步执行）
```python
class DAGExecutionEngine:
    PARAM_REF_PATTERN = re.compile(r"\{\{(\w+)\.(\w+)\}\}")  # 步骤间参数引用

    async def execute(self, ...) -> AsyncGenerator[StreamEvent, None]:
        # 1. 拓扑排序确定执行顺序
        # 2. 按深度分组，同深度步骤可并行
        # 3. 每步执行前解析参数引用（{{step_id.output_key}}）
        # 4. 执行后缓存结果到 step_results
        # 5. 支持重试和降级（retry_policy）
```
- `PARAM_REF_PATTERN` 支持 `{{step_id.output_key}}` 和 `{{step_id.output}}` 两种引用
- 数据流解析在执行时动态解析，支持链式依赖
- 重试策略由 DAGStep.retry_policy 定义（max_retries, delay）
- **适用**：多步骤 Agent 任务编排（web_search→rag→llm_chat）

## SP-019: OTel Metrics UPSERT + Redis TTL 模式
```python
# Python 侧写入 Redis（HINCRBY）
redis.hincrby(f"otel:metrics:{stat_date}:{user_id}", "input_token", count)
redis.expire(f"otel:metrics:{stat_date}:{user_id}", 172800)  # 2 天 TTL

# Go 侧同步到 MySQL（UPSERT）
INSERT INTO chat_otel (stat_date, user_id, name, value)
VALUES (?, ?, ?, ?)
ON DUPLICATE KEY UPDATE value = JSON_SET(value, '$.input_token',
    COALESCE(JSON_EXTRACT(value, '$.input_token'), 0) + VALUES(value->>'$.input_token'))
```
- Python HINCRBY 原子累加，Go UPSERT 也原子累加（JSON_SET），双重保障不丢数据
- Redis 2 天 TTL 自动过期清理，无需手动 Del()
- 一次同步遍历所有 metric fields，批量提交
- **适用**：所有跨服务指标上报场景

## SP-020: Backend Asynq 任务队列（Scheduler + Server）
```go
// Scheduler: 定时触发
scheduler := asynq.NewScheduler(redisClient, nil)
scheduler.Register("@every 5m", asynq.NewTask(OtelSyncTaskType, nil))

// Server: Worker 消费
server := asynq.NewServer(redisClient, asynq.Config{Concurrency: 1})
server.RunAsync()  // 非阻塞启动，与 Echo 共存
server.RegisterHandler(OtelSyncTaskType, otelSyncHandler)
```
- `RunAsync()` 非阻塞启动，与 Echo HTTP 服务器共存于同一进程
- Scheduler 替代 goroutine + time.Ticker，分布式友好
- Asynq 自带重试、超时、任务去重、延迟任务等特性
- **适用**：所有定时同步、延迟处理、后台任务场景

## SP-021: Token 计数启发式算法

```python
def _estimate_tokens(text: str) -> int:
    """Character-level token estimation heuristic."""
    if not text:
        return 0
    cjk_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or '\u3000' <= c <= '\u303f')
    other_count = len(text) - cjk_count
    return math.ceil(cjk_count / 1.5) + math.ceil(other_count / 4)
```

- CJK 字符（中文）约 1 token / 1.5 chars
- 非 CJK 字符（英文、数字等）约 1 token / 4 chars
- 比 tiktoken 计数更轻量（避免额外包依赖）
- 误差通常 < 20%，用于指标统计足够
- **适用**：LLM 调用前后 token 数统计（input_token / output_token）

## SP-022: 跨渠道用户聊天配置缓存模式（Redis Hash）
```go
// 保存 (Client chat 时)
func SetUserChatConfig(ctx, userID, modelID, webSearchEnabled, agentModeEnabled) error
// 读取 (Bot 消息时)
func GetUserChatConfig(ctx, userID) (modelID, webSearchEnabled, agentModeEnabled)
```
- Redis Key: `chat:config:{user_id}` Hash，无 TTL（每次 client chat 更新覆盖）
- 保存使用 `HSet`，读取使用 `HGetAll`
- Redis 不可用时返回零值，调用方降级到默认配置（不阻塞）
- **适用**：Client 端配置需要在 Feishu Bot 等外部渠道复用的场景

## SP-023: 同步方式处理 IM Bot 消息模式
```go
// SyncChatMessage 同步方式处理 Bot 消息
func SyncChatMessage(ctx, userID, platform, extChatID, content string) (string, error)
```
- 非流式：收集完整 SSE 流回复后一次性返回（Bot 平台不支持流式）
- 三步走：存储用户消息 → 调用 LLM → 存储助手消息（同一个 conversation）
- conversation 按 source + ext_chat_id 自动创建/复用
- 调用 `GetUserChatConfig` 读取用户最新模型选择
- 只调用 `/llm/chat/stream`，不调用 `/agent/chat/stream`（MCP skill 需要 client 端执行）
- **适用**：飞书/企微/钉钉等 IM Bot 消息处理

## SP-024: Bot Manager 多平台注册模式
```go
type Bot interface {
    Platform() string
    SendMessage(ctx, userID, content string) error
}

type BotManager struct {
    bots map[string]Bot  // platform -> Bot
}

func (m *BotManager) RegisterBot(platform string, bot Bot)
func (m *BotManager) GetBot(platform string) (Bot, bool)
```
- 通过 Bot interface 抽象多平台差异（Feishu/WeChat/DingTalk）
- BotManager 提供统一的注册和查找入口
- handleBotMessage 根据 platform 查找对应 Bot 实例
- `StartupBots()` 在启动时从数据库加载已配置 Bot 并注册
- **适用**：多 IM 平台集成的管理和消息分发

## SP-025: Bot 消息令牌桶限流模式
```go
// 每个 Bot 平台独立限流器
limiter := ratelimit.NewTokenBucket(cfg.RateLimiter.BotQps, cfg.RateLimiter.BotQps)
if !limiter.Allow() {
    return "消息太频繁，请稍后再试", nil
}
```
- 令牌桶算法，支持突发流量（容量 = QPS）
- 通过 `config.yaml` 的 `rateLimiter.botQps` 配置（默认 5 QPS）
- 按平台维度限流（不是按 user 或 conversation）
- **适用**：IM Bot 消息频率控制，防止被平台限流封禁

## SP-026: Docker 多阶段构建模式
```dockerfile
# Backend Go: builder → runtime
FROM golang:1.24-alpine AS builder
RUN CGO_ENABLED=0 GOOS=linux go build -o /app/server .
FROM alpine:3.19
COPY --from=builder /app/server /app/
HEALTHCHECK --interval=30s CMD wget -qO- http://localhost:6880/health || exit 1

# AiAgent Python: pip → slim runtime
FROM python:3.13-slim AS builder
RUN pip install --no-cache-dir -r requirements.txt -t /install
FROM python:3.13-slim
COPY --from=builder /install /usr/local/lib/python3.13/site-packages

# Ops-web Vue: node build → nginx
FROM node:22-alpine AS build
RUN npm run build
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
```
- Go 应用使用 `CGO_ENABLED=0` 静态编译，alpine 运行时最小化
- Python 使用 pip install 到独立目录再拷贝，保留 builder 层缓存
- Vue 前端使用 nginx:alpine 提供静态文件服务，暴露 80 端口
- Backend 必须添加 `/health` 端点（前置 Auth 中间件）供 HEALTHCHECK 使用
- **适用**：所有服务的容器化构建

## SP-027: Helm Chart ConfigMap 挂载配置模式
```yaml
# values.yaml
configmap:
  enabled: true
  name: app-cm
  files:
    config.yaml:
      key: ${ENV_VAR_FROM_SECRET}

# deployment.yaml
volumes:
  - name: config-volume
    configMap:
      name: app-cm
      items:
        - key: config.yaml
          path: config.yaml
volumeMounts:
  - name: config-volume
    mountPath: /app/config.yaml
    subPath: config.yaml
    readOnly: true
```
- ConfigMap 中嵌入配置文件（config.yaml/nginx.conf），使用 `${ENV_VAR}` 引用 Secret
- Secret 通过 `envFrom` + `secretRef` 注入环境变量，ConfigMap 运行时解析
- `checksum/config` 注解在 ConfigMap 变更时触发 Pod 滚动更新
- **适用**：K8s 部署中所有需要挂载配置文件的场景

## SP-028: Backend Health 端点前置中间件模式
```go
// 在 Auth 中间件之前注册健康检查端点
e.GET("/health", healthHandler)
e.GET("/api/v1/health", healthHandler)
e.Use(authMiddleware)  // Auth 之后的所有路由需要鉴权
```
- 健康检查端点必须在 Auth 中间件之前注册，否则 K8s probe / Docker HEALTHCHECK 需要 Token
- 返回 JSON `{"status":"ok","time":<unix_timestamp>}`
- `prometheus.io/scrape` 注解指向 `/api/v1/health`（通过 service annotation 配置）
- **适用**：所有需要容器编排（K8s/Docker Compose）的 Go 服务
## SP-029: HMAC 会话 Token 鉴权模式
```go
// pkg/auth/token.go
// 格式: base64url(userID:expiryUnix).base64url(hmac-sha256(secret, payload))
token, _ := IssueUserToken(secret, userID, ttl)
userID, err := ParseUserToken(secret, token)  // 常量时间比较 + 过期校验
```
- 身份仅从 token 推导，绝不信任客户端可控 header
- 三套共享密钥分权：`/api/v1/*` 用 `X-User-Token`（会话）、`/admin/api/v1/*` 用 `X-Admin-Token`（共享）、`/inner/api/v1/*` 用 `X-Inner-Token`（服务间）
- 客户端可控的 user_id 一律由中间件以 token 身份覆盖（BindRequester/CurrentUserID）
- **适用**：backend 所有需鉴权路由 + WS 握手（?token= 验签）

## SP-030: ZIP 安全解压工具模式（zip_utils.extract_zip_safe）
```python
def extract_zip_safe(zf, extract_dir, max_total_size=100MB, max_file_count=1000):
    # 1. 剥离公共顶层目录
    # 2. 校验原始条目名 + 剥离后路径（拒绝 .. 绝对路径 反斜杠）
    # 3. 流式写入并统计实际字节（防压缩炸弹）
    # 4. 超限抛 UnsafeZipError
```
- 双重校验：原始条目名 + normpath 后前缀校验（防 prefix-mismatch 如 /x/out_evil）
- 共享给多个解压入口，错误类型子类化 RuntimeError 保持调用方 except 契约
- **适用**：skill/zip 上传解压等所有不可信 zip 处理

## SP-031: 子代理驱动开发（subagent-driven development）
```
每任务: dispatch implementer(带 brief 文件) → implementer 实现+测试+提交
      → dispatch task-reviewer(读 diff 包) → spec+quality 双判
      → fix loop: 最多5轮，每轮 resume implementer + scoped re-review
全部完成后: final whole-branch review → 一次 fix wave 补集成缺口
```
- 每个 implementer 用独立 brief 文件（task-N-brief.md）作需求唯一来源，不污染上下文
- 审查 diff 用 review-package 脚本生成单文件（commit list + stat + 全文 diff）
- 最终整体审查专门抓跨任务集成缺口（服务间 token、跨包契约、部署接线）
- **适用**：任何多任务大计划的执行

## SP-032: LLM 客户端复用 + 有界重试模式
```python
# app/core/llm_clients.py
get_llm_client() / get_async_llm_client()  # 锁保护的进程内缓存, keyed by (sync, api_key, base_url, timeout)
call_with_retry(fn, *args)                 # 有界重试 + 指数退避
# 不重试的确定性错误: AuthenticationError/PermissionDeniedError/BadRequestError/NotFoundError
```
- 每调用新建 OpenAI client 浪费连接池；缓存后复用
- 流式调用只重试 create，不重放已消费 chunk
- 同步重试的 time.sleep 只在线程上下文（to_thread/线程池）执行，不阻塞事件循环
- **适用**：所有 LLM 调用点

## SP-033: Milvus 客户端线程本地缓存模式
```python
# app/core/milvus_clients.py
threading.local()  # 每个线程独立缓存 MilvusClient, keyed by (host, port, db_name)
```
- MilvusClient 非线程安全，per-thread 缓存安全 by construction 且避免连接抖动
- 多 collection 搜索用 asyncio.gather + to_thread 并发，每个 worker 线程持有自己的 client
- **适用**：RAG 检索/写入等线程池调用的场景

## SP-034: WS 连接生命周期上下文模式
```go
func newClientStreamContext(client *ClientConnection) context.Context
// 连接关闭(done)时自动取消 → 流式 goroutine 随之退出, 不泄漏
```
- 所有 spawned goroutine（streamAssistantReply/handleCommandResult/handleAgentSend）都从连接生命周期 context 派生
- cancel() 始终 defer，watch goroutine 经 ctx.Done() 退出
- 终态 DB 写用独立的 30s writeCtx，不被 WS 断连取消（避免消息卡在 streaming）
- **适用**：WS 连接相关的所有后台任务

## SP-035: Electron AudioWorklet data: URL 加载模式
```typescript
// src/audio/recorder-worklet.js (原始源码, vite ?raw 导入)
import workletSrc from '../audio/recorder-worklet.js?raw'
const url = 'data:text/javascript;base64,' + btoa(workletSrc)  // 隔离在 getRecorderWorkletUrl()
await ctx.audioWorklet.addModule(url)
```
- 生产 file:// 下 blob: 和 file: 均被 CORS 拦截，data: URL 实测唯一可用
- worklet 拷贝后 transfer（不持有引擎 buffer），keepalive return true，无输入通道不 post
- **适用**：Electron 中所有 AudioWorklet 场景

## SP-036: 共享 HTTP client 连接池模式
```go
// pkg/utils/httpclient.go
var sharedHTTPTransport = &http.Transport{MaxIdleConns: 100, MaxIdleConnsPerHost: 10, ...}
func NewHTTPClient(timeout time.Duration) *http.Client
```
- 消除 10+ 处 `&http.Client{}` 每调用新建（丢失连接池/DNS 缓存）
- 保持 per-call timeout，流式请求用大 timeout
- **适用**：backend 所有出站 HTTP（chat/agent/skill/file/aimodel）

## SP-037: N+1 批量查询模式（WHERE id IN）
```go
// model/res_files.go
func (*ResFiles) FindByIds(ctx, ids []uint) ([]ResFile, error) {
    return db.Where("id IN ? AND deleted_at IS NULL", ids).Find(&items).Error
}
```
- 替代逐条 FindById 循环（chat_stream.resolveRagContext 每轮 N+1）
- 缺失/已删行正确排除（deleted_at IS NULL）
- List 方法 PageSize=0 时硬上限 MaxListLimit(1000)
- **适用**：所有逐条主键查询可批量化的场景

## SP-038: 对 LLM 非确定性输出做三层容错（标识符/格式/循环）
**做法**：凡是 LLM 输出参与路由或执行的内容（capability 名、commands 块），一律假设输出不可靠，做三层防护：
1. **prompt 展示确切标识符并强制原样使用**（capability 名 `mcp_amap`、`<commands>` 格式样例）
2. **消费端容错解析/归一化**（validator token 重叠归一化 `amap_mcp→mcp_amap`；parse_commands 平衡括号扫描容忍缺闭合标签）
3. **硬性兜底**（命令轮次 Redis 上限+客户端相同命令签名去重）
**效果**：MCP 旅行规划、命令执行两个此前"时好时坏"的功能稳定可用；LLM 行为波动不再导致功能失效
**适用**：所有依赖 LLM 输出但必须可靠执行的功能

## SP-039: 客户端配置页面模式（Overlay 设置页 → IPC → sanitize+persist+内存即时生效）
**做法**：把主进程常量/配置（如命令白名单）暴露为可页面维护的配置：
1. 主进程注册 `get-xxx` / `set-xxx` IPC handler；set 侧做 **sanitize**（trim/小写/去重/拒非法字符/上限）→ **persist**（写 userData JSON）→ **更新内存状态立即生效**（无需重启）；空/非法输入回退默认值防失控
2. preload 用 `ipcRenderer.invoke` 暴露同名方法
3. `vite-env.d.ts` 扩展 `Window.electronAPI` 类型（IPC 三步缺一即运行时报错）
4. UI 复用 Overlay 系统设置页 Tab + 输入框组件（每行一项 + 保存/恢复默认 + Toast 反馈）
**效果**：命令白名单（`DEFAULT_ALLOWED_COMMAND_BINARIES`）现在可由用户在 系统设置→命令白名单 直接维护，配置落盘 userData/command-whitelist.json 并立即生效
**适用**：任何"内置常量需要用户可维护"的场景（白名单/阈值/开关列表），主进程配置修改即时生效优于"改文件+重启"
