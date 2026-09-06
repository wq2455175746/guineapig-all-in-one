.PHONY: help dev build validate test clean docker-build docker-push

APP_NAME := guineapig-aiagent
REGISTRY ?= harbor.whg11.local:17020
IMAGE_TAG ?= latest

help:
	@echo "GuineaPig AI Agent — Development Commands"
	@echo ""
	@echo "  make dev           — Start uvicorn dev server"
	@echo "  make validate      — Check Python imports"
	@echo "  make test          — Run pytest"
	@echo "  make clean         — Clean cache files"
	@echo "  make docker-build  — Build Docker image"
	@echo "  make docker-push   — Push Docker image"

dev:
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

validate:
	uv run python -c "import fastapi; print('OK: fastapi', fastapi.__version__)"

test:
	uv run pytest -q --ignore=test/routers_agent_test.py

clean:
	rm -rf __pycache__ .pytest_cache
	rm -rf app/__pycache__ app/**/__pycache__
	rm -rf .venv

docker-build:
	docker build -t $(REGISTRY)/aiagent/$(APP_NAME):$(IMAGE_TAG) .

docker-push: docker-build
	docker push $(REGISTRY)/aiagent/$(APP_NAME):$(IMAGE_TAG)
