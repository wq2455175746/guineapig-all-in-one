#!/usr/bin/env python3
"""
GuineaPig Integration Test Runner
Tests cross-service integration scenarios.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent

# Service URLs
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8080")
AIAGENT_URL = os.environ.get("AIAGENT_URL", "http://localhost:8000")
OPS_WEB_URL = os.environ.get("OPS_WEB_URL", "http://localhost:3000")

PASS = 0
FAIL = 0


def http_get(url: str, timeout: int = 5) -> tuple:
    """Make HTTP GET request. Returns (status_code, body)."""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return 0, str(e)


def http_post(url: str, data: dict, timeout: int = 5) -> tuple:
    """Make HTTP POST request. Returns (status_code, body)."""
    try:
        body = json.dumps(data).encode()
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return 0, str(e)


def check(name: str, status: int, expected: int, body: str = "", contains: str = "") -> bool:
    """Check a test assertion."""
    if status == expected:
        if contains and contains not in body:
            print(f"  ✗ {name}: body does not contain '{contains}'")
            return False
        print(f"  ✓ {name}")
        return True
    else:
        print(f"  ✗ {name}: expected HTTP {expected}, got {status}")
        return False


def test_backend_health():
    """Test backend health endpoint."""
    print("\n[Backend Health Check]")
    status, body = http_get(f"{BACKEND_URL}/health")
    return check("GET /health", status, 200)


def test_aiagent_health():
    """Test AIAgent health endpoint."""
    print("\n[AIAgent Health Check]")
    status, body = http_get(f"{AIAGENT_URL}/health")
    return check("GET /health", status, 200)


def test_ops_web_index():
    """Test ops web index page."""
    print("\n[Ops Web Check]")
    status, body = http_get(f"{OPS_WEB_URL}/")
    return check("GET /", status, 200)


def test_voice_task_flow():
    """Test the core voice dialogue submission flow."""
    print("\n[Voice Task Flow]")

    # Submit a task
    task_data = {
        "user_id": 1,
        "s3_path": "/integration-test/audio.mp3",
        "task_id": f"integration-test-{int(time.time())}",
    }
    status, body = http_post(f"{BACKEND_URL}/api/v1/tasks", task_data)
    return check("POST /api/v1/tasks (submit voice task)", status, 200, body, "task_id")


def main() -> int:
    """Run all integration tests."""
    print("=" * 60)
    print("  GuineaPig Integration Tests")
    print("=" * 60)

    global PASS, FAIL

    # Run each test and count results
    tests = [
        ("Backend Health", test_backend_health),
        ("AIAgent Health", test_aiagent_health),
        ("Ops Web Index", test_ops_web_index),
        ("Voice Task Flow", test_voice_task_flow),
    ]

    for name, test_fn in tests:
        try:
            if test_fn():
                PASS += 1
            else:
                FAIL += 1
        except Exception as e:
            print(f"  ✗ {name}: Exception - {e}")
            FAIL += 1

    # Summary
    total = PASS + FAIL
    print("\n" + "=" * 60)
    print(f"  Results: {PASS}/{total} passed, {FAIL} failed")
    print("=" * 60)

    # If services aren't running, don't fail - just report
    if FAIL > 0:
        print("\n  Note: If services are not running locally, failures are expected.")
        print("  Start services with: make dev")

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
