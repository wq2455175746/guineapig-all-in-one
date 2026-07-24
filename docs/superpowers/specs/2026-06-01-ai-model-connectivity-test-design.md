# AI Model Connectivity Test — Design Spec

Date: 2026-06-01
Status: Approved
Author: Claude

## Summary

Add a backend API endpoint to test AI model connectivity by sending a minimal chat completion request, wire it into the frontend's add dialog (optional test button) and action column (update `established` field), and fix the `established` field gap in the update flow.

## Architecture

### Backend: POST /aimodel/test

**New handler file:** `packages/guineapig-backend/internal/router/aimodel/test.go`

**Request:**
```json
{
  "api_url": "https://api.deepseek.com",
  "api_key": "sk-xxx",
  "model_name": "deepseek-v4-pro",
  "provider_code": "DeepSeek"
}
```

**Response (success):**
```json
{
  "code": 0,
  "message": "success",
  "result": { "connected": true },
  "requestId": "..."
}
```

**Response (failure):**
```json
{
  "code": 0,
  "message": "success",
  "result": { "connected": false, "message": "connection refused" },
  "requestId": "..."
}
```

Note: Business-level success/failure is in the `result` object, not the top-level `code`. The HTTP endpoint always returns 200; the error code is for system-level errors only.

**Logic:**
1. Validate required fields (api_url, api_key, model_name)
2. Trim trailing slash from api_url
3. Determine API format by provider_code:
   - `Anthropic`: POST `{api_url}/v1/messages` with Anthropic Messages API format
   - Default (OpenAI-compatible: DeepSeek, OpenAI, Qwen, Other): POST `{api_url}/chat/completions` with standard OpenAI chat format
4. Send HTTP request with 10s timeout
5. Check response status code 2xx → `connected: true`
6. Any error (timeout, connection refused, non-2xx) → `connected: false` with error message
7. Do NOT store any state in this endpoint — purely a proxy/test

**Route registration:** Add `POST /aimodel/test` in router.go

### Backend: Fix Established Field in Update Flow

**Files to modify:**

1. `internal/request/aimodel.go` — Add `Established int8` to `AiModelUpdateRequest`
2. `internal/service/aimodel.go` — Pass `req.Established` to the update model struct in `UpdateAiModel`
3. `internal/model/user_aimodel.go` — Add `established` to the update map in `UserAiModel.Update()`

### Frontend: ResourcePage.vue Changes

#### Add Dialog — Test Connection Button
- Add a "测试连接" button between API Key field and Status switch
- On click:
  - In add mode: use the plaintext key from form
  - In edit mode with existing key (no change): call `/aimodel/decrypt-key` first to get decrypted key
  - In edit mode with new key: use the new plaintext key
- Call `POST /aimodel/test` with form's api_url, api_key, model_name, provider_code
- Show loading spinner on button during request
- On success (`connected: true`): show PrimeVue success toast "模型连接成功", track `testPassed = true`
- On failure (`connected: false`): show error toast with the message from backend
- Test is optional — save button is always enabled regardless of test result

#### Action Column — Test Button
- Replace `console.log` placeholder with actual flow:
  1. Call `/aimodel/decrypt-key` to get decrypted API key (the list API returns `"***"`)
  2. Call `POST /aimodel/test` with model's api_url, decrypted key, model_name, provider_code
  3. Show loading spinner on button during request
  4. On success (`connected: true`):
     - Show success toast
     - Call `POST /aimodel/update` with `{ id, user_id, established: 1 }` to persist connection status
     - Refresh the list
  5. On failure: show error toast, do NOT update established

#### Data Table — New Column
- Add a column between "模型类型" and "状态":
  - Header: "连通状态"
  - Display: green checkmark icon + "已连通" when `established == 1`, gray X icon + "未测试" when `established == 0`

## Files Changed

### Backend (4 files)
| File | Action |
|------|--------|
| `router/router.go` | Add route `POST /aimodel/test` |
| `router/aimodel/test.go` | **New** — handler + HTTP client logic |
| `request/aimodel.go` | Add `Established int8` to `AiModelUpdateRequest` |
| `service/aimodel.go` | Pass `Established` in update |
| `model/user_aimodel.go` | Add `established` to update map |

### Frontend (1 file)
| File | Action |
|------|--------|
| `ResourcePage.vue` | Add test button in dialog, implement action test, add established column |

## Error Handling

- If the add dialog test fails, the user can still save (optional test)
- If the action column test fails, established is NOT updated
- Network errors (timeout, DNS failure) are shown as toast messages with the raw error from backend
- The backend test endpoint itself should never panic — handle all HTTP client errors gracefully

## Security

- The test endpoint receives API keys in plaintext (they must be decrypted by the frontend first using the existing decrypt-key endpoint)
- The key is only used in-memory to make the HTTP request, never logged or stored by the test endpoint
- The decrypted key from `/aimodel/decrypt-key` is used only in the frontend's in-memory flow, never stored
