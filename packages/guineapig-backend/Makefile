.PHONY: help dev build clean validate test docker-build docker-push

APP_NAME := guineapig
BIN_DIR := bin
BINARY := $(BIN_DIR)/$(APP_NAME)
REGISTRY ?= harbor.whg11.local:17020
IMAGE_TAG ?= latest

help:
	@echo "GuineaPig Backend — Development Commands"
	@echo ""
	@echo "  make dev           — Run with hot-reload (air)"
	@echo "  make build         — Build native binary"
	@echo "  make build-linux   — Build Linux amd64 binary (for Docker)"
	@echo "  make validate      — Run go vet"
	@echo "  make test          — Run tests"
	@echo "  make clean         — Remove build artifacts"
	@echo "  make docker-build  — Build Docker image"
	@echo "  make docker-push   — Push Docker image"

dev:
	@if command -v air >/dev/null 2>&1; then \
		air; \
	else \
		echo "air not installed, running directly..."; \
		go run main.go; \
	fi

build:
	@mkdir -p $(BIN_DIR)
	go build -o $(BINARY) main.go

build-linux:
	@mkdir -p $(BIN_DIR)
	CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
		go build -ldflags "-s -w" -trimpath -o $(BINARY) main.go

validate:
	go vet ./...

test:
	go test ./... -v -count=1

clean:
	rm -rf $(BIN_DIR)

docker-build:
	docker build -t $(REGISTRY)/aiagent/$(APP_NAME):$(IMAGE_TAG) .

docker-push: docker-build
	docker push $(REGISTRY)/aiagent/$(APP_NAME):$(IMAGE_TAG)
