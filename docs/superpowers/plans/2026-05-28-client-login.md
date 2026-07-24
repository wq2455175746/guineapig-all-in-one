# Client Login Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement backend login API and frontend login flow for guineapig-client using api_key + device_id

**Architecture:** Backend validates api_key against `user_apikey` table, looks up user info from `user` table, returns user_id + email. Frontend calls the API on login, stores credentials in localStorage, then redirects to chat page.

**Tech Stack:** Go 1.24 + Echo v4 + GORM (backend), Electron + Vue 3 + PrimeVue (frontend)

---

### Task 1: Backend — Create UserApiKey Model

**Files:**
- Create: `packages/guineapig-backend/internal/model/user_apikey.go`

- [ ] **Step 1: Create UserApiKey model**

Write `packages/guineapig-backend/internal/model/user_apikey.go`:

```go
package model

type UserApiKey struct {
	Id         int64  `gorm:"column:id"`
	UserId     int64  `gorm:"column:user_id"`
	ApiKey     string `gorm:"column:api_key"`
	Status     int8   `gorm:"column:status"`
}

func (*UserApiKey) TableName() string {
	return "user_apikey"
}

func (*UserApiKey) FindByApiKey(ctx, apiKey string) (*UserApiKey, error) {
	var key UserApiKey
	err := plugin.GetDB(ctx).Where("api_key = ? AND status = 1", apiKey).First(&key).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, err
	}
	return &key, nil
}
```

Note: This model only maps fields we need: id, user_id, api_key, status. The `FindByApiKey` query filters for active (status=1) keys.

- [ ] **Step 2: Add required imports and verify compilation**

The model needs these imports at the top of the file. Write the complete file:

```go
package model

import (
	"context"
	"errors"
	"gorm.io/gorm"
	"guineapig/pkg/plugin"
)
```

Run to verify:
```bash
cd packages/guineapig-backend && go build ./...
```
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add packages/guineapig-backend/internal/model/user_apikey.go
git commit -m "feat(backend): add UserApiKey model for api_key lookup"
```

---

### Task 2: Backend — Add Login Request/Response Structs

**Files:**
- Modify: `packages/guineapig-backend/internal/request/user.go`
- Modify: `packages/guineapig-backend/internal/response/user.go`

- [ ] **Step 1: Add ClientLoginRequest to request/user.go**

Append before the closing of the file:

```go
type ClientLoginRequest struct {
	ApiKey   string `json:"api_key" form:"api_key"`
	DeviceId string `json:"device_id" form:"device_id"`
}
```

- [ ] **Step 2: Add ClientLoginResponse to response/user.go**

Append before the closing of the file:

```go
type ClientLoginResponse struct {
	UserId int64  `json:"user_id"`
	Email  string `json:"email"`
}
```

- [ ] **Step 3: Verify compilation**

```bash
cd packages/guineapig-backend && go build ./...
```
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add packages/guineapig-backend/internal/request/user.go packages/guineapig-backend/internal/response/user.go
git commit -m "feat(backend): add login request/response structs"
```

---

### Task 3: Backend — Add ClientLogin Service

**Files:**
- Modify: `packages/guineapig-backend/internal/service/user.go`

- [ ] **Step 1: Add ClientLogin service function**

Append to `internal/service/user.go` before the last closing brace:

```go
func ClientLogin(ctx context.Context, req *request.ClientLoginRequest) (*response.ClientLoginResponse, error) {
	// 1. 根据 api_key 查找 apikey 记录
	apiKeyRecord, err := model.MUserApiKey.FindByApiKey(ctx, req.ApiKey)
	if err != nil {
		logger.ErrorReqIdf(ctx, "find api_key error: %v, apiKey: %s", err, req.ApiKey)
		return nil, err
	}
	if apiKeyRecord == nil {
		return nil, errors.New("api_key 不存在或已禁用")
	}

	// 2. 根据 user_id 查找用户信息
	user, err := model.MUser.FindById(ctx, apiKeyRecord.UserId)
	if err != nil {
		logger.ErrorReqIdf(ctx, "find user by id error: %v, userId: %d", err, apiKeyRecord.UserId)
		return nil, err
	}
	if user == nil {
		return nil, errors.New("用户不存在")
	}

	// 3. 返回 user_id 和 email
	return &response.ClientLoginResponse{
		UserId: user.Id,
		Email:  user.Email,
	}, nil
}
```

- [ ] **Step 2: Add MUserApiKey global variable reference**

In `internal/model/user_apikey.go`, we already have the model. But we need to make sure `MUserApiKey` is defined as a singleton just like `MUser`. Add to `user_apikey.go`:

```go
var MUserApiKey = &UserApiKey{}
```

- [ ] **Step 3: Add import for model package**

The service already imports `"guineapig/internal/model"`, so no new import is needed. `model.MUserApiKey` will be accessible.

- [ ] **Step 4: Verify compilation**

```bash
cd packages/guineapig-backend && go build ./...
```
Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add packages/guineapig-backend/internal/model/user_apikey.go packages/guineapig-backend/internal/service/user.go
git commit -m "feat(backend): add ClientLogin service with api_key validation"
```

---

### Task 4: Backend — Add Login Route Handler and Register Route

**Files:**
- Create: `packages/guineapig-backend/internal/router/user/client_login.go`
- Modify: `packages/guineapig-backend/internal/router/router.go`

- [ ] **Step 1: Create client_login.go handler**

Write `packages/guineapig-backend/internal/router/user/client_login.go`:

```go
package user

import (
	"github.com/labstack/echo/v4"
	"guineapig/internal/request"
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	"guineapig/pkg/utils"
)

func ClientLogin(e echo.Context) error {
	ctx := utils.NewContext(e)
	var req request.ClientLoginRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}

	if req.ApiKey == "" {
		return common.ResponseParamError(e, nil)
	}

	resp, err := service.ClientLogin(ctx, &req)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, resp)
}
```

- [ ] **Step 2: Register route in router.go**

Add import and route registration. In `packages/guineapig-backend/internal/router/router.go`, add to `init()`:

```go
AddPostRouter("/client/login", user.ClientLogin)
```

- [ ] **Step 3: Verify compilation**

```bash
cd packages/guineapig-backend && go build ./...
```
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add packages/guineapig-backend/internal/router/user/client_login.go packages/guineapig-backend/internal/router/router.go
git commit -m "feat(backend): add POST /client/login route and handler"
```

---

### Task 5: Backend — Update CORS for Electron Client

**Files:**
- Modify: `packages/guineapig-backend/internal/server/server.go`

- [ ] **Step 1: Add Electron dev server to CORS origins**

In `packages/guineapig-backend/internal/server/server.go`, update the CORS config to include the Electron Vite dev server:

```go
e.Use(middleware.CORSWithConfig(middleware.CORSConfig{
    AllowOrigins:     []string{"http://guineapig-ops-web.local:5173", "http://localhost:5173"},
    AllowCredentials: true,
    AllowHeaders:     []string{"Origin", "Content-Type", "Accept", "Authorization"},
    AllowMethods:     []string{echo.GET, echo.POST, echo.PUT, echo.DELETE, echo.OPTIONS},
}))
```

Key change: Added `"http://localhost:5173"` to `AllowOrigins` for the Electron Vite dev server.

- [ ] **Step 2: Verify compilation**

```bash
cd packages/guineapig-backend && go build ./...
```
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add packages/guineapig-backend/internal/server/server.go
git commit -m "fix(backend): add localhost:5173 to CORS origins for Electron client"
```

---

### Task 6: Frontend — Update LoginPage.vue to Call Backend API

**Files:**
- Modify: `packages/guineapig-client/src/renderer/views/LoginPage.vue`

- [ ] **Step 1: Update LoginPage.vue handleLogin function**

Replace the `handleLogin` function and add API call logic. The key changes:

1. `handleLogin()` now makes a POST request to the backend
2. On success, stores `api_key`, `user_email`, `user_id`, and `device_id` to localStorage
3. Then redirects to chat

Updated script section:

```vue
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import Avatar from 'primevue/avatar'
import InputText from 'primevue/inputtext'
import Button from 'primevue/button'

const router = useRouter()
const apiKey = ref('')
const machineId = ref('')
const loggingIn = ref(false)
const loginError = ref('')

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:6880'

onMounted(async () => {
  try {
    machineId.value = await window.electronAPI.getMachineId()
  } catch {
    machineId.value = '获取失败'
  }
})

async function handleLogin() {
  if (!apiKey.value) return

  loggingIn.value = true
  loginError.value = ''

  try {
    const res = await fetch(`${API_BASE_URL}/client/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        api_key: apiKey.value,
        device_id: machineId.value
      })
    })

    const data = await res.json()

    if (data.code !== 0) {
      loginError.value = data.message || '登录失败'
      return
    }

    // 登录成功，写入 localStorage
    localStorage.setItem('api_key', apiKey.value)
    localStorage.setItem('user_email', data.result.email)
    localStorage.setItem('user_id', String(data.result.user_id))
    localStorage.setItem('device_id', machineId.value)

    router.push({ name: 'Chat' })
  } catch (err) {
    loginError.value = '网络错误，请检查后端服务是否启动'
  } finally {
    loggingIn.value = false
  }
}

function openKeyPage() {
  // TODO: 跳转到密钥管理页面，后续补充具体 URL
}
</script>
```

- [ ] **Step 2: Update template to show error message and loading state**

Update the `<template>` section to add error display and loading state. Replace the login button section:

```vue
<Button label="登录" icon="pi pi-sign-in" class="login-button" severity="secondary" raised
  :disabled="!apiKey || loggingIn" @click="handleLogin" />

<p v-if="loginError" class="login-error">{{ loginError }}</p>
```

Add to the `<style scoped>` section:

```css
.login-error {
  font-size: 13px;
  color: #e74c3c;
  margin: 0;
}
```

- [ ] **Step 3: Build verification**

```bash
cd packages/guineapig-client && npx vue-tsc --noEmit && npm run build
```
Expected: TypeScript check passes, build succeeds

- [ ] **Step 4: Commit**

```bash
git add packages/guineapig-client/src/renderer/views/LoginPage.vue
git commit -m "feat(client): integrate backend login API with loading/error states"
```

---

### Task 7: Frontend — Add API Base URL Environment Variable

**Files:**
- Create: `packages/guineapig-client/.env`

- [ ] **Step 1: Create .env file**

Write `packages/guineapig-client/.env`:

```
VITE_API_BASE_URL=http://localhost:6880
```

This allows the backend URL to be changed without modifying code.

- [ ] **Step 2: Add .env to .gitignore if not already there**

Check if `.env` is in `.gitignore`:

```bash
grep -q '\.env' packages/guineapig-client/.gitignore 2>/dev/null && echo "already ignored" || echo "not ignored"
```

If not ignored, add to `.gitignore` or use `.env.local` instead (which is gitignored by default with Create Vue/Vite templates).

- [ ] **Step 3: Commit**

```bash
git add packages/guineapig-client/.env
git commit -m "feat(client): add VITE_API_BASE_URL env var for backend URL"
```

---

### Task 8: Verify Full Build

- [ ] **Step 1: Backend build verification**

```bash
cd packages/guineapig-backend && go build ./...
```
Expected: clean compilation

- [ ] **Step 2: Frontend build verification**

```bash
cd packages/guineapig-client && npx vue-tsc --noEmit && npm run build
```
Expected: TypeScript check passes, Vite build succeeds

- [ ] **Step 3: Automated type check for all three Electron layers**

```bash
cd packages/guineapig-client && npx vue-tsc --noEmit
```
Expected: clean type check

- [ ] **Step 4: Final commit if any fixes were applied**

```bash
git add -A
git commit -m "chore: verify full build pipeline after login feature"
```
