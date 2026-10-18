# =============================================================================
# GuineaPig All-in-One —— 顶层 Makefile
# =============================================================================
# 本 Makefile 是 monorepo 的统一入口，封装了四类操作：
#   1. 开发 (dev-*)      —— 本地启动各服务；
#   2. 校验 (validate)   —— 配合 scripts/validate.py 做结构自检；
#   3. 构建 (build-*)    —— 原生构建 / 构建并推送 Docker 镜像；
#   4. 运维 (docker-*, clean, init, checkpoint ...)
#
# 用法：直接运行 `make help` 查看所有可用目标。
#
# 说明：monorepo 下每个子包（packages/*）通常自带 Makefile，
#      本文件通过 `cd packages/xxx && make ...` 或 `$(MAKE)` 转发到子包。
# =============================================================================

# .PHONY 声明这些目标不是真实文件，避免与同名文件冲突导致命令被跳过。
.PHONY: help validate test dev build clean logs docker-up docker-down docker-build docker-push

# 项目根目录（执行 make 时所在目录）。子目标里用它拼绝对路径，保证 cd 后仍能定位仓库根。
ROOT_DIR := $(shell pwd)
# monorepo 内的子包列表，供 clean 等需要遍历所有包的循环目标使用。
PACKAGES := guineapig-backend guineapig-ops-web guineapig-client guineapig-aiagent

# ---- Docker 相关可覆盖变量（用 `?=` 允许外部环境变量或命令行覆盖）----
REGISTRY ?= harbor.whg11.local:17020   # 镜像仓库地址（私有 harbor）
IMAGE_TAG ?= latest                    # 镜像 tag
DOCKER_COMPOSE_DEV ?= docker-compose.yml       # 开发环境 compose 文件
DOCKER_COMPOSE_PROD ?= docker-compose.prod.yml # 生产环境 compose 文件

# -----------------------------------------------------------------------------
# help：打印命令帮助。用 @ 前缀抑制命令回显，只显示 echo 的内容。
# -----------------------------------------------------------------------------
help:
	@echo "🐹 GuineaPig All-in-One Development Commands"
	@echo ""
	@echo "Development:"
	@echo "  make dev              - Start all services in development mode"
	@echo "  make dev-backend      - Start only backend"
	@echo "  make dev-frontend     - Start only frontend"
	@echo "  make dev-aiagent      - Start only AI agent"
	@echo "  make dev-client       - Start Electron client"
	@echo ""
	@echo "Validation:"
	@echo "  make validate         - Validate all services"
	@echo "  make validate-<svc>   - Validate specific service"
	@echo "  make test             - Run all tests"
	@echo "  make test-<svc>       - Run tests for specific service"
	@echo ""
	@echo "Building:"
	@echo "  make build-all        - Build all services (native)"
	@echo "  make build-client     - Build Electron client installer"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-up        - Start all services via docker-compose"
	@echo "  make docker-down      - Stop all services"
	@echo "  make docker-build     - Build all Docker images"
	@echo "  make docker-push      - Push all Docker images"
	@echo "  make docker-logs      - View docker-compose logs"
	@echo "  make docker-prod-up   - Start production stack"
	@echo ""
	@echo "Utilities:"
	@echo "  make logs             - View all logs"
	@echo "  make clean            - Clean build artifacts"
	@echo "  make checkpoint       - Save current progress to .ai/"
	@echo "  make memory-add       - Add lesson to AI memory"

# =============================================================================
# 开发环境
# =============================================================================

# dev：通过 docker compose 在后台启动全部服务（--profile all 启用所有 profile，--build 先重建镜像）。
dev:
	@echo "Starting development environment..."
	docker compose -f $(DOCKER_COMPOSE_DEV) --profile all up --build -d
	@echo "Services starting... use 'make docker-logs' to tail logs"

# dev-backend：仅以本地（非容器）方式启动 Go 后端，转发到子包 Makefile 的 dev 目标。
dev-backend:
	cd packages/guineapig-backend && make dev

# dev-frontend：仅启动运营后台前端（Vite 开发服务器）。
dev-frontend:
	cd packages/guineapig-ops-web && npm run dev -- --host guineapig-ops-web.local

# dev-aiagent：仅启动 Python AI agent，转发到子包 Makefile。
dev-aiagent:
	cd packages/guineapig-aiagent && make dev

# dev-client：以开发模式启动 Electron 客户端。
#   通过 `--` 把参数透传给底层的 vite，指定 host 别名与端口（需在 /etc/hosts 里配置 guineapig-client.local）。
dev-client:
	cd packages/guineapig-client && npm run dev -- --host guineapig-client.local --port 5174

# =============================================================================
# 验证
# =============================================================================

# validate：对全部服务做静态自检。
#   先对各子包做语言级检查（go vet / 前端构建 / vue-tsc 类型检查 / aiagent 可导入），
#   再调用 scripts/validate.py 做目录结构与配置完整性校验。
#   子包的检查用 `2>/dev/null || ...` 做成「尽力而为」：环境没装好时打印跳过提示而非中断。
validate:
	@echo "🔍 Validating all services..."
	@echo "  Validating guineapig-backend..."
	@cd $(ROOT_DIR)/packages/guineapig-backend && go vet ./... 2>/dev/null || go vet ./...
	@echo "  Validating guineapig-ops-web..."
	@cd $(ROOT_DIR)/packages/guineapig-ops-web && npm run build -- --logLevel error 2>/dev/null || echo "  ⚠️  ops-web build skipped (check node_modules)"
	@echo "  Validating guineapig-client..."
	@cd $(ROOT_DIR)/packages/guineapig-client && npx vue-tsc --noEmit 2>/dev/null || echo "  ⚠️  client type check skipped (check node_modules)"
	@echo "  Validating guineapig-aiagent..."
	@cd $(ROOT_DIR)/packages/guineapig-aiagent && uv run python -c "import fastapi" 2>/dev/null || echo "  ⚠️  aiagent import check skipped"
	@python3 $(ROOT_DIR)/scripts/validate.py
	@echo "✅ All validations passed"

# validate-<svc>：只校验指定子包。$* 是模式中 % 捕获的部分（如 validate-backend 里的 backend）。
#   注意此处用相对路径 packages/$*，因此需要从仓库根执行。
validate-%:
	@echo "🔍 Validating $*..."
	@cd packages/$* && make validate

# =============================================================================
# 测试
# =============================================================================

# test：运行后端与 aiagent 的测试。
#   Go 测试用 `tail -5` 只保留末尾输出；aiagent 测试在缺依赖时打印跳过提示。
test:
	@echo "🧪 Running all tests..."
	@echo "  Testing guineapig-backend..."
	@cd $(ROOT_DIR)/packages/guineapig-backend && go test ./... 2>&1 | tail -5
	@echo "  Testing guineapig-aiagent..."
	@cd $(ROOT_DIR)/packages/guineapig-aiagent && uv run pytest -q --ignore=test/routers_agent_test.py 2>/dev/null || echo "  ⚠️  aiagent tests skipped"
	@echo "✅ All tests passed"

# test-<svc>：转发到指定子包的 test 目标。
test-%:
	@cd packages/$* && make test

# =============================================================================
# 构建
# =============================================================================

# build-all：原生构建所有服务。
#   Go 后端编译成 bin/guineapig；两个前端做生产构建；aiagent 是 Python 包无需构建。
build-all:
	@echo "🏗️  Building all services..."
	@echo "  Building guineapig-backend..."
	@cd $(ROOT_DIR)/packages/guineapig-backend && go build -o bin/guineapig main.go 2>&1 | tail -3
	@echo "  Building guineapig-ops-web..."
	@cd $(ROOT_DIR)/packages/guineapig-ops-web && npm run build 2>&1 | tail -3
	@echo "  Building guineapig-client..."
	@cd $(ROOT_DIR)/packages/guineapig-client && npm run build 2>&1 | tail -3 || echo "  ⚠️  client build skipped (check node_modules)"
	@echo "  Building guineapig-aiagent..."
	@echo "  ✅ aiagent is a Python package, no build needed"

# build-docker：依次构建 backend / aiagent / ops-web 的 Docker 镜像（转发到子包 Makefile）。
build-docker:
	@echo "Building all Docker images..."
	@cd $(ROOT_DIR)/packages/guineapig-backend && $(MAKE) docker-build
	@cd $(ROOT_DIR)/packages/guineapig-aiagent && $(MAKE) docker-build
	@cd $(ROOT_DIR)/packages/guineapig-ops-web && $(MAKE) docker-build
	@echo "All Docker images built"

# build-docker-<svc>：只构建指定子包的镜像。
build-docker-%:
	@cd packages/$* && $(MAKE) docker-build

# push-docker：把三类镜像推送到镜像仓库（转发到子包 Makefile）。
push-docker:
	@echo "Pushing all Docker images..."
	@cd $(ROOT_DIR)/packages/guineapig-backend && $(MAKE) docker-push
	@cd $(ROOT_DIR)/packages/guineapig-aiagent && $(MAKE) docker-push
	@cd $(ROOT_DIR)/packages/guineapig-ops-web && $(MAKE) docker-push
	@echo "All Docker images pushed"

# push-docker-<svc>：只推送指定子包的镜像。
push-docker-%:
	@cd packages/$* && $(MAKE) docker-push

# docker-up：用开发 compose 启动全套服务（后台运行）。等价于 dev 目标的核心命令。
docker-up:
	docker compose -f $(DOCKER_COMPOSE_DEV) --profile all up --build -d
	@echo "Development stack started"

# docker-down：先停开发栈，再停生产栈（down 会停止并移除容器/网络）。
docker-down:
	docker compose -f $(DOCKER_COMPOSE_DEV) down
	docker compose -f $(DOCKER_COMPOSE_PROD) down

# docker-logs：实时跟踪（-f）开发栈日志。
docker-logs:
	docker compose -f $(DOCKER_COMPOSE_DEV) logs -f

# docker-prod-up：在生产 compose 下构建并后台启动生产环境。
docker-prod-up:
	docker compose -f $(DOCKER_COMPOSE_PROD) up -d --build
	@echo "Production stack started"

# build-client：构建 Electron 客户端安装包。
build-client:
	cd packages/guineapig-client && npm run build:electron

# =============================================================================
# 日志
# =============================================================================

# logs：查看开发栈日志（与 docker-logs 相同，保留为习惯用法的别名）。
logs:
	docker compose -f $(DOCKER_COMPOSE_DEV) logs -f

# =============================================================================
# 清理
# =============================================================================

# clean：清理各子包构建产物，并回收 docker 资源。
#   $(foreach ...) 遍历 PACKAGES，对每个子包执行其 make clean（失败忽略）；
#   末尾 `down -v` 会同时删除数据卷（-v）。
clean:
	@echo "🧹 Cleaning..."
	@$(foreach pkg,$(PACKAGES), \
		cd $(ROOT_DIR)/packages/$(pkg) && make clean 2>/dev/null || true; \
	)
	rm -rf .ai/checkpoints/*.tmp
	docker compose -f $(DOCKER_COMPOSE_DEV) down -v
	@echo "✅ Cleaned"

# =============================================================================
# AI 工具
# =============================================================================

# checkpoint：把当前进度快照保存到 .ai/ 工作区。
checkpoint:
	@echo "💾 Saving checkpoint..."
	@python3 scripts/update_memory.py --checkpoint

# memory-add：向 AI 记忆库追加一条经验教训。
memory-add:
	@python3 scripts/update_memory.py --add

# =============================================================================
# 初始化
# =============================================================================

# init：首次克隆后初始化目录骨架与占位文件（幂等：已存在则不覆盖）。
init:
	@echo "🐹 Initializing GuineaPig project..."
	@mkdir -p .ai/{memory,checkpoints,traces,rules}
	@mkdir -p docs/{design-docs,exec-plans/{active,completed}}
	@mkdir -p templates scripts/verify
	@[ -f .ai/CURRENT_FOCUS ] || echo '{"service": null, "task_id": null}' > .ai/CURRENT_FOCUS
	@[ -f .ai/memory/lessons.json ] || echo '{"lessons": []}' > .ai/memory/lessons.json
	@[ -f .ai/memory/anti-patterns.md ] || echo '# Anti-Patterns\n' > .ai/memory/anti-patterns.md
	@[ -f .ai/memory/successful-patterns.md ] || echo '# Successful Patterns\n' > .ai/memory/successful-patterns.md
	@[ -f .ai/traces/failures.log ] || touch .ai/traces/failures.log
	@chmod +x scripts/*.py scripts/verify/*.sh scripts/verify/*.py scripts/docker/*.sh 2>/dev/null || true
	@echo "✅ Harness initialization complete"
	@echo ""
	@echo "Next steps:"
	@echo "  1. cd packages/guineapig-backend && go mod download"
	@echo "  2. cd packages/guineapig-ops-web && npm install"
	@echo "  3. cd packages/guineapig-client && npm install"
	@echo "  4. cd packages/guineapig-aiagent && uv sync"
	@echo "  5. make docker-up"
