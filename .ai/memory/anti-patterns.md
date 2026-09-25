# Anti-Patterns

## AP-001: Backend 直接调用 AI 模型
**错误**：在 guineapig-backend 中 `import openai` 或直接调用 ASR/TTS 库
**正确**：通过 HTTP/gRPC 调用 guineapig-aiagent 的 API
**原因**：层级分离 - backend 只做业务编排，AI 能力集中在 aiagent

## AP-002: 跨 package 直接 import 内部模块
**错误**：`guineapig-client` import `guineapig-backend/internal/model`
**正确**：通过 API 契约（HTTP/WebSocket）通信，不共享代码
**原因**：monorepo 中每个 package 是独立部署单元

## AP-003: 跳过 ASR 直接传文本给 LLM
**错误**：client 端侧做 ASR 后只传文本，跳过音频存档
**正确**：音频文件始终上传 S3 存档，ASR 在服务端执行
**原因**：音频存档用于后续分析和模型优化

## AP-004: 配置硬编码
**错误**：数据库连接串、API Key 直接写死在代码中
**正确**：使用 .env 文件 + config.yaml，backend 使用 Viper 的 ${ENV_VAR} 机制
**原因**：安全性和环境可移植性

## AP-005: 不检查任务状态直接操作
**错误**：aiagent 拿到任务直接执行，不检查任务是否已被处理
**正确**：先查询 MySQL 任务状态，幂等处理
**原因**：防止重复处理和状态不一致

## AP-006: 日志不带 request_id
**错误**：`log.Info("user login")` 缺少追踪信息
**正确**：使用 `logger.WithContext(ctx).Info(...)` 自动带上 request_id
**原因**：分布式系统中需要 request_id 串联调用链

## AP-007: download_file_from_s3 传入目录路径而非文件路径
**错误**：调用 `download_file_from_s3(object_key, directory_path)` 传入目录路径
**正确**：使用 `download_file_from_s3(object_key, os.path.join(directory_path, filename))` 传入完整文件路径
**原因**：函数内部使用 `os.path.dirname` 创建父目录，然后直接写入 `local_path`。传入目录路径时触发 "[Errno 21] Is a directory" 错误

## AP-008: GORM Updates 使用 struct 导致零值字段被跳过
**错误**：`db.Model(&obj).Updates(&UserAiModel{Status: 0})` — status=0 的 int8 零值被 GORM 忽略
**正确**：使用 `db.Model(&obj).Updates(map[string]any{"status": 0})` — map 方式保留所有字段
**原因**：GORM 的 Updates() 对 struct 和 map 处理不同：struct 时零值（0, "", false）被视为"未设置"而跳过，map 则保留所有键值对。这是 GORM 的已知行为，必须在所有需要更新零值字段的地方使用 map

## AP-009: List API 返回真实 API Key 导致前端编辑表单覆盖
**错误**：List API 返回 `api_key: "sk-xxx..."`，前端编辑时回填到表单，提交时将 `"***"` 写回数据库覆盖真实密钥
**正确**：List/Get API 对敏感字段返回 `"***"` 掩码，编辑时前端提供 "换一个" 选项，提交时不发送 api_key 或仅在用户明确修改时发送
**原因**：前端使用掩码作为表单初始值提交时，服务端无法区分"用户未修改"和"用户有意设为 ***"

## AP-010: Go SSE reader 在首个 done 事件退出循环
**错误**：Go 后端读取 SSE 流时，遇到 `data: [DONE]` 就 break 读取循环
```go
scanner := bufio.NewScanner(body)
for scanner.Scan() {
    if strings.Contains(scanner.Text(), "[DONE]") {
        break  // ❌ 首个 done 就退出，破坏 ReAct 多轮
    }
}
```
**正确**：区分"流结束"和"轮次结束"。遇到 done 事件只标记轮次完成，等待 stream_end 事件才退出
**原因**：Python ReAct loop 每轮输出一个 done 事件，Go 后端需要支持多轮 done。SSE 连接应该在最终 stream_end 事件或 context 取消时关闭，而不是在首个 done 就关闭

## AP-011: Vue 普通变量在异步 WebSocket 流程中用作唯一会话标识
**错误**：使用 `let currentConvId`（非响应式普通变量）保存 WebSocket 会话的唯一 conversation ID，在异步流程中被其他事件处理函数重置
```typescript
let currentConvId: number = 0  // ❌ 普通变量，异步流程中不可靠
```
**正确**：使用 `let pendingConvId` 在命令执行前提前保存 ID，或将关键状态改为 Vue `ref()` 响应式变量，确保异步流程中状态一致性
**原因**：SSE 流的 done 事件在异步命令执行完成前就重置了 currentConvId，导致后续需要该 ID 时获取不到。普通变量在事件驱动架构中无法保证跨异步操作的一致性

## AP-012: 单 SSE 流中拼接多轮 ReAct 输出到同一条消息
**错误**：Python ReAct loop 的所有轮次输出到同一个 SSE 流，Go 后端透传到客户端后全部追加到同一 chat message
```
SSE Stream: [round1_chunks] [commands1] [done1] [round2_chunks] [commands2] [done2] ...
                      全部拼接到同一个 message.content
```
**正确**：每个 ReAct 轮次生成独立消息，每条消息有唯一 message_id，通过 parentMessageId 连接
**原因**：单消息多轮拼接导致：(1) 命令对话框重复触发（无法判断哪些命令已被处理）(2) UI 展示异常（大量内容堆积到一条消息）(3) 无法按轮次回溯或分支

## AP-013: 单轮 SSE 流中 commands 既作为事件转发又嵌入 done payload
**错误**：commands 在轮次中以 SSE 事件形式单独转发，又在 done 事件的 data payload 中重复携带，导致客户端收到两份相同命令
**正确**：commands 仅在轮次中以事件形式转发一次。done 事件 payload 中使用布尔标志表示"该轮有命令"而非重复嵌入命令内容。Go 后端用闭包变量 commandsForwardedAsEvent 做防重
**原因**：客户端收到重复 commands 后触发多次命令对话框，用户交互体验严重受损。防重标志需要放在 Go 后端（透传层），而不是在 Python 生成端修改

## AP-014: sync for 遍历 async generator
**错误**：对 async generator 使用同步 `for` 迭代，导致 TypeError
```python
for event in pipeline.run_and_yield(query, ...):  # ❌ TypeError: 'async_generator' object is not iterable
    yield event
```
**正确**：使用 `async for` 迭代
```python
async for event in pipeline.run_and_yield(query, ...):  # ✅
    yield event
```
**原因**：async generator 是异步可迭代对象，需要 `async for`。Python 在生成器函数中如果没有任何 await 表达式，会将其视为普通生成器而非异步生成器。流式端点中 SSE writer 和 generator consumer 都必须是异步的

## AP-015: Python finally 块中 yield 触发 GeneratorExit
**错误**：在 async generator 的 finally 块中执行 yield，generator 被 GC 回收时抛出异常
```python
try:
    async for event in some_generator():
        yield event
finally:
    yield StreamEvent(type="error", ...)  # ❌ GeneratorExit 在 finally 中 yield
```
**正确**：在外部调用侧处理异常和 metrics，generator 内部不处理副作用
```python
# Generator 只用 yield，外部负责后续处理
async for event in some_generator():
    yield event
# 在这里报告 metrics 等（不在 generator 内部）
```
**原因**：Python 生成器被 GC/close() 关闭时会向生成器内部抛出 GeneratorExit 异常，进入任何 finally 块。如果在 finally 中 yield，会抛出 RuntimeError("generator ignored GeneratorExit")。流式 generator 应在 generator 外部（调用方）处理 metrics 上报等副作用

## AP-016: session_id 格式不匹配导致跨语言 conversation_id 丢失
**错误**：Go backend 传递给 Python aiagent 的 session_id 格式与 aiagent 期望解析格式不一致
```python
# Python 期望某种格式解析 conversation_id
# Go 传递的是另一种格式的数字字符串
# 结果: conversation_id 始终为 0
```
**正确**：在 aiagent 端使用统一解析函数，兼容多种可能的 session_id 格式
```python
def _parse_conversation_id(session_id: str) -> int:
    # 支持多种格式
    ...
```
**原因**：Go 和 Python 对 session_id 格式的约定不一致时，没有统一解析入口。修复方式是在 aiagent 端做兼容性解析，因为 aiagent 是消费者，需要适应上游的各种格式

## AP-017: ZIP 解压不校验成员路径（ZIP SLIP）
**错误**：解压 zip 时 `os.path.join(extract_dir, member_path)` 直接写入，恶意条目 `../../etc/cron.d/evil` 逃逸解压目录
```python
target_path = os.path.join(extract_dir, member_path)  # ❌ 可穿越
open(target_path, "wb").write(...)
```
**正确**：`normpath(join(extract_dir, member_path))` 后校验 `startswith(extract_dir + os.sep)`，拒绝绝对路径与 `..` 段，限制总大小与条目数
**原因**：skill 来自用户上传的 zip，未校验即任意文件写入，RCE 风险

## AP-018: S3 上传设置 public-read ACL 或剥除预签名签名
**错误**：`put_object(..., ACL="public-read")` 让用户语音等隐私对象公开；`get_object_url` 里 `split("?")[0]` 把预签名签名剥掉变成永久公开链接
**正确**：上传默认私有；返回完整预签名 URL（含 X-Amz-Signature）
**原因**：用户 TTS/ASR 音频是隐私数据，公开可下载违反合规

## AP-019: 加鉴权后不接线跨服务调用方
**错误**：aiagent 加了 fail-closed 鉴权，但 backend 的 9 个调用点仍不带 token，整个运行时链路静默 401
**正确**：加鉴权的同时，grep 所有调用方并接线共享 token（AttachAiAgentAuth / X-Inner-Token），docker-compose 共享值
**原因**：服务间鉴权是双向契约，只改接收端不改调用端 = 全系统不可用，且单元测试无法发现

## AP-020: 信任客户端可控的身份头（X-User-Id）
**错误**：auth 中间件信任 `X-User-Id` header 且只查用户存在，任何人可伪造任意用户身份
```go
userID, _ := strconv.Atoi(c.Request().Header.Get("X-User-Id"))  // ❌ 不可信
```
**正确**：身份从可验证 token（HMAC/JWT）推导，常量时间比较；客户端输入的 user_id 一律以 token 身份覆盖
**原因**：header 完全由客户端控制，等于无鉴权

## AP-021: 对客户端提供的 URL 发送解密后的密钥（SSRF + 解密预言机）
**错误**：aimodel/test 把 RSA 解密的 api_key 明文发给客户端提供的 apiUrl，攻击者指向自己服务器即可拿到任意密文的明文，且 apiUrl 任意可 SSRF 内网
**正确**：apiUrl 加入网络 allowlist（未配置仅允许回环），DB 模型用登记 api_url，请求绑定 context + 超时
**原因**：服务端拿私钥解密后发给攻击者控制的地址 = 私钥保护的密钥全量泄漏

## AP-022: WebSocket Send channel 被 close 后仍有 goroutine 发送
**错误**：`close(client.Send)` 后后台 goroutine 继续 `client.Send <- data`，send on closed channel panic 崩溃整个进程
```go
close(client.Send)  // ❌ 仍有 writer 在发送
```
**正确**：Send 永不 close，用 done chan + sync.Once 的 Close()，sendToClient select done 丢弃，goroutine 全加 recover()
**原因**：WS 断连后流式回复 goroutine 仍在运行，panic 无 recover 覆盖 Echo 中间件，直接进程崩溃

## AP-023: async 路由中直接调用同步阻塞 LLM
**错误**：async SSE 路由里直接 `client.chat.completions.create(...)`（同步），一次 LLM 往返阻塞整个事件循环
**正确**：asyncio.to_thread 包装同步调用，或改用 AsyncOpenAI；所有外部调用显式 timeout
**原因**：并发下单个慢 LLM 请求冻结所有其他请求

## AP-024: Fire-and-forget asyncio.create_task 无引用无异常处理
**错误**：`asyncio.create_task(_run_embedding_async(params))` 丢弃引用，异常被静默吞掉，任务可能被 GC
**正确**：保留 task 引用（set），done 回调记录异常，服务关闭时取消
**原因**：后台任务失败无感知，资源泄漏

## AP-025: 业务错误与内部错误混用一个响应函数导致用户可读信息被屏蔽
**错误**：ResponseServerError 一律返回通用"系统错误"，导致"无权操作该会话"等业务错误用户不可见
**正确**：BizError(code,msg) 走用户可见分支（errors.As），仅真实内部错误（SQL/路径）走通用错误+服务端日志
**原因**：安全修复（不泄漏内部细节）与可用性（保留业务提示）必须同时满足

## AP-026: CJS 库打进 ESM 主进程包却不进 external
**错误**：client 主进程为 ESM（`"type": "module"`），引入 CJS 库 `adm-zip` 且未加入 vite `rollupOptions.external`，rolldown 将其内联后把 `require("fs")` 编译为 `__require("fs")` 代理
```js
// dist/electron/index.js 运行时报错
var fsystem = __require("fs")  // ❌ ESM 作用域无 require → App threw an error during load
```
**正确**：所有 CJS/原生依赖（adm-zip/archiver/node-machine-id/@modelcontextprotocol/sdk）都进 `external`，运行时由 Electron 以真实 CJS 加载；**按子路径导入的包（`@modelcontextprotocol/sdk/client/index.js` 等）external 必须用正则 `^/包名/`（如 `/^@modelcontextprotocol\/sdk/`），精确字符串 `'@modelcontextprotocol/sdk'` 匹配不到子路径 import，包仍会被内联**
**原因**：rolldown 对打进 ESM bundle 的 CJS 代码里的 Node 内建 require 无法转换，只能在运行时抛错

## AP-033: 命令白名单/参数校验按"理想输入"设计，误伤真实用法
**错误**：SAFE_ARG_TOKEN 只允许 ASCII 安全字符，LLM 给中文用户生成 `open 日历` 被拒（'命令参数包含非法字符: 日历'）；isAllowedBinary 用精确字符串匹配，`/usr/bin/open` 这类路径限定二进制被拒（'命令不在白名单内'）
```ts
const SAFE_ARG_TOKEN = /^[A-Za-z0-9_.:/+=-]+$/          // ❌ 拒掉非 ASCII
isAllowedBinary(bin) = whitelist.includes(bin)           // ❌ 拒掉带路径的二进制
```
**正确**：参数集 = ASCII 安全字符 ∪ 任意非 ASCII（`/^(?:[A-Za-z0-9_./:@+=~-]|[\u{0080}-\u{10FFFF}])+$/u`），仍拒绝 shell 元字符；二进制白名单按 basename 匹配（`/usr/bin/open` → basename `open` 命中即放行），白名单项本身存命令名
**原因**：白名单是"防注入"不是"防真实用法"，把合法输入（中文参数/路径二进制）拒掉会直接破坏功能，且 LLM 输出天然贴近真实用户语言

## AP-027: CORS 白名单只配 .local 域名忽略 localhost
**错误**：backend `corsHosts` 只写 `http://guineapig-client.local:5174`，而 dev 时 vite 在 5173 被占后顺延到 5174，origin 是 `http://localhost:5174`，预检没有 Access-Control-Allow-Origin
**正确**：白名单同时覆盖 `.local` 与 `localhost` 两种访问方式（localhost:5173/5174），并提醒改动后需重启 backend
**原因**：Echo CORS 中间件对未匹配 origin 不返回 CORS 头，浏览器直接拦截预检，表现成 `ERR_FAILED` 而非 403，容易误判为网络故障

## AP-028: 加鉴权中间件后不把 token 配置进各环境 .env
**错误**：aiagent 加了 fail-closed 的 AdminTokenAuthMiddleware，但本地 .env 没有 ADMIN_TOKEN（默认空），backend→aiagent 全部 401，运行时链路静默断掉
```bash
# aiagent .env 缺这一行
# ADMIN_TOKEN=...
```
**正确**：加鉴权的同时，把 ADMIN_TOKEN 写进所有运行环境（dev .env / docker-compose / prod），且 backend 与 aiagent 值保持一致
**原因**：fail-closed 设计安全，但漏配 token 时所有非白名单接口 401，且单元测试发现不了（单测不经过真实网络链路）

## AP-029: 把不确定的 LLM 输出直接当精确键匹配
**错误**：DAG 执行用 LLM 生成的 capability 名做精确匹配/校验，LLM 看不到确切标识符就只能猜，猜错（amap_mcp / mcp_amap_maps_weather）就整个 DAG 被丢或 URL 匹配失败
**正确**：①prompt 展示确切标识符并强制原样使用；②消费端做模糊归一化（token 重叠 → 真实名）；③能注入的连接信息（mcp_url 等）走服务端匹配注入而非依赖 LLM 输出
**原因**：LLM 输出天然不稳定，凡是非确定性输出参与路由/匹配，必须有归一化兜底，否则行为随 LLM 心情波动，表现为"时好时坏"难排查

## AP-030: 多个 Origin 白名单各自维护、漏配 localhost
**错误**：backend 同时有 CORS AllowOrigins（config.yaml）和 gorilla CheckOrigin（websocket.go）两套白名单，都只配 .local 域名，vite 顺延端口后 dev 以 localhost 访问，CORS 预检和 WS 握手先后失败（ERR_FAILED / 403）
**正确**：所有 Origin 白名单统一考虑 .local 与 localhost 两种访问方式；新增 host 时同步检查 CORS、CheckOrigin 两处；配置类改动（config.yaml）需重启服务生效
**原因**：Origin 校验分散在多层，漏一处就出现诡异症状（预检失败表现为 ERR_FAILED、WS 表现为 403），容易误判为网络/鉴权问题

## AP-031: 解析 LLM 输出时用"强制格式"正则而非容错解析
**错误**：parse_commands 用 `<commands>\s*(\[...\])\s*</commands>` 严格正则，LLM 漏掉 `</commands>` 闭合标签就整体解析失败——命令块当纯文本显示、done 事件不带 commands、确认框不弹出
**正确**：对 LLM 输出的结构化标签做容错解析：平衡括号扫描提取 JSON 数组（不依赖闭合标签存在），正确处理字符串内嵌套数组；并为每种容错场景写回归测试
**原因**：LLM 输出格式天然不稳定（漏闭合标签、大小写、多余空白），严格正则把"格式偏差"当成"无内容"，功能静默失效且难排查

## AP-032: 允许 LLM 无限循环执行而不设轮次上限
**错误**：handleCommandResult 把命令执行结果注入 system prompt 并提示"可以生成新命令继续执行"，无轮次上限；LLM 对一次性任务也反复生成相同命令，确认框无限循环（日志 conv_id=83 连续 4 轮 messages 递增）
**正确**：后端 Redis 计数器限制命令轮次（MaxCommandRounds=3），达上限丢弃 commands 兜底；prompt 明确任务完成即总结、标明剩余轮次；客户端对相同命令签名去重；用户新消息清零计数
**原因**：任何"LLM 驱动的循环动作"都必须有硬性轮次上限——prompt 约束是软性的，LLM 可能忽略；三层（后端硬限+prompt 引导+客户端去重）才能防住

## AP-034: 更新内置默认配置却忽略已落盘的持久化副本
**错误**：改代码 `DEFAULT_ALLOWED_COMMAND_BINARIES` 追加 mkdir/cp 以为修复生效，但 `loadCommandWhitelist` 优先读 `userData/command-whitelist.json`（首次启动自动生成的默认副本），本机仍走旧清单，`命令不在白名单内: mkdir` 依旧报错（"修了没生效"）
```ts
// ❌ 只改代码默认，已存在的 userData 副本覆盖了它
const DEFAULT_ALLOWED_COMMAND_BINARIES = [...newList]
```
**正确**：默认清单变更时同步更新已有持久化副本（本机直接改写 userData JSON，或引导用户经设置页"恢复默认→保存"）；更稳的长期方案是区分"自动生成的默认文件"与"用户自定义"，默认变更时仅重生成默认文件
**原因**：凡有"文件优先于代码默认"的配置机制，改代码默认不会改变运行行为，必须连同配置副本一起处理

## AP-035: 排错只依赖渲染进程 console，日志不落盘
**错误**：主进程关键 handler（execute-command/skill/MCP/安全拦截）无 logger 调用，renderer 的 console.log/error 只进 DevTools 不进文件，日志文件只有启动信息，线上问题无从排查
**正确**：主进程关键路径补 logger.info/error（命令执行全流程 + stdout/stderr 截断 500B）；renderer console warning/error 经 attachRendererLogging 转发到文件；Electron 42 用新 `console-message` 事件 API（details 直挂参数）
**原因**：没有落盘日志等于没有观测手段，用户报错只能靠猜
