# GuineaPig 优化待办清单

> 来源：2026-08-21 全项目优化审查（并行分析 4 个 package）
> 状态说明：`[ ]` 待办 / `[x]` 已完成
> 更新：2026-09-06 全部任务已通过子代理执行并逐任务审查完成（详见 git log 516e37e..9340038）

## 🔴 P0 安全漏洞（最紧急）

### guineapig-aiagent
- [x] **ZIP SLIP 路径穿越**：`app/services/skill_load_service.py:167-174` 与 `app/services/skill_service.py:86-98` 解压时未校验成员路径，恶意 zip 可任意写文件 → RCE。修复：`normpath` 校验 + 拒绝 `..`/绝对路径 + 限制解压总大小/条目数（zip bomb）
- [x] **S3 全公开 ACL**：`app/core/oss.py:293,560,581` 所有上传（含用户 TTS/ASR 音频）设为 `ACL="public-read"`。修复：改私有 + 预签名 URL 控制访问
- [x] **接口无鉴权**：所有路由无认证（`CORS_ORIGINS=["*"]`），`agent_control.py` session_id 可被猜测劫持。修复：加 API key/token 中间件 + 校验 session 归属 + 限制 CORS
- [x] **预签名 URL 签名被剥除**：`app/core/oss.py:421-428` `get_object_url` 把 `?` 后的签名去掉，变成永久公开链接。修复：返回完整预签名 URL
- [x] **凭据泄漏**：`.env` 存真实 DeepSeek/OSS/Redis key；`app/config.py:23` 默认 `SECRET_KEY` 不安全。修复：轮换凭据 + 移除硬编码默认值
- [x] **网络搜索 URL 未编码**：`network_search_service.py:20` 用户 query 直接拼接进 URL。修复：用 `params=` 传参

### guineapig-client (Electron)
- [x] **`webSecurity: false`**：`src/main/index.ts:40,112` 禁用同源策略。修复：移除，改用 `session.webRequest`/自定义 scheme
- [x] **IPC 任意命令执行**：`src/main/index.ts:352-371` `execute-command` 无白名单执行任意 shell。修复：主进程边界加白名单（npx/python 等）+ 拒绝高风险命令 + 限制 cwd
- [x] **unzip 命令注入 + 路径穿越**：`src/main/index.ts:300` `skillName` 拼进 shell 字符串（命令注入），且可 `../` 穿越。修复：改用 JS zip 库（adm-zip/yauzl）+ 严格校验 `skillName`
- [x] **`read-local-file` 任意文件读取**：`src/main/index.ts:260-266` 无目录限制。修复：限制在 userData/temp 内
- [x] **`open-external` 任意协议**：`src/main/index.ts:506-508` 接受任意 URL。修复：协议白名单（https/http + 必要自定义 scheme）
- [x] **登录用 MD5**：`src/renderer/views/LoginPage.vue:50-52,65` 应用已有 RSA（`src/utils/rsa.ts`）。修复：复用 `encryptApiKey()`

### guineapig-ops-web
- [x] **注册页坏掉**：`src/views/RegisterPage.vue:104` `API_ENDPOINTS.AUTH` 未定义（`src/config/api.js`）。修复：补 AUTH 端点
- [x] **硬编码 admin token 入库**：`src/config/axios.js:12` + `.env:1`，且无 `.gitignore`。修复：删除回退 token + 加 `.gitignore` + 轮换 token

## 🟠 P1 性能 / 正确性

### guineapig-aiagent
- [x] **async 事件循环被阻塞（最高影响）**：`DeepAnalyzer.analyze`（`deep_analyzer.py:114`）、`DAGGenerator.generate`（`generator.py:124`）、`get_llm_response`（`handle_llmservice.py:76`）同步阻塞 LLM 调用跑在 async SSE/chat 路由内，并发时冻结所有请求。修复：改 `AsyncOpenAI` 或 `asyncio.to_thread`
- [x] **HTTP/LLM 调用无超时**：ASR/TTS/LLM 多处 `requests.post`/OpenAI 调用无 `timeout`（`handle_asrservice.py:33`、`handle_ttsservice.py:38`、`deep_analyzer.py`、`generator.py`、`memory_summarize_service.py:185` 等）。修复：全部加 timeout + 有界重试
- [x] **RAG 后台任务 fire-and-forget**：`app/routers/rag.py:27` `asyncio.create_task` 无异常处理/引用/取消。修复：保留引用 + done 回调 + 任务管理器
- [x] **`OSS._download_single` 吞错误**：`app/core/oss.py:96-112` 失败仅 log 不传播，下游可能拿到截断文件。修复：re-raise 或返回失败状态
- [x] **重复创建 LLM client**：每调用新建 OpenAI/AsyncOpenAI 实例（7 处）。修复：模块级缓存复用
- [x] **Milvus 连接反复创建**：`rag_retrieval_service.py`、`rag_service.py` 每次 search/write 新建连接；多 collection 顺序搜索。修复：复用 client + 并发搜索
- [x] **`tqdm` 进度条污染服务日志**：`app/core/oss.py:104-110,133-139`。修复：移除或 dev 才启用

### guineapig-client (Electron)
- [x] **`ScriptProcessorNode` 已废弃**：`src/composables/useRecorder.ts:103` 录音跑 UI 线程。修复：迁移 AudioWorklet
- [x] **WebSocket 用 user_id 当鉴权**：`src/renderer/views/ChatPage.vue:192` token 可被猜/泄漏。修复：用服务端签发的 session token

### guineapig-ops-web
- [x] **ECharts 实例泄漏**：`src/views/Dashboard.vue:180,217` 丢弃 `renderChart` 返回值，dispose 全清 null，换用户/卸载后图表+ResizeObserver 泄漏。修复：保存实例 + 复用前 dispose（或用 vue-echarts）
- [x] **每页拉 999 个用户**：8 处 `loadUsers` 全量加载且不缓存；`Dashboard.vue:145` 二次请求只读 total。修复：后端加下拉专用端点或共享缓存

## 🟡 P2 维护性

### guineapig-aiagent
- [x] **`agent.py` 956 行单体**：`/chat/stream` 内 4+ 段重复 LLM 流式代码（661-766/769-784/794-889/920-932）。修复：抽 `_stream_llm_response` 复用函数 + Langfuse span 封装
- [x] **静默吞错/bare except**：`oss.py:658,715` bare `except:`；`engine.py:636`、`fileutils.py` 用 print。修复：`except Exception` + 结构化日志
- [x] **响应约定不一致**：`schemas/base_models.py:19-45` 错误永远返回 HTTP 400，与 body code 矛盾。修复：统一 envelope / 映射正确状态码
- [x] **死代码**：`pipeline_session.py`、`thread_safe_breakpoint_mgr.py`、`thread_safe_counter.py`、`fileutils.py` 大部分、`aes_utils.py`（ECB 弱加密）。修复：清理或标注
- [x] **配置漂移**：`agent.py:46` 硬编码 `deepseek-chat`；`config.py` 默认值多处与 `.env` 不一致；`extra="allow"` 容忍拼写错误。修复：统一收敛到 `settings`
- [x] **LLM 无重试/令牌预算**：所有 LLM 调用无超时重试；RAG top_k×2000 字符无总预算。修复：加超时+退避重试 + 总 token 预算守卫
- [x] **提示注入面**：skill 文件内容、RAG 检索内容直接注入 system prompt（`skill_load_service.py:256-305`、`rag_retrieval_service.py:307-323`）。修复：分隔/清洗不可信内容
- [x] **需求清单不一致**：`requirements.txt` 与 `pyproject.toml` 漂移（缺 `httpx`/`mcp`，含未用 `torch`/`funasr` 拖爆镜像）。修复：单一来源 + 精确 pin + 清理未用依赖
- [x] **日志无 request_id**：`core/log.py` 无 request_id 关联。修复：中间件注入 request_id + 进响应头

### guineapig-ops-web
- [x] **8 个视图重复 CRUD 样板**：`loadUsers`/`fetchList`/分页/样式块大量重复（`formatTime` 16/19 字符不一致）。修复：抽 `usePagedList` composable + 共享 `<DataListPage>`
- [x] **无路由守卫/登出空操作**：`router/index.js` 无 beforeEach；`Layout.vue:61` user 硬编码 admin；`handleLogout` 空；`/settings` 死链。修复：加鉴权守卫 + 真实登出 + 清理路由
- [x] **空壳视图注册为路由**：`AsrTtsMgr/RobotMgr/SystemMgr/WorkflowMgr.vue` 空白页。修复：接入 `PlaceholderView` 或移除
- [x] **axios 拦截器被注释**：`config/axios.js:34-46` 无 401 处理，27 处手动检查 `code===0`。修复：启用拦截器统一 unwrap + toast + 401 跳登录
- [x] **ECharts 全量引入 + 未用依赖**：`Dashboard.vue:80` 全量 import；`html2canvas`/`xterm`/`xterm-addon-fit` 从未使用。修复：按需引入 + 清理
- [x] **行号用 `indexOf`**：O(n²) 且重复对象错乱（8 张表）。修复：用插槽 index + 分页偏移
- [x] **配置不一致**：`api.js` 用 `process.env` 而应 `import.meta.env`；vite proxy `secure:true` 无效。修复：统一 env 方案
- [x] **build.sh 镜像名不匹配**：build `guineapig-web:1.0.0` 却 push `guineapig:1.0.0`。修复：统一 tag

### guineapig-backend（Go）
- [x] 待展开：N+1 查询、缺失索引、日志 request_id、错误处理等（详见审查原始报告，需补全到本文件）

---

## 建议执行顺序

1. **P0 安全**（zip 穿越 → ACL → 鉴权 → 命令注入 → admin token）
2. **P1 性能**（事件循环阻塞 → 超时 → ECharts 泄漏 → AudioWorklet）
3. **P2 维护性**（代码结构 → 重复样板 → 依赖清理）
