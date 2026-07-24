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
