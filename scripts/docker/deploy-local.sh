#!/bin/bash
# GuineaPig Local Deployment
# Deploys all services locally using docker-compose.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.dev.yml}"

echo "============================================"
echo "  GuineaPig Local Deployment"
echo "  Compose file: $COMPOSE_FILE"
echo "============================================"
echo ""

cd "$ROOT_DIR"

# Check prerequisites
echo "[Prerequisites]"

echo -n "  Docker ... "
if docker info >/dev/null 2>&1; then
    echo "OK"
else
    echo "FAILED"
    echo "  Docker is not running. Please start Docker first."
    exit 1
fi

echo -n "  docker compose ... "
if docker compose version >/dev/null 2>&1; then
    echo "OK"
else
    echo "FAILED"
    echo "  docker compose is not available."
    exit 1
fi

echo ""

# Stop existing containers (optional)
read -r -p "Stop existing containers? [y/N]: " stop_existing
if [[ "$stop_existing" =~ ^[Yy]$ ]]; then
    echo "  Stopping existing containers..."
    docker compose -f "$COMPOSE_FILE" down --remove-orphans 2>/dev/null || true
fi

# Start services
echo ""
echo "[Starting Services]"
docker compose -f "$COMPOSE_FILE" up -d --build

# Wait for healthy
echo ""
echo "[Waiting for services to be healthy...]"
sleep 5

# Check status
echo ""
echo "[Service Status]"
docker compose -f "$COMPOSE_FILE" ps

# Show URLs
echo ""
echo "============================================"
echo "  Services running:"
echo "  Backend:   http://localhost:8080"
echo "  AIAgent:   http://localhost:8000"
echo "  Ops Web:   http://localhost:3000"
echo "============================================"
echo ""
echo "  View logs: docker compose -f $COMPOSE_FILE logs -f"
echo "  Stop:      docker compose -f $COMPOSE_FILE down"
