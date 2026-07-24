# AI Model Connectivity Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) for syntax tracking.

**Goal:** Add a backend API to test AI model connectivity, add test buttons in frontend add dialog and action column, sync `established` field to DB.

**Architecture:** Backend gets a new `POST /aimodel/test` endpoint that sends a minimal chat request to the AI provider's API. Backend also gets a `POST /aimodel/decrypt-key` endpoint for frontend to decrypt stored keys. The `Established` field gap in the update flow is fixed. Frontend gets test buttons in the add dialog and action column.

**Tech Stack:** Go (Echo, net/http), Vue 3 (PrimeVue), GORM

---

### Task 1: Fix Established Field in Update Flow

**Files:**
- Modify: `packages/guineapig-backend/internal/request/aimodel.go:14-23`
- Modify: `packages/guineapig-backend/internal/service/aimodel.go:101-112`
- Modify: `packages/guineapig-backend/internal/model/user_aimodel.go:43-61`

- [ ] **Step 1: Add `Established` to `AiModelUpdateRequest` in request/aimodel.go**

Edit `packages/guineapig-backend/internal/request/aimodel.go` — add `Established int8` field to `AiModelUpdateRequest` struct:

```go
type AiModelUpdateRequest struct {
	Id           int64  `json:"id"`
	UserId       int64  `json:"user_id"`
	ModelName    string `json:"model_name"`
	ApiUrl       string `json:"api_url"`
	ApiKey       string `json:"api_key"`
	ProviderCode string `json:"provider_code"`
	ModelType    string `json:"model_type"`
	Status       int8   `json:"status"`
	Established  int8   `json:"established"`
}
```

- [ ] **Step 2: Pass `Established` in update service in service/aimodel.go**

Edit `packages/guineapig-backend/internal/service/aimodel.go` — add `Established: req.Established` to the model struct inside `UpdateAiModel` (between lines 108 and 109):

```go
	m := &model.UserAiModel{
		Id:           req.Id,
		ApiUrl:       req.ApiUrl,
		ApiKey:       req.ApiKey,
		ProviderCode: req.ProviderCode,
		ModelType:    req.ModelType,
		ModelName:    req.ModelName,
		Status:       req.Status,
		Established:  req.Established,
	}
```

- [ ] **Step 3: Add `established` to the update map in model/user_aimodel.go**

Edit `packages/guineapig-backend/internal/model/user_aimodel.go` — add `"established": m.Established` to the `updates` map inside `Update`:

```go
	updates := map[string]any{
		"model_name":    m.ModelName,
		"api_url":       m.ApiUrl,
		"provider_code": m.ProviderCode,
		"model_type":    m.ModelType,
		"status":        m.Status,
		"established":   m.Established,
		"updated_at":    m.UpdatedAt,
	}
```

- [ ] **Step 4: Build check**

Run: `cd /Users/haoguangwang/DOC/workspace/guineapig-all-in-one/packages/guineapig-backend && go build ./...`

Expected: Build succeeds with no errors.

- [ ] **Step 5: Commit**

```bash
cd /Users/haoguangwang/DOC/workspace/guineapig-all-in-one
git add packages/guineapig-backend/internal/request/aimodel.go packages/guineapig-backend/internal/service/aimodel.go packages/guineapig-backend/internal/model/user_aimodel.go
git commit -m "fix: add Established field to AI model update flow"
```

---

### Task 2: Add Decrypt-Key Endpoint

**Files:**
- Create: `packages/guineapig-backend/internal/router/aimodel/decrypt_key.go`
- Modify: `packages/guineapig-backend/internal/router/router.go:22`

- [ ] **Step 1: Create decrypt-key handler**

Create `packages/guineapig-backend/internal/router/aimodel/decrypt_key.go`:

```go
package aimodel

import (
	"errors"
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	"guineapig/pkg/utils"

	"github.com/labstack/echo/v4"
)

type decryptKeyRequest struct {
	Id     int64 `json:"id"`
	UserId int64 `json:"user_id"`
}

type decryptKeyResponse struct {
	ApiKey string `json:"api_key"`
}

func DecryptKey(e echo.Context) error {
	ctx := utils.NewContext(e)
	var req decryptKeyRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}
	if req.Id <= 0 {
		return common.ResponseParamError(e, errors.New("id 不能为空"))
	}
	if req.UserId <= 0 {
		return common.ResponseParamError(e, errors.New("user_id 不能为空"))
	}

	apiKey, err := service.DecryptApiKey(ctx, req.Id, req.UserId)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, &decryptKeyResponse{ApiKey: apiKey})
}
```

- [ ] **Step 2: Register route in router.go**

Edit `packages/guineapig-backend/internal/router/router.go` — add decrypt-key route after the list route (line 22):

```go
	AddPostRouter("/aimodel/decrypt-key", aimodel.DecryptKey)
```

- [ ] **Step 3: Build check**

Run: `cd /Users/haoguangwang/DOC/workspace/guineapig-all-in-one/packages/guineapig-backend && go build ./...`

Expected: Build succeeds.

- [ ] **Step 4: Commit**

```bash
cd /Users/haoguangwang/DOC/workspace/guineapig-all-in-one
git add packages/guineapig-backend/internal/router/aimodel/decrypt_key.go packages/guineapig-backend/internal/router/router.go
git commit -m "feat: add decrypt-key endpoint for AI model API key"
```

---

### Task 3: Create Test Connection Endpoint

**Files:**
- Create: `packages/guineapig-backend/internal/router/aimodel/test.go`
- Modify: `packages/guineapig-backend/internal/router/router.go:23`

- [ ] **Step 1: Create test connection handler**

Create `packages/guineapig-backend/internal/router/aimodel/test.go`:

```go
package aimodel

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"guineapig/internal/router/common"

	"github.com/labstack/echo/v4"
)

type testRequest struct {
	ApiUrl       string `json:"api_url"`
	ApiKey       string `json:"api_key"`
	ModelName    string `json:"model_name"`
	ProviderCode string `json:"provider_code"`
}

type testResponse struct {
	Connected bool   `json:"connected"`
	Message   string `json:"message,omitempty"`
}

func TestConnection(e echo.Context) error {
	var req testRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}
	if req.ApiUrl == "" {
		return common.ResponseParamError(e, errors.New("api_url 不能为空"))
	}
	if req.ApiKey == "" {
		return common.ResponseParamError(e, errors.New("api_key 不能为空"))
	}
	if req.ModelName == "" {
		return common.ResponseParamError(e, errors.New("model_name 不能为空"))
	}

	result := doTest(req)
	return common.ResponseOk(e, result)
}

func doTest(req testRequest) *testResponse {
	apiURL := strings.TrimRight(req.ApiUrl, "/")

	var reqBody []byte
	var err error

	// Anthropic uses a different API format
	if req.ProviderCode == "Anthropic" {
		reqBody, err = buildAnthropicBody(req.ModelName)
	} else {
		reqBody, err = buildOpenAIBody(req.ModelName)
	}
	if err != nil {
		return &testResponse{Connected: false, Message: fmt.Sprintf("构建请求失败: %v", err)}
	}

	var targetURL string
	if req.ProviderCode == "Anthropic" {
		targetURL = apiURL + "/v1/messages"
	} else {
		targetURL = apiURL + "/chat/completions"
	}

	httpReq, err := http.NewRequest("POST", targetURL, bytes.NewReader(reqBody))
	if err != nil {
		return &testResponse{Connected: false, Message: fmt.Sprintf("创建请求失败: %v", err)}
	}

	httpReq.Header.Set("Content-Type", "application/json")
	if req.ProviderCode == "Anthropic" {
		httpReq.Header.Set("x-api-key", req.ApiKey)
		httpReq.Header.Set("anthropic-version", "2023-06-01")
	} else {
		httpReq.Header.Set("Authorization", "Bearer "+req.ApiKey)
	}

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(httpReq)
	if err != nil {
		return &testResponse{Connected: false, Message: fmt.Sprintf("连接失败: %v", err)}
	}
	defer resp.Body.Close()

	_, _ = io.Copy(io.Discard, resp.Body)

	if resp.StatusCode >= 200 && resp.StatusCode < 300 {
		return &testResponse{Connected: true}
	}

	return &testResponse{
		Connected: false,
		Message:   fmt.Sprintf("请求失败，HTTP状态码: %d", resp.StatusCode),
	}
}

func buildOpenAIBody(modelName string) ([]byte, error) {
	body := map[string]interface{}{
		"model": modelName,
		"messages": []map[string]string{
			{"role": "user", "content": "Hello!"},
		},
		"stream": false,
	}
	return json.Marshal(body)
}

func buildAnthropicBody(modelName string) ([]byte, error) {
	body := map[string]interface{}{
		"model":      modelName,
		"max_tokens": 256,
		"messages": []map[string]string{
			{"role": "user", "content": "Hello!"},
		},
	}
	return json.Marshal(body)
}
```

- [ ] **Step 2: Register route in router.go**

Edit `packages/guineapig-backend/internal/router/router.go` — add test route after decrypt-key:

```go
	AddPostRouter("/aimodel/test", aimodel.TestConnection)
```

The router.go should look like:

```go
	// AI模型相关
	AddPostRouter("/aimodel/create", aimodel.Create)
	AddPostRouter("/aimodel/update", aimodel.Update)
	AddPostRouter("/aimodel/delete", aimodel.Delete)
	AddGetRouter("/aimodel/list", aimodel.List)
	AddPostRouter("/aimodel/decrypt-key", aimodel.DecryptKey)
	AddPostRouter("/aimodel/test", aimodel.TestConnection)
```

- [ ] **Step 3: Build check**

Run: `cd /Users/haoguangwang/DOC/workspace/guineapig-all-in-one/packages/guineapig-backend && go build ./...`

Expected: Build succeeds.

- [ ] **Step 4: Commit**

```bash
cd /Users/haoguangwang/DOC/workspace/guineapig-all-in-one
git add packages/guineapig-backend/internal/router/aimodel/test.go packages/guineapig-backend/internal/router/router.go
git commit -m "feat: add AI model test connection endpoint"
```

---

### Task 4: Frontend — Add Test Button in Dialog + Established Column

**File:**
- Modify: `packages/guineapig-client/src/renderer-overlay/views/ResourcePage.vue`

- [ ] **Step 1: Add testing states and test function**

Add new reactive refs after line 313 (`const submitting = ref(false)`):

```ts
const testingConnection = ref(false)
```

Add the test connection function after `cancelChangeApiKey` function (after line 364):

```ts
async function testConnection(): Promise<void> {
  if (!formData.api_url || !formData.model_name) {
    toast.add({ severity: 'warn', summary: '请填写URL和模型名称', detail: '测试连接需要URL和模型名称', life: 2000 })
    return
  }
  if (dialogMode.value === 'edit' && !changingApiKey.value && !formData.api_key) {
    // 编辑模式且未更换密钥，需要先解密
    try {
      const res = await fetch(`${API_BASE_URL}/aimodel/decrypt-key`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: editingId.value, user_id: userId })
      })
      const data = await res.json()
      if (data.code !== 0 || !data.result?.api_key) {
        toast.add({ severity: 'error', summary: '测试失败', detail: '无法获取API Key', life: 3000 })
        return
      }
      formData.api_key = data.result.api_key
    } catch (err) {
      toast.add({ severity: 'error', summary: '请求失败', detail: String(err), life: 3000 })
      return
    }
  }

  testingConnection.value = true
  try {
    const res = await fetch(`${API_BASE_URL}/aimodel/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        api_url: formData.api_url,
        api_key: formData.api_key,
        model_name: formData.model_name,
        provider_code: formData.provider_code
      })
    })
    const data = await res.json()
    if (data.code !== 0) {
      toast.add({ severity: 'error', summary: '测试失败', detail: data.message, life: 3000 })
      return
    }
    if (data.result?.connected) {
      toast.add({ severity: 'success', summary: '连接成功', detail: '模型可以正常连通', life: 3000 })
    } else {
      toast.add({ severity: 'error', summary: '连接失败', detail: data.result?.message || '未知错误', life: 3000 })
    }
  } catch (err) {
    toast.add({ severity: 'error', summary: '请求失败', detail: String(err), life: 3000 })
  } finally {
    testingConnection.value = false
  }
}
```

- [ ] **Step 2: Add test button in dialog template**

Edit the template — add a "测试连接" field after the API Key field (after line 101, before the Status field at line 103):

```html
        <div class="field">
          <label class="field-label">测试连接</label>
          <Button label="测试连接" icon="pi pi-send" severity="info" outlined size="small"
            @click="testConnection" :loading="testingConnection" :disabled="!formData.api_url || !formData.model_name" />
        </div>
```

- [ ] **Step 3: Add established column in data table**

Edit the template — add a column after "模型类型" column (after line 33, before the status column at line 34):

```html
              <Column header="连通状态">
                <template #body="{ data }">
                  <div style="display: flex; align-items: center; gap: 4px;">
                    <i v-if="data.established === 1" class="pi pi-check-circle" style="color: #22c55e; font-size: 14px;"></i>
                    <i v-else class="pi pi-minus-circle" style="color: #d0d5dd; font-size: 14px;"></i>
                    <span :style="{ color: data.established === 1 ? '#22c55e' : '#999', fontSize: '13px' }">
                      {{ data.established === 1 ? '已连通' : '未测试' }}
                    </span>
                  </div>
                </template>
              </Column>
```

- [ ] **Step 4: Build check**

Run: `cd /Users/haoguangwang/DOC/workspace/guineapig-all-in-one/packages/guineapig-client && npx vue-tsc --noEmit 2>&1 || echo "Type check skipped if vue-tsc not available"`

Expected: No type errors (or skip if vue-tsc not configured).

- [ ] **Step 5: Commit**

```bash
cd /Users/haoguangwang/DOC/workspace/guineapig-all-in-one
git add packages/guineapig-client/src/renderer-overlay/views/ResourcePage.vue
git commit -m "feat: add test connection button in dialog and established column"
```

---

### Task 5: Frontend — Implement Action Column Test Button

**File:**
- Modify: `packages/guineapig-client/src/renderer-overlay/views/ResourcePage.vue`

- [ ] **Step 1: Implement `handleTestConnection` function**

Replace the placeholder `handleTestConnection` function (lines 410-412) with:

```ts
async function handleTestConnection(data: AiModelItem) {
  // 先解密获取 API Key
  let decryptedKey = ''
  try {
    const res = await fetch(`${API_BASE_URL}/aimodel/decrypt-key`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: data.id, user_id: userId })
    })
    const r = await res.json()
    if (r.code !== 0 || !r.result?.api_key) {
      toast.add({ severity: 'error', summary: '测试失败', detail: '无法获取API Key', life: 3000 })
      return
    }
    decryptedKey = r.result.api_key
  } catch (err) {
    toast.add({ severity: 'error', summary: '请求失败', detail: String(err), life: 3000 })
    return
  }

  // 测试连接
  try {
    const res = await fetch(`${API_BASE_URL}/aimodel/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        api_url: data.api_url,
        api_key: decryptedKey,
        model_name: data.model_name,
        provider_code: data.provider_code
      })
    })
    const r = await res.json()
    if (r.code !== 0) {
      toast.add({ severity: 'error', summary: '测试失败', detail: r.message, life: 3000 })
      return
    }
    if (r.result?.connected) {
      toast.add({ severity: 'success', summary: '连接成功', detail: '模型可以正常连通', life: 3000 })
      // 更新 established 字段
      const updateRes = await fetch(`${API_BASE_URL}/aimodel/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: data.id, user_id: userId, established: 1 })
      })
      const updateData = await updateRes.json()
      if (updateData.code === 0) {
        fetchList() // 刷新列表
      }
    } else {
      toast.add({ severity: 'error', summary: '连接失败', detail: r.result?.message || '未知错误', life: 3000 })
    }
  } catch (err) {
    toast.add({ severity: 'error', summary: '请求失败', detail: String(err), life: 3000 })
  }
}
```

- [ ] **Step 2: Build check**

Run: `cd /Users/haoguangwang/DOC/workspace/guineapig-all-in-one/packages/guineapig-client && npx vue-tsc --noEmit 2>&1 || echo "Type check skipped"`

Expected: No type errors.

- [ ] **Step 3: Commit**

```bash
cd /Users/haoguangwang/DOC/workspace/guineapig-all-in-one
git add packages/guineapig-client/src/renderer-overlay/views/ResourcePage.vue
git commit -m "feat: implement action column test connection button"
```

---

### Task 6: Final Verification

- [ ] **Step 1: Full Go build**

```bash
cd /Users/haoguangwang/DOC/workspace/guineapig-all-in-one/packages/guineapig-backend
go build ./...
```

Expected: Build succeeds with no errors.

- [ ] **Step 2: Go vet**

```bash
cd /Users/haoguangwang/DOC/workspace/guineapig-all-in-one/packages/guineapig-backend
go vet ./...
```

Expected: No warnings.

- [ ] **Step 3: Verify commit log**

```bash
cd /Users/haoguangwang/DOC/workspace/guineapig-all-in-one
git log --oneline -6
```

Expected: 5-6 clean commits with meaningful messages.
