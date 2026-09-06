# GuineaPig 全项目优化计划

> 来源：`.ai/TODO.md` 全项目优化审查（2026-08-21）
> 目标：修复 4 个 package 的安全漏洞、性能问题与维护性问题

## Global Constraints

- 修复过程中**不得改变外部 API 契约**（HTTP 状态码、请求/响应字段、路由路径）除非任务明确要求
- 遵循各 package 现有代码风格与项目架构规则（`.ai/AGENTS.md`）：backend 用 zap 日志、aiagent 用结构化日志带 request_id、禁跨包导入
- 所有修改必须通过现有测试；Python 包用 pytest，Go 包用 `go test ./...`，前端如有构建脚本则运行
- 安全修复优先，保持最小改动，不引入新依赖除非任务明确要求
- 当前工作分支 `dev-v727`，工作树中已有未提交的 `skill_load_service.py` 格式化改动（保留，基于它继续）
- aiagent 未使用任何认证；新增中间件后需更新所有 routers 确保不破坏 `/llm` 等现有端点
- Electron 客户端修复须保持 preload API 形状不变（`window.api.*`）

---

# Task 1: aiagent — P0 安全修复（ZIP SLIP + S3 ACL + 预签名 + 凭据 + URL 编码）

**文件**：
- `packages/guineapig-aiagent/app/services/skill_load_service.py`（`_ensure_skill_extracted` ~167-174 行）
- `packages/guineapig-aiagent/app/services/skill_service.py`（~86-98 行）
- `packages/guineapig-aiagent/app/core/oss.py`（`create_folder` 293、上传 560/581、`get_object_url` 421-428）
- `packages/guineapig-aiagent/app/config.py`（默认 `SECRET_KEY`、`OSS_AK/SK`）
- `packages/guineapig-aiagent/app/services/network_search_service.py`（20 行）

**要求**：
1. **ZIP SLIP 修复**：在 `skill_load_service.py` 和 `skill_service.py` 的解压循环中，对每个 `member_path` 做 `os.path.normpath(os.path.join(extract_dir, member_path))`，校验解析后路径 `startswith(extract_dir)`（注意 `normpath` 后再 join 一次父目录），拒绝绝对路径与 `..` 段（以 `..` 开头、含 `..` 组件）。同时限制解压总大小（如 100MB）和条目数（如 1000），超限报错/跳过。提取公共校验函数避免两处重复。
2. **S3 ACL 修复**：`oss.py` 中所有显式 `ACL="public-read"`（create_folder、小文件上传）改为私有（移除 ACL 参数或改 `private`），音频等敏感对象不再公开。确认 `get_object_url` 仍返回可用 URL。
3. **预签名 URL 修复**：`oss.py:get_object_url` 不再 `split("?")[0]` 剥离签名，返回完整预签名 URL。
4. **凭据修复**：`config.py` 默认 `SECRET_KEY="your-secret-key-change-in-production"` 与默认 `OSS_AK/SK="xxxx"` 移除或改为从环境读取（若启动必需则保留占位但打警告）。
5. **URL 编码修复**：`network_search_service.py:20` 改用 `params={"q": query, "format": "json", "language": "zh"}` 传给 requests，不再 f-string 拼接。

**验收**：上述 5 项全部修复；`python -m pytest test/ -x -q` 通过；不破坏现有 zip 解压、S3 上传下载正常路径。

---

# Task 2: aiagent — P0 接口鉴权中间件 + CORS 收紧

**文件**：
- `packages/guineapig-aiagent/app/middleware.py`（或新建 `app/core/auth.py`）
- `packages/guineapig-aiagent/app/config.py`（`CORS_ORIGINS` 24 行附近）
- `packages/guineapig-aiagent/app/main.py`（中间件注册）
- 所有 `app/routers/*.py`

**要求**：
1. 新增鉴权中间件：从 `X-Admin-Token` / `Authorization: Bearer` 读取 token，与 `settings.ADMIN_TOKEN`（新增配置项，从环境变量读，无默认值或仅 dev 默认）比对；不匹配返回 401。放行 `/docs`、`/openapi.json`、`/health` 等元数据端点。
2. 后端 `packages/guineapig-backend` 调用 aiagent 时需带 token —— 检查 backend 调用方（可在 Task 12 后端修复时处理），本次只需在 aiagent 侧实现机制并在 README 说明。
3. `agent_control.py` 的 `confirm/cancel/delegate-result` 端点同样受鉴权保护。
4. `CORS_ORIGINS`：prod 下从环境变量读取，去掉默认 `["*"]`（dev 可保留）。
5. 注意不要破坏现有测试中对未鉴权调用的假设——若测试直接调用端点，需在测试中加 token header 或 mark 跳过。

**验收**：所有 routers 端点（除白名单）无 token 返回 401；`python -m pytest test/ -x -q` 通过（必要时更新测试 fixture 带 token）。

---

# Task 3: aiagent — P1 事件循环阻塞 + 超时

**文件**：
- `packages/guineapig-aiagent/app/agent/intent.py` / `deep_analyzer.py`（114 行同步 OpenAI 调用）
- `packages/guineapig-aiagent/app/agent/dag.py` / `generator.py`（124 行）
- `packages/guineapig-aiagent/app/agent/executor/handlers.py`（135 行）
- `packages/guineapig-aiagent/app/services/handle_llmservice.py`（76 行 `get_llm_response`）
- `packages/guineapig-aiagent/app/services/handle_asrservice.py`（33 行）、`handle_ttsservice.py`（38 行）
- `packages/guineapig-aiagent/app/services/memory_summarize_service.py`（185 行）
- `packages/guineapig-aiagent/app/services/skill_load_service.py`（85 行）

**要求**：
1. 将 async 上下文中的同步阻塞 LLM 调用（`DeepAnalyzer.analyze`、`DAGGenerator.generate`、`get_llm_response`）改为 `asyncio.to_thread` 包装，或改用 `AsyncOpenAI`（与 `get_llm_response_stream` 一致）。保留 sync 版本供 sync 路径使用。
2. 所有 `requests.post`/OpenAI 调用加显式 `timeout`（如 `timeout=(5, 30)` 或 `client.timeout=...`），合理取值（LLM 可长一些如 120s，ASR/TTS 60s）。
3. 为 sync-route 中的 LLM 调用保持线程池行为不变（`def` 路由天然线程池），只为 async 路径修复。

**验收**：async 路径不再有同步阻塞调用（代码审查确认）；所有外部调用带超时；测试通过。

---

# Task 4: aiagent — P1 RAG 任务管理 + 下载错误传播 + 客户端复用 + Milvus 复用 + tqdm

**文件**：
- `packages/guineapig-aiagent/app/routers/rag.py`（27 行 `asyncio.create_task`）
- `packages/guineapig-aiagent/app/core/oss.py`（`_download_single` 96-112、`tqdm` 104-110/133-139）
- `packages/guineapig-aiagent/app/services/oss_wrapper_utils.py`（`download_file_from_s3` 164-190）
- `packages/guineapig-aiagent/app/services/rag_retrieval_service.py`（28-35 Milvus client、281-288 顺序搜索）
- `packages/guineapig-aiagent/app/services/rag_service.py`（119-126）
- LLM client 复用：`deep_analyzer.py:32`、`generator.py:38`、`handlers.py:135`、`memory_summarize_service.py:179`、`skill_load_service.py:65`、`handle_llmservice.py:126`

**要求**：
1. `rag.py` 的 `asyncio.create_task`：保留 task 引用（set），加 `done` 回调记录异常；服务关闭时取消。
2. `oss.py:_download_single`：失败时 re-raise 或返回失败状态，`download_file_from_s3` 据此返回准确状态；调用方（`handle_asr_task` 等）处理失败。
3. 移除 `oss.py` 中的 `tqdm`（或 gate 到 debug 环境变量）。
4. Milvus client：`rag_retrieval_service.py` 与 `rag_service.py` 缓存/复用单个 client（注意线程安全，可用 per-thread 或锁），多 collection 搜索可并发（`asyncio.gather`/`to_thread`）。
5. LLM client：模块级缓存复用 `OpenAI`/`AsyncOpenAI` 实例（sync+async 各一个），避免每调用新建。

**验收**：代码审查确认无泄漏 task、无 tqdm 噪音、client 复用；测试通过。

---

# Task 5: aiagent — P2 `agent.py` 单体重构 + 静默吞错 + 响应约定

**文件**：
- `packages/guineapig-aiagent/app/routers/agent.py`（956 行，`_unified_stream` 583-956，4 段重复 LLM 流式代码）
- `packages/guineapig-aiagent/app/core/oss.py`（658/715 bare `except:`）
- `packages/guineapig-aiagent/app/agent/executor/engine.py`（636）
- `packages/guineapig-aiagent/app/schemas/base_models.py`（19-45 error_response 永远 400）
- `packages/guineapig-aiagent/app/core/fileutils.py`（print 替代 logger）

**要求**：
1. `agent.py`：抽取可复用的 `_stream_llm_response(system_prompt, human_prompt, temperature, max_tokens, ...)` 帮助函数与统一 Langfuse span 封装，消除 4 段重复（trivial/direct、reject、DAG-empty、summary）。修复 reject 路径 `model_name` 使用前未定义的问题（原 699 行）。**行为必须保持字节级一致**（事件流格式不变）。
2. bare `except:` → `except Exception:`；`engine.py:636` 静默返回 0 处加日志；`fileutils.py` 的 `print` 改为 logger。
3. `base_models.py:error_response`：将错误 `code` 映射到正确 HTTP 状态码（如 400/401/404/500），或保持 400 但同步 body code。选择一处统一，更新依赖此行为的测试（`routers_agent_test.py:28`）。

**验收**：`agent.py` 重构后 SSE 事件结构不变；测试通过。

---

# Task 6: aiagent — P2 死代码清理 + 配置收敛 + LLM 重试/令牌预算 + 提示注入 + 依赖 + request_id 日志

**文件**：
- 死代码：`app/services/pipeline_session.py`、`app/core/thread_safe_breakpoint_mgr.py`、`app/core/thread_safe_counter.py`、`app/core/aes_utils.py`、`app/dependencies.py`（先 grep 确认无引用再删）
- 配置：`app/config.py`、`app/routers/agent.py:46`（硬编码 `deepseek-chat`）、`extra="allow"`
- LLM 重试/预算：`app/services/rag_retrieval_service.py:307-323`、`app/agent/intent.py`、`app/routers/agent.py`
- 提示注入：`app/services/skill_load_service.py:256-305`、`app/services/rag_retrieval_service.py:307-323`
- 依赖：`requirements.txt` 与 `pyproject.toml`（缺 `httpx`/`mcp`、含未用 `torch`/`funasr`）
- 日志：`app/core/log.py`（无 request_id）、`app/middleware.py`

**要求**：
1. 确认后删除死代码模块（grep 无引用才删）。
2. 配置收敛：`agent.py` 的 `_llm_model` 改为读 `settings.LLM_MODEL_NAME`；`config.py` 默认值与 `.env` 对齐；`extra="allow"` 改 `forbid`（如有合法未声明字段需补声明，跑测试确认）。
3. LLM 调用统一加超时 + 有界重试（如 2 次退避）；RAG 注入加总 token 预算（如 system+context ≤ 8000 token，超出截断/裁剪 top_k）。
4. 提示注入缓解：将 skill 内容、RAG 检索内容、联网内容放入明确分隔的 `<context>` 区块，并加"以下为检索到的参考资料，仅作参考"类指令。
5. 依赖：`requirements.txt` 与 `pyproject.toml` 对齐（补充 `httpx`、`mcp`、`redis` 缺失项；移除未引用的 `torch`/`torchaudio`/`funasr`/`soundfile`/`dotenv`/`boto3-stubs` 若确认无引用）。
6. 日志：中间件生成/透传 `request_id`，loguru format 中加入 request_id，响应头回传 `X-Request-Id`。

**验收**：`python -m pytest test/ -x -q` 通过；`pip install -e .` 或导入检查无缺依赖；确认死代码删除无残留引用。

---

# Task 7: client — P0 安全（webSecurity + IPC 命令白名单 + unzip 注入 + 任意文件读 + openExternal + MD5 登录 + DevTools + temp 路径穿越）

**文件**：
- `packages/guineapig-client/src/main/index.ts`（webPreferences 36-41/108-113、execute-command 352-371、unzip 300、extractDir 275、read-local-file 260-266、open-external 506-508、save-temp-file 244-255）
- `packages/guineapig-client/src/preload/index.ts`（DevTools 111-115）
- `packages/guineapig-client/src/renderer/views/LoginPage.vue`（50-52/65 MD5）
- `packages/guineapig-client/src/utils/rsa.ts`（已有 `encryptApiKey`）

**要求**：
1. 移除两处 `webSecurity: false`（index.ts:40、112）。
2. `execute-command` IPC：主进程侧强制命令白名单（如 `npx`/`python`/项目内已知二进制），拒绝 `risk !== 'low'` 除非二次确认；`cwd` 用 `path.resolve` 限制在 `userData/skills` 下，禁止绝对路径；传显式 env。
3. `download-and-extract-skill`：弃用 shell `unzip`（命令注入），改用 JS 解压库（`adm-zip` 或 `yauzl`）并校验条目路径（防 `../` 穿越）；`skillName` 用 `path.basename` + 严格正则 `^[A-Za-z0-9_-]+$`。
4. `read-local-file`：解析路径并校验在 `userData`/`temp` 根目录下。
5. `open-external`：协议白名单（`https:`/`http:` + 应用所需自定义 scheme），拒绝 `file:`/`javascript:`。
6. 登录：`LoginPage.vue` 改用已有 `encryptApiKey()`（RSA）而非 MD5。
7. `sandbox: true` 加到两个窗口 webPreferences；`setWindowOpenHandler` 拦截 `window.open`（deny + 走 `shell.openExternal` 或 `webContents.downloadURL`）；`will-navigate` 限制站内导航。
8. DevTools 快捷键仅 dev 生效（通过 preload API 暴露 `isDev` 或 `process.env.NODE_ENV` 判断）。
9. `save-temp-file`：`filename` 用 `path.basename`，`dateDir` 用 `^\d{8}$` 校验。

**验收**：TypeScript 构建通过（`npm run build` 或 `vue-tsc`）；preload API 形状不变；无 `execSync('unzip'` 残留。

---

# Task 8: client — P1 录音迁移 AudioWorklet + WebSocket 鉴权

**文件**：
- `packages/guineapig-client/src/composables/useRecorder.ts`（`createScriptProcessor` 103、`cleanupAudio` 60-73）
- `packages/guineapig-client/src/renderer/views/ChatPage.vue`（192 行 WS `?token=userId`）

**要求**：
1. `useRecorder.ts`：将 `ScriptProcessorNode` 录音改为 `AudioWorklet`（`audioWorklet.addModule` + `AudioWorkletNode`）。若 AudioWorklet 需要额外文件（如 `recorder-worklet.js`）则创建并放在 `src/` 下。保持对外暴露的 API（`start`/`stop`/`onAudioChunk` 回调及 PCM 数据格式）不变，`cleanupAudio` 正确释放。
2. WebSocket 鉴权：不再用 `user_id` 作为 token；改用后端签发的会话/访问 token（若无则先通过登录接口获取，或至少使用 `encryptApiKey` 后的凭据换取 token）。如后端暂不支持，则保留但加 TODO 注释并记录为已知限制。
3. 如可行，为 `useRecorder` 增加简单测试或至少构建通过验证。

**验收**：`npm run build` 通过；录音数据流格式与改造前一致（审查确认）；WS 不再用裸 `user_id` 当 token。

---

# Task 9: ops-web — P0 注册页修复 + admin token 清理 + gitignore

**文件**：
- `packages/guineapig-ops-web/src/config/api.js`（无 `AUTH` key）
- `packages/guineapig-ops-web/src/views/RegisterPage.vue`（104 行）
- `packages/guineapig-ops-web/src/config/axios.js`（12 行 fallback token）
- `packages/guineapig-ops-web/.env`
- 新建 `packages/guineapig-ops-web/.gitignore`

**要求**：
1. `api.js` 增加 `AUTH` 端点定义（`REGISTER`，指向后端实际注册端点；如后端无公开注册端点，则对齐 `RegisterPage.vue` 现有调用路径）。确认 `RegisterPage.vue` 注册流程可用。
2. 移除 `axios.js:12` 硬编码 `'guineapig-admin-dev-token'` 回退；token 改为从 `import.meta.env.VITE_ADMIN_TOKEN` 读取，缺失时警告。
3. 新增 `.gitignore`（`.env*`、`node_modules`、`dist` 等）。
4. 若 `.env` 已提交则从 git 移除（`git rm --cached`）但保留本地文件。

**验收**：注册页不再抛 `Cannot read properties of undefined`；构建通过；`.env` 不入库。

---

# Task 10: ops-web — P1 ECharts 泄漏 + loadUsers 999

**文件**：
- `packages/guineapig-ops-web/src/views/Dashboard.vue`（chart 实例 102-105/180/217/112-122/268-272/301-305/319-332）
- 8 个视图的 `loadUsers`（Dashboard 124-139、ConversationMgr 149-165、UserMemoryMgr 174-190、McpMgr 160-176、SkillMgr 141-157、ModelMgr 148-164、InfoChannelMgr 139-155、UserFileMgr 106-122）

**要求**：
1. `Dashboard.vue`：将 `renderChart`/`renderPieChart` 返回值保存到响应式变量；`onBeforeUnmount`/`onUserChange` 真正 dispose；重绘前先 dispose 旧实例；ResizeObserver 在卸载时断开。
2. `loadUsers`：将 `pageSize: 999` 下拉改为轻量用户选项接口或共享缓存（新 composable `useUserOptions`，模块级缓存 + 失效）。至少消除 Dashboard 的二次请求（复用第一次的 total）。
3. 若后端有用户列表接口支持 `pageSize` 较小分页，下拉用分页搜索；否则缓存整表到模块级。

**验收**：换用户/卸载页面不再累积 chart 实例（代码审查）；`loadUsers` 不再每页全量拉取（或已缓存）。

---

# Task 11: ops-web — P2 CRUD 样板 + 路由守卫 + 空壳视图 + axios 拦截器 + ECharts 按需 + indexOf + 配置 + build.sh

**文件**：
- 8 个管理视图（Dashboard、ConversationMgr、UserMemoryMgr、McpMgr、SkillMgr、ModelMgr、InfoChannelMgr、UserFileMgr）
- `packages/guineapig-ops-web/src/router/index.js`、`src/components/Layout.vue`（61/104/117-119）
- `AsrTtsMgr.vue`、`RobotMgr.vue`、`SystemMgr.vue`、`WorkflowMgr.vue`（空壳）
- `src/config/axios.js`（拦截器 34-46 被注释）
- `src/views/Dashboard.vue`（80 行 echarts 全量 import）
- `package.json`（未用依赖 html2canvas/xterm/xterm-addon-fit）
- `src/config/api.js`、`vite.config.js`、`build.sh`
- `src/views/UserList.vue`、`ScheduledTaskMgr.vue`（document.title）

**要求**：
1. 抽取 `usePagedList(endpoint, {filters})` composable（状态 items/total/loading/pageSize/pageNum + fetchList/handleSearch/onPage/onFilterChange），8 个视图复用；`formatTime` 抽公共 util 统一格式。
2. 路由守卫：`router.beforeEach` 检查 token，无 token 跳登录；`Layout.vue` logout 实现清理 + 跳转；移除或实现 `/settings`；`document.title` 移入 router meta + `afterEach`。
3. 空壳视图接入 `PlaceholderView` 或移除路由；加 catch-all `*` → PlaceholderView。
4. 启用 axios 响应拦截器（unwrap `{code,result,message}`、非 0 弹 toast、401 跳登录）；视图相应简化（可选，保持最小改动）。
5. ECharts 按需引入（`echarts/core` + 用到的 chart/component/renderer）；移除 `html2canvas`/`xterm`/`xterm-addon-fit`（确认未用）。
6. 行号计算改用插槽 `index` + `(pageNum-1)*pageSize`，弃用 `indexOf`。
7. `api.js` 用 `import.meta.env` 替代 `process.env`；vite proxy `secure:true` 移除、rewrite 修正；删除 `main.js` 多余全局 axios 默认。
8. `build.sh` push 镜像名与 build 名统一。

**验收**：`npm run build` 通过；页面行为不变；无 `indexOf(data)` 残留；无全量 echarts import。

---

# Task 12: backend — P0 安全（鉴权 + IDOR + inner 路由 + aimodel 解密预言机/SSRF + WS 崩溃 + 关闭死锁 + 硬编码验证码）

**文件**：
- `packages/guineapig-backend/pkg/middleware/auth.go`（X-User-Id 信任 79-105、skipPaths 30、inner 74-77）
- `packages/guineapig-backend/internal/router/chat/websocket.go`（50-63 parseToken、19-21 CheckOrigin）
- `packages/guineapig-backend/internal/router/memory/controller.go`（30-45）、`internal/service/chat_memory.go`（139-162、429-434）
- `packages/guineapig-backend/internal/service/user.go`（56-77、86-88、122）
- `packages/guineapig-backend/internal/router/chat/{messages,conversations,conversation_history}.go`
- `packages/guineapig-backend/internal/router/aimodel/test.go`（62-102、178）
- `packages/guineapig-backend/internal/service/chat_hub.go`（73-107、245、717-733）
- `packages/guineapig-backend/internal/server/server.go`（79-88）
- `packages/guineapig-backend/internal/router/file/embed_progress.go`、`internal/router/memory/`（inner 路由）
- `packages/guineapig-backend/config.yaml`（jwtSecret 4、debug 3）

**要求**：
1. **鉴权**：实现真实 token 鉴权（JWT 或 HMAC 签名会话），从 token 推导 caller identity，所有路由（含 WS 握手、inner 路由）强制校验；`X-User-Id` 不再作为可信身份。`config.yaml:jwtSecret` 改为环境变量注入（`jwtSecret: ${JWT_SECRET}` 或 config.go 从 env 读取），移除 `dmxaitest`。
2. **IDOR**：`memory/get`、`DecryptUserInfo`、聊天消息/会话/历史列表强制 `requester == resource.Owner`；不接受客户端传入的目标 user_id。
3. **inner 路由**：`/inner/api/v1/*` 加共享内部 token（header）校验。
4. **aimodel/test**：不再将解密后的明文 key 发送到客户端提供的 `apiUrl`；`apiUrl` 加入网络 allowlist（预注册模型端点）；`http.NewRequest` 绑定 request context + 超时。
5. **WS hub 崩溃**：`Register`/`Unregister` 不再直接 `close(client.Send)`，改 `done` channel + `sync.Once`，`sendToClient` 在 closed 后 drop；所有 spawned goroutine 加 `recover()`；`Unregister` 只取消该用户自己会话的 aiAgentConns。
6. **关闭死锁**：`server.go` 的 `RunAsync` 在 `defer` 中保证 `close(done)`。
7. **硬编码验证码**：注册验证码从配置读取（env），MD5 存 key 改 HMAC-SHA256 或 bcrypt（最小改动可 HMAC）。

**验收**：`go build ./...`、`go vet ./...`、`go test ./...` 通过；鉴权中间件对无 token 请求拒绝；不破坏现有健康检查/心跳端点。

---

# Task 13: backend — P1 上下文/超时 + 并发 + N+1/索引 + HTTP client 复用 + 背压

**文件**：
- `packages/guineapig-backend/pkg/utils/uuid.go`（15-23 NewContext）
- `packages/guineapig-backend/internal/service/{file.go,chat_memory.go,chat_hub.go}`、`agent_proxy.go`、`chat_stream.go`
- `packages/guineapig-backend/sql/`（新建迁移）
- `packages/guineapig-backend/internal/model/{chat_otel,user_aimodel,res_files,user,res_rags,res_mcp,res_skills}.go`
- 10+ 处 `&http.Client{}`

**要求**：
1. `NewContext` 从 `c.Request().Context()` 派生（保留 requestId 字段），DB/Redis/HTTP 操作加 `context.WithTimeout`。
2. goroutine：`file.go:145,327`、`chat_memory.go:378`、`agent_proxy.go:457` 等改用连接生命周期 context，bound 并发或用 Asynq；WS 断开时取消。
3. N+1：`chat_stream.go:resolveRagContext` 改 `WHERE ... IN` 批量；`chat_memory.go` 当日消息加载加 limit；List 方法 `PageSize=0` 时加硬上限（如 1000）。
4. 索引：新增迁移 SQL 为 `chat_messages(conversation_id)`、`chat_otel(user_id, stat_date, name, type)`（含 UPSERT 唯一键）、`res_files(user_id, deleted_at)`、`chat_memory(user_id, deleted_at)`、`user_apikey(api_key)`、`user_aimodel(user_id, deleted_at)` 加索引。
5. HTTP client：抽共享 `http.Client`（带 transport 连接池）供 10+ 处复用。
6. 背压：`sendToClient` 缓冲满时 drop-and-log（或断开），不再阻塞 10s。

**验收**：`go build ./...`、`go vet ./...`、`go test ./...` 通过；新迁移 SQL 有效（review 确认语法）。

---

# Task 14: backend — P2 message_count + 忽略错误 + 日志统一 + 死代码 + 配置

**文件**：
- `packages/guineapig-backend/internal/service/chat.go`（125-127）、`chat_hub.go`（379-381、662-664）、`chat_sync.go`（45-47）
- ~84 处忽略错误点
- `pkg/plugin/logger/logger.go`（18-34 fmt.Sprintf 问题）
- `internal/service/file.go`（17 处 log.Printf）、`chat_memory.go`、`config/config.go:73`
- `internal/router/common/response.go`（40-44）
- `internal/server/server.go`（死代码 Run/shutdownCh 67-77、98-107）
- `config.yaml`（debug 3、rateLimiter 31-32、CORS）

**要求**：
1. `message_count`：所有设置点改 `gorm.Expr("message_count + 1")`；`chat_sync.go` 读回的错误处理。
2. 审计并处理 `_ =` 忽略错误（DB 写、json.Marshal、Redis 操作）：至少记录日志，不静默吞。
3. 日志统一：`log.Printf` → zap（带 request_id）；`logger.go` 的 `fmt.Sprintf(msg, a...)` 修复（避免 `%` 损坏）；`ResponseServerError` 不再泄漏原始错误细节到客户端。
4. 删除死代码 `server.go` 的 `Run`/`shutdownCh`。
5. 配置：`debug: true` 改为 env 控制（默认 false），启动不再 dump 含密钥配置；rateLimiter 配置补全或明确注释；CORS 从配置读取（`CorsHosts`）。

**验收**：`go build ./...`、`go vet ./...`、`go test ./...` 通过；`message_count` 递增正确（如有测试更新之）。