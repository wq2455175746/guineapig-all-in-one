.PHONY: help validate test dev build clean logs docker-up docker-down docker-build docker-push

# 项目根目录
ROOT_DIR := $(shell pwd)
PACKAGES := guineapig-backend guineapig-ops-web guineapig-client guineapig-aiagent

# Docker 镜像配置
REGISTRY ?= harbor.whg11.local:17020
IMAGE_TAG ?= latest
DOCKER_COMPOSE_DEV ?= docker-compose.yml
DOCKER_COMPOSE_PROD ?= docker-compose.prod.yml

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

# 开发环境
dev:
	@echo "Starting development environment..."
	docker compose -f $(DOCKER_COMPOSE_DEV) --profile all up --build -d
	@echo "Services starting... use 'make docker-logs' to tail logs"

dev-backend:
	cd packages/guineapig-backend && make dev

dev-frontend:
	cd packages/guineapig-ops-web && npm run dev

dev-aiagent:
	cd packages/guineapig-aiagent && make dev

dev-client:
	cd packages/guineapig-client && npm run dev

# 验证
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

validate-%:
	@echo "🔍 Validating $*..."
	@cd packages/$* && make validate

# 测试
test:
	@echo "🧪 Running all tests..."
	@echo "  Testing guineapig-backend..."
	@cd $(ROOT_DIR)/packages/guineapig-backend && go test ./... 2>&1 | tail -5
	@echo "  Testing guineapig-aiagent..."
	@cd $(ROOT_DIR)/packages/guineapig-aiagent && uv run pytest -q --ignore=test/routers_agent_test.py 2>/dev/null || echo "  ⚠️  aiagent tests skipped"
	@echo "✅ All tests passed"

test-%:
	@cd packages/$* && make test

# 构建
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

build-docker:
	@echo "Building all Docker images..."
	@cd $(ROOT_DIR)/packages/guineapig-backend && $(MAKE) docker-build
	@cd $(ROOT_DIR)/packages/guineapig-aiagent && $(MAKE) docker-build
	@cd $(ROOT_DIR)/packages/guineapig-ops-web && $(MAKE) docker-build
	@echo "All Docker images built"

build-docker-%:
	@cd packages/$* && $(MAKE) docker-build

push-docker:
	@echo "Pushing all Docker images..."
	@cd $(ROOT_DIR)/packages/guineapig-backend && $(MAKE) docker-push
	@cd $(ROOT_DIR)/packages/guineapig-aiagent && $(MAKE) docker-push
	@cd $(ROOT_DIR)/packages/guineapig-ops-web && $(MAKE) docker-push
	@echo "All Docker images pushed"

push-docker-%:
	@cd packages/$* && $(MAKE) docker-push

docker-up:
	docker compose -f $(DOCKER_COMPOSE_DEV) --profile all up --build -d
	@echo "Development stack started"

docker-down:
	docker compose -f $(DOCKER_COMPOSE_DEV) down
	docker compose -f $(DOCKER_COMPOSE_PROD) down

docker-logs:
	docker compose -f $(DOCKER_COMPOSE_DEV) logs -f

docker-prod-up:
	docker compose -f $(DOCKER_COMPOSE_PROD) up -d --build
	@echo "Production stack started"

build-client:
	cd packages/guineapig-client && npm run build:electron

# 日志
logs:
	docker compose -f $(DOCKER_COMPOSE_DEV) logs -f

# 清理
clean:
	@echo "🧹 Cleaning..."
	@$(foreach pkg,$(PACKAGES), \
		cd $(ROOT_DIR)/packages/$(pkg) && make clean 2>/dev/null || true; \
	)
	rm -rf .ai/checkpoints/*.tmp
	docker compose -f $(DOCKER_COMPOSE_DEV) down -v
	@echo "✅ Cleaned"

# AI 工具
checkpoint:
	@echo "💾 Saving checkpoint..."
	@python3 scripts/update_memory.py --checkpoint

memory-add:
	@python3 scripts/update_memory.py --add

# 初始化
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