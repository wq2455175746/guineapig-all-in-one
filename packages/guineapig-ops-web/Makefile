.PHONY: help dev build validate clean docker-build docker-push

APP_NAME := guineapig-ops-web
REGISTRY ?= harbor.whg11.local:17020
IMAGE_TAG ?= latest

help:
	@echo "GuineaPig Ops-Web — Development Commands"
	@echo ""
	@echo "  make dev           — Start Vite dev server"
	@echo "  make build         — Build production bundle"
	@echo "  make validate      — Check build"
	@echo "  make clean         — Remove build artifacts"
	@echo "  make docker-build  — Build Docker image"
	@echo "  make docker-push   — Push Docker image"

dev:
	npm run dev

build:
	npm run build

validate:
	npm run build -- --logLevel error

clean:
	rm -rf dist node_modules

docker-build:
	docker build -t $(REGISTRY)/aiagent/$(APP_NAME):$(IMAGE_TAG) .

docker-push: docker-build
	docker push $(REGISTRY)/aiagent/$(APP_NAME):$(IMAGE_TAG)
