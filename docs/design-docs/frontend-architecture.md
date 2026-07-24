# Frontend Architecture (guineapig-ops-web)

## Metadata
- **Status**: draft
- **Created**: 2026-05-21
- **Package**: guineapig-ops-web
- **Tech**: Vue 3, Vite, Element Plus, ECharts

## Overview
guineapig-ops-web 是运营管理后台，提供用户管理、权限管理、模型管理、Skill/MCP/Subagent 管理等功能。

## Page Structure

```
/                        Dashboard (系统概览)
├── /users              用户管理
│   ├── /users/list     用户列表
│   └── /users/:id      用户详情
├── /roles              角色权限管理
├── /sessions           会话管理
│   ├── /sessions/list  会话列表
│   └── /sessions/:id   会话详情 (对话记录)
├── /models             模型管理
│   ├── /models/list    LLM/ASR/TTS 模型列表
│   └── /models/:id     模型配置
├── /skills             Skill 管理
├── /mcps               MCP Server 管理
├── /subagents          Subagent 管理
├── /files              文件管理 (S3)
├── /tasks              任务监控
└── /settings           系统设置
```

## Component Tree

```
App.vue
├── Layout
│   ├── Sidebar         侧边栏导航
│   ├── Header          顶部栏 (用户头像/退出)
│   └── Main Content
│       ├── RouterView
│       └── Breadcrumb
├── Common Components
│   ├── DataTable       通用表格组件
│   ├── SearchForm      通用搜索表单
│   ├── CreateEditDialog 通用创建/编辑弹窗
│   ├── StatusBadge     状态标签
│   └── FileUploader    文件上传 (S3)
└── Pages (see above)
```

## API Layer

```
src/
├── api/
│   ├── index.js        Axios 实例 (baseURL, interceptors)
│   ├── user.js         用户 API
│   ├── session.js      会话 API
│   ├── task.js         任务 API
│   ├── model.js        模型 API
│   ├── skill.js        Skill API
│   └── file.js         文件 API
├── stores/             Pinia stores
│   ├── user.js
│   ├── session.js
│   └── app.js
├── router/
│   └── index.js        路由配置
└── utils/
    ├── request.js      Axios 封装
    └── auth.js         认证工具
```

## Design Principles
1. **通用化 (Generalized)**: 组件尽量做到通用，可复用到 client 和 aiagent 的管理模块
2. **无状态化 (Stateless)**: 页面组件不持有业务状态，通过 Pinia store 管理
3. **模块化 (Modular)**: 每个功能模块独立目录，方便后续拆分到能力中心

## Key Dependencies
- `vue` 3.x
- `vue-router` 4.x
- `pinia` (state management)
- `element-plus` (UI components)
- `echarts` (charts)
- `axios` (HTTP client)
- `@element-plus/icons-vue` (icons)
