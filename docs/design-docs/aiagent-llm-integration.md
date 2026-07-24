# AIAgent LLM Integration Design

## Metadata
- **Status**: draft
- **Created**: 2026-05-21
- **Package**: guineapig-aiagent
- **Tech**: FastAPI, SenseVoice-Small, CosyVoice2-0.5B, DeepSeek

## Overview
guineapig-aiagent 是系统的 AI 能力核心，负责 ASR 语音识别、LLM 对话驱动、TTS 语音合成。核心流程为 Subagent 多轮循环模式。

## Core Loop: Subagent 多轮循环

```
┌──────────────────────────────────────────────────┐
│                 AIAgent Core Loop                 │
│                                                   │
│  1. Receive task (session_id, user_id, s3_path)  │
│  2. Download audio from S3                       │
│  3. ASR: audio -> text (SenseVoice-Small)        │
│  4. Load context from Redis                      │
│  5. Build prompt (system + context + user input) │
│  6. LLM call (DeepSeek)                          │
│  7. Parse LLM response:                          │
│     - Tool calls -> execute -> loop back to 5    │
│     - Text response -> TTS -> audio              │
│     - Need more input -> return clarification    │
│  8. Update context in Redis                      │
│  9. Upload response audio to S3                  │
│ 10. Report result to Backend                     │
│                                                   │
│  Loop continues until:                           │
│  - LLM returns final response                    │
│  - Max iterations reached                        │
│  - Force stop requested                          │
└──────────────────────────────────────────────────┘
```

## API Endpoints

### Internal API (called by Backend)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/tasks/process` | Process a voice task |
| GET | `/api/v1/tasks/:task_id/status` | Get task processing status |
| POST | `/api/v1/tasks/:task_id/cancel` | Cancel processing |
| GET | `/health` | Health check |

### Request/Response

**POST /api/v1/tasks/process**
```json
// Request
{
  "task_id": "uuid",
  "session_id": "uuid",
  "user_id": 1,
  "s3_path": "/audio/user_1/session_x/input.mp3"
}

// Response (async - returned immediately)
{
  "task_id": "uuid",
  "status": "processing"
}
```

**Task Status Callback to Backend**
```json
{
  "task_id": "uuid",
  "status": "completed",
  "result": {
    "input_text": "今天天气怎么样",
    "output_text": "今天北京天气晴朗，温度20度",
    "output_audio_path": "/audio/user_1/session_x/output_001.mp3",
    "iterations": 3,
    "tokens_used": 1500,
    "duration_ms": 3500
  }
}
```

## LLM Prompt Template

```
System: You are GuineaPig, a voice assistant. You have the following capabilities:
- Answer questions conversationally
- Use tools when needed: {available_tools}
- Keep responses concise (under 20 seconds when spoken)
- If you need more information from the user, ask a clarification question

Context from previous conversation:
{context_summary}

User said: {asr_text}

Respond naturally as a voice assistant.
```

## Context Management

### Redis Data Structure
```
Key: "session:{session_id}:context"
Value: JSON array of messages
TTL: 24 hours (renewed on each interaction)

Key: "session:{session_id}:summary"
Value: Compressed summary of older messages
TTL: 7 days
```

### Context Compression Strategy
1. Keep last 10 messages in full
2. Messages 11-20: keep as compressed summary
3. Messages 21+: archive to S3, only keep summary
4. Run as scheduled task every 1 hour

## Error Handling
1. ASR failure -> retry once, then return error to Backend
2. LLM timeout (30s) -> return partial response or timeout error
3. TTS failure -> return text-only response
4. S3 download/upload failure -> retry 3 times with backoff

## Performance Targets
- ASR processing: < 1s
- LLM response: < 3s
- TTS generation: < 2s
- Total end-to-end: < 6s per iteration
