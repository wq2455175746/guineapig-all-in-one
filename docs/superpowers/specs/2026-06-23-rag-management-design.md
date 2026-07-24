# 知识库管理功能设计文档

## 概述
在 ResourcePage.vue 中添加"知识库" tab，提供知识库的 CRUD 能力。用户可创建知识库（配置分段大小、嵌入模型、reranker 模型等），以卡片形式浏览，支持搜索和分页。

## 架构

### 后端
- **数据库表**: `guineapig.res_rags`（按用户提供的 SQL CREATE TABLE）
- **新增路由**: `/api/v1/rag/*` — CRUD 4 个端点
- **新增**: `/api/v1/aimodel/options-by-type` — 按 model_type 过滤 AI 模型选项

### 前端
- **新增组件**: `RagTab.vue` — 知识库管理 tab
- **修改**: `ResourcePage.vue` — 添加知识库 tab

## 数据流
1. 用户打开知识库页面 → 前端请求 `GET /api/v1/rag/list` → 渲染卡片列表
2. 用户添加知识库 → 弹出 Dialog → 填写表单并提交 `POST /api/v1/rag/create`
3. 用户更新 → 弹出编辑 Dialog → 仅可修改描述 → `POST /api/v1/rag/update`
4. 用户删除 → 确认弹窗 → `POST /api/v1/rag/delete`
5. 搜索 → 输入关键词 → 点击搜索 → 带 keywords 的 `GET /api/v1/rag/list`
