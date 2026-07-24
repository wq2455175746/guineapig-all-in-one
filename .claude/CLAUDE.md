# GuineaPig Project - AI Development Rules

## 🚨 MANDATORY - READ THESE FIRST

### 项目结构
- 多工程位于 `packages/` 目录
- AI Harness 位于 `.ai/` 目录
- 架构文档位于 `docs/`

### 强制前置步骤
在开始任何代码编写前，你必须：
1. 读取 `.ai/AGENTS.md`
2. 读取 `.ai/CURRENT_FOCUS`
3. 读取 `docs/ARCHITECTURE.md`
4. 检查 `.ai/traces/failures.log` 最后5行

### 核心约束
- 禁止跨服务直接导入
- 遵守 Clean Architecture 分层
- 修改 API 必须更新 OpenAPI 文档
- 提交前建议运行 `make validate`

### 快速响应模板
开始每个回复时，请包含：