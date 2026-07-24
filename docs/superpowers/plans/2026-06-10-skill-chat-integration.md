# Skill Chat Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate enabled skills into AI chat flow — backend passes skills to aiagent, aiagent two-phase loads relevant skills into LLM context, LLM can return commands, client shows dialog for user-approved local execution.

**Architecture:** Backend reads `res_skills` and passes to aiagent alongside chat messages. AiAgent Phase 1 asks LLM which skills are relevant, Phase 2 loads skill content into system prompt. LLM can include `<commands>` block in response. Client parses commands, shows risk-leveled dialog, executes via IPC.

**Tech Stack:** Go (Echo/GORM), Python (FastAPI/AsyncOpenAI), TypeScript (Vue3/Electron)

---

### Task 1: Backend — Add skill types, model methods, SSE chunk Commands field

**Files:**
- Modify: `packages/guineapig-backend/internal/response/chat.go`
- Modify: `packages/guineapig-backend/internal/model/res_skills.go`
- Modify: `packages/guineapig-backend/internal/model/chat_message.go`

- [ ] **Step 1: Add SkillInfo and CommandItem to response/chat.go**

Read the file first, then add to the end:
```go
type SkillInfo struct {
    Name        string `json:"name"`
    Description string `json:"description"`
    ObjectKey   string `json:"object_key"`
}

type CommandItem struct {
    Type        string `json:"type"`
    Description string `json:"description"`
    Command     string `json:"command"`
    Cwd         string `json:"cwd,omitempty"`
    Risk        string `json:"risk"`
}
```

Then add `Commands []CommandItem` to `SSEStreamChunk`:
```go
type SSEStreamChunk struct {
    Type      string        `json:"type"`
    Content   string        `json:"content,omitempty"`
    MessageId int64         `json:"messageId,omitempty"`
    Commands  []CommandItem `json:"commands,omitempty"`
}
```

- [ ] **Step 2: Add ListEnabledByUserId to model/res_skills.go**

```go
func (m *ResSkills) ListEnabledByUserId(ctx context.Context, userId int64) ([]ResSkills, error) {
    var list []ResSkills
    err := plugin.GetDB(ctx).
        Where("user_id = ? AND status = 1 AND deleted_at IS NULL", userId).
        Find(&list).Error
    return list, err
}
```

- [ ] **Step 3: Add UpdateCommands to model/chat_message.go**

```go
func (m *ChatMessage) UpdateCommands(ctx context.Context, id int64, commands *string) error {
    return plugin.GetDB(ctx).Model(&ChatMessage{}).
        Where("id = ?", id).
        Update("commands", commands).Error
}
```

- [ ] **Step 4: Run `make validate` in backend**

```bash
cd packages/guineapig-backend && go build ./...
```



### Task 2: Backend — Modify chat_stream.go to read skills and pass to aiagent

**Files:**
- Modify: `packages/guineapig-backend/internal/service/chat_stream.go`

- [ ] **Step 1: Read the full chat_stream.go file**

- [ ] **Step 2: In StreamChatMessage, add skill query before proxyAiAgentStream**

After conversation load and message creation, before proxyAiAgentStream call:
```go
// 查询用户已开启的 skills
var skills []response.SkillInfo
if skillList, err := model.MResSkills.ListEnabledByUserId(ctx, userId); err == nil {
    for _, s := range skillList {
        skills = append(skills, response.SkillInfo{
            Name:        s.Name,
            Description: s.Description,
            ObjectKey:   s.ZipUrl,
        })
    }
}
```

- [ ] **Step 3: Modify proxyAiAgentStream signature and request body**

Add `skills []response.SkillInfo` and `userId int64` to params. In request body JSON building:
```go
if len(skills) > 0 {
    reqMap["skills"] = skills
    reqMap["user_id"] = userId
}
```

Change return to include `commands []response.CommandItem`.

- [ ] **Step 4: Parse commands from SSE done event**

In the SSE parsing loop after `event.Done`:
```go
if event.Commands != nil {
    commands = event.Commands
}
```

- [ ] **Step 5: Save commands to DB and forward to chunkChan**

After proxyAiAgentStream returns:
```go
if len(commands) > 0 {
    cmdJson, _ := json.Marshal(commands)
    cmdStr := string(cmdJson)
    _ = model.MChatMessage.UpdateCommands(ctx, messageId, &cmdStr)
}

// In done chunk
chunkChan <- response.SSEStreamChunk{
    Type:      "done",
    MessageId: messageId,
    Commands:  commands,
}
```

- [ ] **Step 6: Run `go build ./...` to verify**



### Task 3: AiAgent — Add new models to llm_models.py

**Files:**
- Modify: `packages/guineapig-aiagent/app/schemas/llm_models.py`

- [ ] **Step 1: Read the file**

- [ ] **Step 2: Add SkillInfo and CommandItem models**

```python
class SkillInfo(BaseModel):
    name: str
    description: str
    object_key: str

class CommandItem(BaseModel):
    type: str
    description: str
    command: str
    cwd: Optional[str] = None
    risk: str  # "low" | "medium" | "high"
```

- [ ] **Step 3: Add skills and user_id to LLMStreamRequest**

```python
class LLMStreamRequest(BaseModel):
    messages: list[dict]
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2048
    stream: bool = True
    skills: Optional[list[SkillInfo]] = None
    user_id: Optional[int] = None
```



### Task 4: AiAgent — Create skill_load_service.py

**Files:**
- Create: `packages/guineapig-aiagent/app/services/skill_load_service.py`

- [ ] **Step 1: Write the full skill_load_service.py**

```python
"""Skill load service for two-phase skill context loading."""

import json
import os
import re
import shutil
from typing import Optional

from openai import AsyncOpenAI

from app.core.oss_wrapper_utils import download_file_from_oss
from app.core.fileutils import unzip_file
from app.schemas.llm_models import SkillInfo, CommandItem


SKILL_BASE_DIR = "data/skills"
COMMANDS_PATTERN = re.compile(
    r'<commands>\s*(\[[\s\S]*?\])\s*</commands>',
    re.IGNORECASE
)


def _get_skill_dir(user_id: int, skill_name: str) -> str:
    return os.path.join(SKILL_BASE_DIR, str(user_id), skill_name)


def _ensure_skill_extracted(skill: SkillInfo, user_id: int) -> str:
    """Ensure skill is extracted locally, download from S3 if needed."""
    skill_dir = _get_skill_dir(user_id, skill.name)
    if os.path.exists(skill_dir) and os.listdir(skill_dir):
        return skill_dir

    # Download and extract
    os.makedirs(skill_dir, exist_ok=True)
    zip_path = os.path.join(skill_dir, f"{skill.name}.zip")
    try:
        download_file_from_oss(skill.object_key, zip_path)
        unzip_file(zip_path, skill_dir)
    finally:
        if os.path.exists(zip_path):
            os.remove(zip_path)

    return skill_dir


def _read_skill_context(skill_dir: str) -> str:
    """Read SKILL.md and scripts directory content."""
    parts = []

    # Read SKILL.md
    md_path = os.path.join(skill_dir, "SKILL.md")
    if os.path.exists(md_path):
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Strip YAML frontmatter if present
        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                content = content[end + 3:].strip()
        parts.append(f"### Description\n{content}")

    # Read scripts directory
    scripts_dir = os.path.join(skill_dir, "scripts")
    if os.path.exists(scripts_dir) and os.path.isdir(scripts_dir):
        scripts = []
        for fname in os.listdir(scripts_dir):
            fpath = os.path.join(scripts_dir, fname)
            if os.path.isfile(fpath) and fname.endswith((".py", ".sh", ".js", ".md")):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    scripts.append(f"#### `{fname}`\n```\n{content[:2000]}\n```")
                except Exception:
                    scripts.append(f"#### `{fname}`\n(could not read)")
        if scripts:
            parts.append("### Scripts\n" + "\n\n".join(scripts))

    # List all files
    file_list = []
    for root, dirs, files in os.walk(skill_dir):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), skill_dir)
            if not rel.startswith("."):
                file_list.append(rel)
    if file_list:
        parts.append("### Files\n" + "\n".join(f"- `{f}`" for f in file_list[:20]))  # limit to 20

    return "\n\n".join(parts)


async def select_relevant_skills(
    user_message: str,
    skills: list[SkillInfo],
    api_key: str,
    base_url: str,
    model: str
) -> list[str]:
    """Phase 1: Ask LLM to select relevant skills for the user's message."""
    if not skills:
        return []

    skill_list = "\n".join([f"- {s.name}: {s.description}" for s in skills])

    messages = [
        {
            "role": "system",
            "content": (
                "You are a skill selector. Given the user's message and available skills, "
                "determine which skills are relevant. "
                "Return ONLY a JSON array of skill names. "
                "If none are relevant, return an empty array []. "
                "Do not include any other text in your response."
            ),
        },
        {
            "role": "user",
            "content": f"Available skills:\n{skill_list}\n\nUser message: {user_message}",
        },
    ]

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.1,
        max_tokens=500,
    )

    text = response.choices[0].message.content or "[]"
    # Extract JSON array from response
    try:
        # Try to find JSON array in the response
        match = re.search(r'\[.*?\]', text, re.DOTALL)
        if match:
            result = json.loads(match.group(0))
            return [name for name in result if isinstance(name, str)]
    except (json.JSONDecodeError, ValueError):
        pass

    return []


async def load_skill_context(
    skill_names: list[str],
    user_id: int,
    skills: list[SkillInfo]
) -> str:
    """Phase 2: Load full context of selected skills."""
    context_parts = []

    for skill in skills:
        if skill.name not in skill_names:
            continue

        skill_dir = _ensure_skill_extracted(skill, user_id)
        skill_context = _read_skill_context(skill_dir)
        context_parts.append(
            f"## Skill: {skill.name}\n{skill_context}"
        )

    return "\n\n---\n\n".join(context_parts)


def inject_skill_system_prompt(
    messages: list[dict],
    skill_context: str,
    commands_instruction: str = None
) -> list[dict]:
    """Inject skill context and command generation rules into system prompt."""
    if commands_instruction is None:
        commands_instruction = (
            "\n\n## Command Generation Rules\n"
            "If you need to execute commands to fulfill the user's request, "
            "include a commands block at the end of your response. "
            "Each command must include a risk level.\n"
            "- low: Read/query operations (ls, cat, open, read file, API query)\n"
            "- medium: Write/update operations (cp, mv, sed -i, install package, modify config)\n"
            "- high: Delete/destroy operations (rm -rf, drop, del, shutdown, format, clear data)\n\n"
            "Format:\n"
            "<commands>\n"
            '[{"type": "shell", "description": "what this does", '
            '"command": "the actual command", '
            '"cwd": "optional/relative/path", "risk": "low"}]\n'
            "</commands>"
        )

    skill_block = f"\n\n## Available Skills\n{skill_context}\n{commands_instruction}"

    for msg in messages:
        if msg.get("role") == "system":
            msg["content"] += skill_block
            return messages

    # No system message found, prepend one
    messages.insert(0, {"role": "system", "content": skill_block})
    return messages


def parse_commands(full_content: str) -> tuple[str, list[dict]]:
    """Extract commands from LLM response. Returns (clean_content, commands_list)."""
    match = COMMANDS_PATTERN.search(full_content)
    if not match:
        return full_content, []

    try:
        commands_data = json.loads(match.group(1))
        if not isinstance(commands_data, list):
            return full_content, []
        # Validate each command has required fields
        valid = []
        for cmd in commands_data:
            if all(k in cmd for k in ("type", "description", "command", "risk")):
                valid.append({
                    "type": cmd["type"],
                    "description": cmd["description"],
                    "command": cmd["command"],
                    "cwd": cmd.get("cwd", ""),
                    "risk": cmd["risk"],
                })
        commands = valid
    except (json.JSONDecodeError, ValueError):
        return full_content, []

    clean_content = COMMANDS_PATTERN.sub("", full_content).strip()
    return clean_content, commands
```



### Task 5: AiAgent — Modify llm.py router for two-phase flow

**Files:**
- Modify: `packages/guineapig-aiagent/app/routers/llm.py`

- [ ] **Step 1: Read the file completely**

- [ ] **Step 2: Add imports for skill_load_service**

```python
from app.services.skill_load_service import (
    select_relevant_skills,
    load_skill_context,
    inject_skill_system_prompt,
    parse_commands,
)
```

- [ ] **Step 3: Add helper to get last user message**

```python
def _get_last_user_message(messages: list[dict]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return msg.get("content", "")
    return ""
```

- [ ] **Step 4: Modify event_generator for two-phase processing**

In `event_generator`, before the LLM streaming call, add:
```python
# Phase 1: Skill selection
if request.skills and request.user_id:
    user_message = _get_last_user_message(request.messages)
    if user_message:
        try:
            selected_skill_names = await select_relevant_skills(
                user_message=user_message,
                skills=request.skills,
                api_key=request.api_key,
                base_url=request.base_url,
                model=request.model,
            )
            # Phase 2: Load skill context
            if selected_skill_names:
                skill_context = await load_skill_context(
                    skill_names=selected_skill_names,
                    user_id=request.user_id,
                    skills=request.skills,
                )
                request.messages = inject_skill_system_prompt(
                    request.messages, skill_context
                )
        except Exception as e:
            logger.error(f"Skill load failed: {e}")
```

After the LLM streaming loop, before yielding done:
```python
# Parse commands from full response
clean_content, commands = parse_commands(full_content)

result = {"done": True}
if commands:
    result["commands"] = commands
yield result
```

Also ensure the content streamed is the clean content (without commands block). The simplest way: buffer all content chunks, then at the end, send clean content. Or better: send content as-is during streaming (may include commands block temporarily), and at the end yield the done event with clean content. The client uses the final content for display.

Actually the cleanest approach is: stream content normally (the commands block at the end will be streamed as content), but in the done event, send the clean content AND commands. The client will use the done event's content as the final message, ignoring the last few chunks that contained the commands block.

Let me simplify: stream everything as-is. On done, yield `{"done": true, "content": clean_content, "commands": commands}`. The client should use `content` from done event as final content.

So the done event becomes:
```python
clean_content, commands = parse_commands(full_content)
yield {"done": True, "content": clean_content, "commands": commands}
```



### Task 6: Client — Add types and IPC handler for command execution

**Files:**
- Modify: `packages/guineapig-client/src/main/index.ts`
- Modify: `packages/guineapig-client/src/preload/index.ts`
- Modify: `packages/guineapig-client/src/renderer/vite-env.d.ts`

- [ ] **Step 1: Add execute-command IPC handler to main/index.ts**

```typescript
import { exec } from 'child_process'

// In setupIPC() or similar
ipcMain.handle('execute-command', async (event, cmd: {
  type: string
  description: string
  command: string
  cwd?: string
  risk: string
}) => {
  const userDataPath = app.getPath('userData')
  const workingDir = cmd.cwd ? path.join(userDataPath, cmd.cwd) : userDataPath

  return new Promise((resolve) => {
    exec(cmd.command, { cwd: workingDir, timeout: 300000 }, (err, stdout, stderr) => {
      resolve({
        stdout: stdout || '',
        stderr: stderr || '',
        exitCode: err ? (err.code || -1) : 0,
      })
    })
  })
})
```

- [ ] **Step 2: Add executeCommand bridge to preload/index.ts**

```typescript
executeCommand: (cmd) => ipcRenderer.invoke('execute-command', cmd),
```

- [ ] **Step 3: Add types to vite-env.d.ts**

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

// In ElectronAPI interface:
executeCommand: (cmd: CommandItem) => Promise<CommandResult>
```



### Task 7: Client — Add command dialog to ChatPage.vue

**Files:**
- Modify: `packages/guineapig-client/src/renderer/views/ChatPage.vue`

- [ ] **Step 1: Read the full ChatPage.vue file, understand the SSE handling**

- [ ] **Step 2: Add reactive refs for commands state**

```typescript
import { ref } from 'vue'

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

const pendingCommands = ref<CommandItem[]>([])
const showCommandDialog = ref(false)
const commandResults = ref<{ cmd: CommandItem; result: CommandResult }[]>([])
const isExecuting = ref(false)
```

- [ ] **Step 3: Handle commands in SSE done event**

When parsing SSE done event:
```typescript
if (event.commands && event.commands.length > 0) {
  pendingCommands.value = event.commands
  commandResults.value = []
  showCommandDialog.value = true
}
```

- [ ] **Step 4: Add command dialog template in <template> section**

```vue
<Dialog v-model:visible="showCommandDialog"
  header="待执行的命令" modal :draggable="false"
  :style="{ width: '640px' }">

  <div class="command-dialog-body">
    <div v-for="(cmd, i) in pendingCommands" :key="i"
      class="command-item p-mb-2 p-p-3"
      :class="'risk-' + cmd.risk">

      <div class="command-item-header">
        <Tag :value="cmd.type" severity="warn" />
        <span class="command-description">{{ cmd.description }}</span>
        <Tag :value="riskLabel(cmd.risk)" :severity="riskSeverity(cmd.risk)" />
      </div>

      <code class="command-code">{{ cmd.command }}</code>

      <!-- Show result if available -->
      <div v-if="commandResults[i]" class="command-result"
        :class="{ success: commandResults[i].result.exitCode === 0, error: commandResults[i].result.exitCode !== 0 }">
        <div v-if="commandResults[i].result.stdout" class="result-stdout">
          <pre>{{ commandResults[i].result.stdout }}</pre>
        </div>
        <div v-if="commandResults[i].result.stderr" class="result-stderr">
          <pre>{{ commandResults[i].result.stderr }}</pre>
        </div>
      </div>
    </div>
  </div>

  <template #footer>
    <Button v-if="!isExecuting" label="取消" severity="secondary" @click="showCommandDialog = false" />
    <Button v-if="!isExecuting" label="允许执行" @click="executeCommands"
      :class="{ 'p-button-danger': hasHighRiskCommands }" />
    <Button v-else label="执行中..." disabled />
  </template>
</Dialog>
```

- [ ] **Step 5: Add command execution logic**

```typescript
const hasHighRiskCommands = computed(() =>
  pendingCommands.value.some(c => c.risk === 'high')
)

function riskLabel(risk: string): string {
  const map: Record<string, string> = { low: '低风险', medium: '中风险', high: '高风险' }
  return map[risk] || risk
}

function riskSeverity(risk: string): string {
  const map: Record<string, string> = { low: 'success', medium: 'warn', high: 'danger' }
  return map[risk] || 'info'
}

async function executeCommands() {
  isExecuting.value = true
  commandResults.value = []

  for (let i = 0; i < pendingCommands.value.length; i++) {
    const cmd = pendingCommands.value[i]
    try {
      const result = await window.electronAPI.executeCommand(cmd)
      commandResults.value[i] = { cmd, result }
    } catch (e: any) {
      commandResults.value[i] = {
        cmd,
        result: { stdout: '', stderr: e.message || String(e), exitCode: -1 }
      }
    }
  }

  isExecuting.value = false
}
```

- [ ] **Step 6: Add CSS styles**

```css
.command-item {
  border: 1px solid var(--surface-border);
  border-radius: 6px;
  margin-bottom: 8px;
}

.command-item.risk-low { border-left: 3px solid var(--green-500); }
.command-item.risk-medium { border-left: 3px solid var(--yellow-500); }
.command-item.risk-high { border-left: 3px solid var(--red-500); }

.command-item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.command-description {
  flex: 1;
  font-weight: 500;
}

.command-code {
  display: block;
  padding: 6px 10px;
  background: var(--surface-ground);
  border-radius: 4px;
  font-size: 13px;
  word-break: break-all;
}

.command-result { margin-top: 8px; }
.command-result.success pre { color: var(--green-600); }
.command-result.error pre { color: var(--red-600); }
.command-result pre {
  margin: 0;
  font-size: 12px;
  max-height: 100px;
  overflow-y: auto;
  white-space: pre-wrap;
}
```

- [ ] **Step 7: Verify TypeScript passes**



### Task 8: Verify full flow

- [ ] **Step 1: Backend build**

```bash
cd packages/guineapig-backend && go build ./...
```

- [ ] **Step 2: Verify aiagent imports**

```bash
cd packages/guineapig-aiagent && python -c "from app.services.skill_load_service import select_relevant_skills, load_skill_context, parse_commands; print('OK')"
```

- [ ] **Step 3: Verify client types**

```bash
cd packages/guineapig-client && npx tsc --noEmit 2>&1 | head -20
```
