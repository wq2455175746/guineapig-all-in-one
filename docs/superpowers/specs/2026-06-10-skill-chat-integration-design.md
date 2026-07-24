# Skill Chat Integration — Design Spec

Date: 2026-06-10
Status: Draft
Author: Claude

## Summary

Integrate user-enabled skills into the AI chat flow. When a user chats with the AI, the backend reads enabled skills from `res_skills`, passes them to the aiagent. The aiagent runs a two-phase process: (1) ask the LLM which skills are relevant to the user's question, (2) load relevant skill content into the system prompt. If the LLM decides to execute commands, they are returned as a `commands` array alongside the response. The client shows a risk-leveled command dialog for user approval before local execution.

## Data Flow

```
User sends message → Backend StreamChatMessage
  ├─ 1. Query res_skills WHERE user_id=? AND status=1
  ├─ 2. Build skills: [{name, description, object_key}]
  ├─ 3. POST /guineapig-aiagent/llm/chat/stream (messages + skills + user_id)
  │
  ▼
AiAgent event_generator()
  ├─ Phase 1: LLM selects relevant skills by name+description
  ├─ Phase 2: Download & extract selected skills → inject context into system prompt
  ├─ Phase 3: Streaming LLM call with augmented context
  ├─ SSE: content chunks → Backend
  └─ SSE: {done:true, commands:[...]} → Backend
                                         │
                                    Backend saves commands to chat_messages
                                    Forward to client via SSE
                                         │
                                    Client ChatPage
                                    → Pop modal dialog with risk levels
                                    → User clicks "允许执行"
                                    → IPC execute-command
                                    → Electron main process runs command
                                    → Show result in dialog
```

## Commands Data Structure

```typescript
interface CommandItem {
  type: 'shell' | 'python' | 'npx'
  description: string      // Human-readable description for dialog display
  command: string          // Full CLI command (e.g. "open https://...", "python3 script.py")
  cwd?: string             // Optional working directory (relative to userData/)
  risk: 'low' | 'medium' | 'high'
}
```

Risk classification (by LLM, guided by system prompt):
- `low` — Read/query operations: `ls`, `cat`, `open`, read file, API query
- `medium` — Write/update operations: `cp`, `mv`, `sed -i`, install package, modify config
- `high` — Delete/destroy operations: `rm -rf`, `drop`, `del`, `shutdown`, `format`, clear data

## Backend Changes

### New Model Method: `internal/model/res_skills.go`

```go
func (m *ResSkills) ListEnabledByUserId(ctx context.Context, userId int64) ([]ResSkills, error)
```

Query: `WHERE user_id = ? AND status = 1 AND deleted_at IS NULL`

### New Response Types: `internal/response/chat.go`

```go
type SkillInfo struct {
    Name        string `json:"name"`
    Description string `json:"description"`
    ObjectKey   string `json:"object_key"`       // S3 key from res_skills.zip_url
}

type CommandItem struct {
    Type        string `json:"type"`
    Description string `json:"description"`
    Command     string `json:"command"`
    Cwd         string `json:"cwd,omitempty"`
    Risk        string `json:"risk"`
}

type SSEStreamChunk struct {
    Type      string        `json:"type"`
    Content   string        `json:"content,omitempty"`
    MessageId int64         `json:"messageId,omitempty"`
    Commands  []CommandItem `json:"commands,omitempty"`  // NEW
}
```

### Modified: `internal/service/chat_stream.go`

**`StreamChatMessage()` changes:**
1. Before `proxyAiAgentStream()`, query enabled skills via `model.MResSkills.ListEnabledByUserId()`
2. Build `[]response.SkillInfo` (name, description, object_key)
3. Pass to `proxyAiAgentStream()`

**`proxyAiAgentStream()` changes:**
1. Accept new params: `skills []response.SkillInfo`, `userId int64`
2. Add `"skills"` and `"user_id"` to request JSON body
3. Parse `"commands"` from SSE done event
4. Return `commands []CommandItem` alongside full content

**After stream completes:**
1. If commands exist, marshal to JSON and call `model.MChatMessage.UpdateCommands()`
2. Send commands to SSE chunk channel in the "done" chunk

### New Model Method: `internal/model/chat_message.go`

```go
func (m *ChatMessage) UpdateCommands(ctx context.Context, id int64, commands *string) error
```

Update `chat_messages SET commands = ? WHERE id = ?`.

### Files Changed (Backend)

| File | Action |
|------|--------|
| `internal/service/chat_stream.go` | Add skill query + pass to aiagent + parse/save commands |
| `internal/response/chat.go` | Add CommandItem, add Commands to SSEStreamChunk |
| `internal/model/res_skills.go` | Add ListEnabledByUserId |
| `internal/model/chat_message.go` | Add UpdateCommands |

## AiAgent Changes

### New Schema Models: `app/schemas/llm_models.py`

```python
class SkillInfo(BaseModel):
    name: str
    description: str
    object_key: str       # S3 key: skills/{userId}/{date}/{name}.zip

class CommandItem(BaseModel):
    type: str
    description: str
    command: str
    cwd: Optional[str] = None
    risk: str             # "low" | "medium" | "high"

class LLMStreamRequest(BaseModel):
    # ... existing fields ...
    skills: Optional[list[SkillInfo]] = None
    user_id: Optional[int] = None
```

### New Service: `app/services/skill_load_service.py`

**Phase 1 — `select_relevant_skills()`:**

```python
async def select_relevant_skills(
    user_message: str,
    skills: list[SkillInfo],
    api_key: str,
    base_url: str,
    model: str
) -> list[str]:
```

- Build compact prompt with user message + available skill names+descriptions
- Call LLM with low temperature (0.1) for deterministic selection
- Parse response as JSON array of skill names
- Return empty list if no skills relevant or parsing fails

**Phase 2 — `load_skill_context()`:**

```python
async def load_skill_context(
    skill_names: list[str],
    user_id: int,
    skills: list[SkillInfo]
) -> str:
```

- For each selected skill, check if `data/skills/{userId}/{skillName}/` exists locally
- If not, download zip from S3 (using object_key) and extract
- Read SKILL.md and scripts/ directory content
- Build a formatted context string with skill name, description, and available scripts

**Commands parsing — `parse_commands()`:**

```python
def parse_commands(full_content: str) -> tuple[str, list[CommandItem]]:
```

- Regex match `<commands>[...JSON...]</commands>` block
- Parse JSON array into CommandItem objects
- Remove the `<commands>` block from content
- Return (clean_content, commands)

### Modified Router: `app/routers/llm.py`

**`event_generator()` changes:**
1. Phase 1: If `request.skills` present, call `select_relevant_skills()`
2. Phase 2: If selected skills, call `load_skill_context()` and inject into system prompt
3. Phase 3: Existing streaming LLM call (unchanged)
4. After stream completes: `parse_commands(full_content)`
5. Yield `{"done": true, "commands": [...]}` with the filtered content via SSE

**System prompt injection** adds at the end of existing system prompt:

```
## Available Skills
{skill_context}

## Command Generation Rules
If you need to execute commands to fulfill the user's request, include a commands block at the end of your response. Each command must include a risk level.
- low: Read/query operations (ls, cat, open, read file, API query)
- medium: Write/update operations (cp, mv, sed -i, install package, modify config)
- high: Delete/destroy operations (rm -rf, drop, del, shutdown, format, clear data)

Format:
<commands>
[{"type": "shell", "description": "what this does", "command": "the actual command", "cwd": "optional/relative/path", "risk": "low"}]
</commands>
```

### Files Changed (AiAgent)

| File | Action |
|------|--------|
| `app/schemas/llm_models.py` | Add SkillInfo, CommandItem, fields to LLMStreamRequest |
| `app/services/skill_load_service.py` | **New** — Phase 1 + Phase 2 + commands parse |
| `app/routers/llm.py` | Modify event_generator for two-phase flow |

## Client Changes

### Modified: `src/renderer/views/ChatPage.vue`

**SSE event handling:**
- On `done` event, check for `commands` array
- If commands present, store in reactive ref `pendingCommands`
- Pop modal dialog (PrimeVue Dialog) with risk-leveled command list

**Command dialog template:**
```
Dialog (title: "待执行的命令", width: 640px)
  ┌─────────────────────────────────────────────────┐
  │ [shell] 查询文件列表     ls -la          [低风险] │
  │ [python] 运行分析脚本   python3 analyze.py [中风险] │
  │ [shell] 删除临时文件    rm -rf /tmp/x    [高风险] │
  │                                                 │
  │           [取消]          [允许执行]              │
  └─────────────────────────────────────────────────┘
```

- `low` → Tag severity `success`, green
- `medium` → Tag severity `warn`, yellow
- `high` → Tag severity `danger`, red + extra confirmation step
  - Click "允许执行" → if any high-risk commands → confirm dialog "包含高风险操作，确认执行？"
  - After second confirmation → proceed

**Execution flow:**
```typescript
async function executeCommands() {
  // Check for high-risk commands
  if (commands.value.some(c => c.risk === 'high')) {
    const confirmed = await confirm.require({ message: '包含高风险操作，确认执行？' })
    if (!confirmed) return
  }

  for (const cmd of commands.value) {
    const result = await window.electronAPI.executeCommand(cmd)
    appendResult(cmd, result)
  }
}
```

### New IPC Handler: `src/main/index.ts`

```typescript
ipcMain.handle('execute-command', async (event, cmd: CommandItem) => {
  const userDataPath = app.getPath('userData')
  const workingDir = cmd.cwd ? path.join(userDataPath, cmd.cwd) : userDataPath

  const { exec } = require('child_process')
  return new Promise((resolve) => {
    exec(cmd.command, { cwd: workingDir, timeout: 300000 }, (err, stdout, stderr) => {
      resolve({
        stdout: stdout || '',
        stderr: stderr || '',
        exitCode: err ? (err.code || -1) : 0
      })
    })
  })
})
```

### New Preload Bridge: `src/preload/index.ts`

```typescript
executeCommand: (cmd: CommandItem) => ipcRenderer.invoke('execute-command', cmd),
```

### New Type Declarations: `src/renderer/vite-env.d.ts`

```typescript
interface CommandItem {
  type: string
  description: string
  command: string
  cwd?: string
  risk: 'low' | 'medium' | 'high'
}

interface CommandResult {
  stdout: string
  stderr: string
  exitCode: number
}

interface ElectronAPI {
  executeCommand: (cmd: CommandItem) => Promise<CommandResult>
  // ... existing
}
```

### Files Changed (Client)

| File | Action |
|------|--------|
| `src/renderer/views/ChatPage.vue` | Add command dialog + SSE commands handling + execution |
| `src/main/index.ts` | Add execute-command IPC handler |
| `src/preload/index.ts` | Expose executeCommand bridge |
| `src/renderer/vite-env.d.ts` | Add CommandItem/CommandResult types |

## Error Handling

- No enabled skills → skip Phase 1+2, normal chat flow
- Phase 1 LLM call fails → skip to normal chat (degrade gracefully)
- Phase 2 S3 download/extract fails → log error, skip that skill only
- Commands parse fails → return content as-is without commands
- Client command execution fails → show error result in dialog, continue next command
- IPC handler timeout → return timeout error after 5 minutes

## Security

- Commands are NOT auto-executed — always require user approval via dialog
- High-risk commands require a second confirmation
- Commands run with the Electron app's user permissions (no sudo escalation)
- The `cwd` is always resolved relative to `userDataPath` (no arbitrary path traversal)
- Commands are logged for audit but never contain secrets from the chat context
- The aiagent never executes commands directly — only generates them
