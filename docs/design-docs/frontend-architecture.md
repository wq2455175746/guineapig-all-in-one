# Frontend Architecture (guineapig-ops-web)

## Metadata
- **Status**: implemented (updated to match current code)
- **Created**: 2026-05-21
- **Updated**: 2026-10-17
- **Package**: guineapig-ops-web
- **Tech**: Vue 3.5, Vite 7, PrimeVue 4 (Aura), ECharts 5, axios, vue-router 4

> 说明：本文替换早期"Element Plus + Pinia + TS"的草稿设计，描述**当前代码**实现。

## Overview

guineapig-ops-web 是运营管理后台，提供用户、模型、Skill、MCP、知识库(RAG)、记忆、文件、
对话记录、指标、定时任务、Bot 管理等管理功能。

- 使用 **JavaScript (ESM)**，非 TypeScript
- UI 组件库为 **PrimeVue 4**（Aura 主题），非 Element Plus
- **无 Pinia**：状态由 Vue `ref` + 模块级单例 composable + `localStorage` 管理
- 路由使用 `createWebHistory`（history 模式）

## Page Structure

路由定义在 `src/router/index.js`：

```
/register                用户注册（无鉴权）
/                        Layout（侧边栏 + 顶栏）
├── /dashboard           Dashboard（系统概览）
├── /conversationMgr     对话管理
├── /userList            用户管理
├── /userFileMgr         用户文件
├── /modelMgr            模型管理
├── /skillMgr            Skill 管理
├── /mcpMgr              MCP 管理
├── /userMemoryMgr       用户记忆
├── /infoChannelMgr      信息渠道
├── /scheduledTaskMgr    定时任务
├── /permissionMgr       权限管理（占位）
└── /roleMgr             角色管理（占位）
/:pathMatch(.*)*         404 占位页
```

> `src/views/` 中另有 `AsrTtsMgr`、`SystemMgr`、`WorkflowMgr`、`RobotMgr` 等文件，当前未挂载路由。
> 权限/角色等页面为 `PlaceholderView` 占位（"待实现"）。

## Directory Structure

```
src/
├── main.js                 # 应用入口：PrimeVue(Aura)、router、ToastService、指令
├── App.vue                 # <router-view/>
├── components/
│   ├── Layout.vue          # 侧边栏 Menu + 顶栏 + <router-view> + Toast
│   ├── AppHeader.vue
│   └── PlaceholderView.vue # "待实现" 占位组件
├── composables/
│   ├── usePagedList.js     # 通用分页列表
│   └── useUserOptions.js   # 用户下拉选项（模块级缓存）
├── config/
│   ├── axios.js            # axios 实例 + 拦截器（注入 X-Admin-Token）
│   └── api.js              # 端点定义 + base URL（/admin/api/v1）
├── router/index.js         # 路由 + 鉴权守卫
├── utils/format.js
└── views/                  # 17 个页面组件
```

## API Layer

- `src/config/axios.js`：axios 实例，请求拦截器注入 **`X-Admin-Token`**
  （取自 `localStorage.admin_token`，回退 `import.meta.env.VITE_ADMIN_TOKEN`）；
  响应拦截器对业务错误弹 Toast，401 清除 token 并跳转 `/register`。
- `src/config/api.js`：
  - `API_BASE_URL`：dev 为 `http://guineapig-ops-web.local:6880`，prod 为同源
  - 管理端点前缀 **`/admin/api/v1`**（`ADMIN_PREFIX`）
  - 登录/注册端点前缀 **`/api/v1`**（`/api/v1/client/login|register`）
- Vite dev proxy：`/admin/api/v1`、`/api/v1` → `http://guineapig-ops.local:6880`
- 生产由 nginx 反代到 `guineapig-backend:6880`

## Auth Guard

`router.beforeEach` 检查 `localStorage.admin_token`（或 `VITE_ADMIN_TOKEN`）；无 token 且目标非 `/register` 时重定向到 `/register`。
`afterEach` 按 `meta.title` 设置 `document.title`。登出清除 `admin_token`。

## Design Principles

1. **通用化**: 通用组件（`usePagedList`、`PlaceholderView`）可复用于资源管理模块
2. **轻状态**: 以 composable + localStorage 管理，避免引入重型状态库
3. **模块化**: 每个功能模块独立 view，便于后续拆分

## Key Dependencies

- `vue` 3.5
- `vue-router` 4 (history)
- `primevue` 4 + `@primevue/themes` (Aura) + `primeicons`
- `echarts` 5（Dashboard 直接使用 `echarts/core`；`vue-echarts` 已声明但未使用）
- `axios`
- `qs`

## Dev / Build

```bash
npm run dev      # Vite dev server, 端口 5173
npm run build    # NODE_ENV=production vite build
```

Node 要求 `^20.19.0 || >=22.12.0`。
