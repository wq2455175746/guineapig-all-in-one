# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Backend (Go)
- **Go version**: 1.24.0 (as defined in `go.mod`)
- **Build**: `go build -o bin/guineapig main.go`
- **Run**: `go run main.go` (requires `.env` file with database and Redis credentials)
- **Build for Linux container**: `CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags "-s -w" -trimpath -o ./bin/guineapig main.go`
- **Docker/Podman build**: `podman build --tag=harbor.whg11.local:17020/aiagent/guineapig:1.0.0 .`
- **Push image**: `podman push harbor.whg11.local:17020/aiagent/guineapig:1.0.0`
- **Run with hot reload** (if air/reflex installed): Not configured, but could be added.
- **Note**: The `buildImage.sh` script currently writes binary as `autoeval`; adjust if needed.

### Frontend (Vite)
Located in `web/guineapig-web/`. Uses Vue 3 with Element Plus, ECharts, and xterm.
- **Development server**: `npm run dev` (or `pnpm dev`)
- **Build for production**: `npm run build` (or `pnpm build`)
- **Preview production build**: `npm run preview`
- **Container build**: `podman build --platform linux/amd64 --tag=harbor.whg11.local:17020/aiagent/guineapig-web:1.0.0 .` (see `build.sh`; note tag mismatch in push command)

### Go Tooling
- **Format code**: `go fmt ./...`
- **Download dependencies**: `go mod download`
- **Vendor dependencies**: `go mod tidy`
- **Run vet**: `go vet ./...`
- **Run tests**: `go test ./...` (no tests yet; add `*_test.go` files alongside code)

### Configuration
- Copy `.env.example` to `.env` and fill in credentials (no example file currently; create one from `.env` template). Required environment variables: `MYSQL_USERNAME`, `MYSQL_PASSWORD`, `MYSQL_HOST`, `REDIS_HOST`, `REDIS_PASSWORD`.
- Main config: `config.yaml` with environment variable substitution (`${VAR}`).
- Server runs on port `6880` by default.
- Debug mode prints parsed configuration as JSON when `debug: true` in config.

## Architecture Overview

### Tech Stack
- **Web framework**: Echo v4
- **ORM**: GORM with MySQL/SQLite drivers
- **Cache**: Redis via go-redis
- **Configuration**: Viper with YAML + godotenv for `.env`
- **Logging**: Zap with custom DB logger
- **Middleware**: Request ID, rate limiting, CORS, logger, recovery

### Project Structure
- `internal/` – private application code
  - `model/` – GORM models and database operations
  - `service/` – business logic
  - `router/` – HTTP route handlers (grouped by resource)
  - `request/` – request structs (input validation)
  - `response/` – response structs
- `pkg/` – reusable packages
  - `plugin/` – initialization of DB, Redis, logger
  - `middleware/` – Echo middleware (request ID, rate limiting)
  - `utils/` – utilities (desensitization, UUID)
  - `constant/` – constants and error codes
  - `ratelimit/` – rate‑limiter implementation
- `config/` – configuration loading (`config.go`)
- `web/guineapig-web/` – separate frontend Vite project

### Boot Sequence
1. `main.go` initializes Zap logger
2. Loads config via `config.ParseConfig()` (reads `config.yaml` + `.env`)
3. Calls `plugin.Init()` to set up database and Redis connections
4. Creates Echo server with middlewares
5. Registers routes via `router.Register()`
6. Starts server on configured port

### Key Patterns
- **Plugin system**: `pkg/plugin` centralizes external service initialization (DB, Redis).
- **Database access**: Models are accessed via global singleton (e.g., `model.MUser`). Database operations use `plugin.GetDB(ctx)` which attaches the context to the GORM instance.
- **Request/response separation**: Dedicated packages for API contracts.
- **Router registration**: Routes are added via `router.AddGetRouter()` etc. in `init()` functions.
- **Environment‑aware config**: `config.yaml` supports `${ENV_VAR}` placeholders expanded via `os.ExpandEnv`.
- **Rate limiting**: Configurable per‑endpoint QPS/concurrency limits via `config.yaml` → `rateLimiter` section.
- **Logging**: Zap logger with request‑ID support; DB queries can be logged when `logger.dbTrace: true` in config.

### Frontend Integration
- Backend CORS is configured to allow `http://guineapig-ops-web.local:5173`.
- Frontend is a separate Vite project; treat it as a standalone client.

### Deployment
- Container image expects compiled binary at `/app/guineapig` (see `Dockerfile`).
- Build script `buildImage.sh` shows the typical build‑and‑push flow for the internal registry.

### Notes
- No unit tests are present yet; add them in `*_test.go` files alongside the code they test.
- The `.env` file is git‑ignored; ensure sensitive credentials are not committed.
- Debug mode prints the parsed configuration as JSON when `debug: true` in `config.yaml`.
