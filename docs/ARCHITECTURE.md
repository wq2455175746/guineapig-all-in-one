# GuineaPig Architecture

## Layer Definitions

```
┌─────────────────────────────────────────────┐
│  Layer 4: Presentation                       │
│  guineapig-client (Electron+Vue)            │  桌面客户端
│  guineapig-ops-web (Vue3+Vite+ElementPlus)  │  运营管理 Web
├─────────────────────────────────────────────┤
│  Layer 3: Business                           │
│  guineapig-backend (Go+Echo v4+GORM)        │  业务编排层
├─────────────────────────────────────────────┤
│  Layer 2: AI Capability                      │
│  guineapig-aiagent (FastAPI)                │  AI 能力服务
├─────────────────────────────────────────────┤
│  Layer 1: Infrastructure                     │
│  MySQL / Redis / S3 (MinIO)                 │  数据存储
└─────────────────────────────────────────────┘
```

## Dependency Rules

### Layer Communication
1. **Layer 4 -> Layer 3**: HTTP REST / WebSocket only. No shared code.
2. **Layer 3 -> Layer 2**: HTTP REST / gRPC only. Backend never imports AI libraries.
3. **Layer 2 -> Layer 1**: Direct access to S3 (read audio). Redis for context cache.
4. **Layer 3 -> Layer 1**: Direct access to MySQL (business data) and Redis (session/cache).

### Forbidden Dependencies
- ❌ Backend directly importing `openai`, `anthropic`, `langchain`, or any AI/ML library
- ❌ Frontend/Client directly calling AIAgent (must go through Backend)
- ❌ Cross-package `internal/` imports between packages
- ❌ AIAgent directly writing to MySQL (must go through Backend API)

### Allowed Dependencies
- ✅ Backend calling AIAgent via HTTP for ASR/TTS/LLM tasks
- ✅ Client/OpsWeb calling Backend for all business operations
- ✅ AIAgent reading from S3 for audio files
- ✅ AIAgent reading/writing Redis for conversation context

## Tech Stack Per Package

### guineapig-backend
| Component | Technology | Purpose |
|-----------|-----------|---------|
| Language | Go 1.24.0 | Backend service |
| HTTP | Echo v4 | REST API framework |
| ORM | GORM | MySQL database access |
| Cache | go-redis | Redis caching |
| Config | Viper | YAML + .env configuration |
| Logging | Zap | Structured logging |

### guineapig-aiagent
| Component | Technology | Purpose |
|-----------|-----------|---------|
| Language | Python 3.11+ | AI service |
| HTTP | FastAPI | REST API framework |
| ASR | SenseVoice-Small | Speech recognition |
| TTS | CosyVoice2-0.5B | Speech synthesis |
| LLM | DeepSeek API | Language model |
| Protocol | MCP + Agent Skills | AI agent framework |

### guineapig-ops-web
| Component | Technology | Purpose |
|-----------|-----------|---------|
| Language | JavaScript | Web frontend |
| Framework | Vue 3 + Vite | UI framework |
| UI Kit | Element Plus | Component library |
| Charts | ECharts | Data visualization |

### guineapig-client
| Component | Technology | Purpose |
|-----------|-----------|---------|
| Language | JavaScript | Desktop client |
| Framework | Electron + Vue 3 | Desktop + UI |
| Audio | Web Audio API | Audio recording |

## Data Flow

### Core Voice Dialogue Flow (async, MVP)
```
1. Client records MP3 audio
2. Client uploads MP3 to S3
3. Client POST /api/v1/tasks to Backend (user_id, s3_path, task_id)
4. Backend inserts task record into MySQL (status=pending)
5. Backend POST /api/v1/tasks/process to AIAgent (session_id, user_id, s3_path)
6. AIAgent:
   a. Downloads audio from S3
   b. ASR: audio -> text (SenseVoice-Small)
   c. Loads conversation context from Redis
   d. LLM: drives subagent loop (DeepSeek)
   e. TTS: text -> audio (CosyVoice2-0.5B)
   f. Uploads response audio to S3
   g. PUT /api/v1/tasks/{id}/result to Backend
7. Backend updates task status in MySQL
8. Backend notifies Client via WebSocket
9. Client downloads response audio from S3 and plays
```

### Context Archive Flow (scheduled)
```
1. Cron job triggers context compression
2. Read conversation history from Redis
3. Summarize older messages using LLM
4. Archive raw conversation to S3 by date
5. Update MySQL with current context pointer
6. Prune expired Redis keys
```

## Port Allocations

| Service | Port | Protocol |
|---------|------|----------|
| guineapig-backend | 8080 | HTTP |
| guineapig-aiagent | 8000 | HTTP |
| guineapig-aiagent | 50051 | gRPC |
| guineapig-ops-web | 3000 | HTTP (dev) |
| MySQL | 3306 | TCP |
| Redis | 6379 | TCP |
| MinIO (S3) | 9000 | HTTP |

## Security Rules

1. All Backend API endpoints require authentication (JWT)
2. AIAgent internal API is not exposed publicly (internal network only)
3. S3 presigned URLs for audio upload/download
4. `.env` files never committed to git
5. Secret rotation via environment variables, not config files
