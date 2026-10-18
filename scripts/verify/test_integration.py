#!/usr/bin/env python3
"""
GuineaPig 集成测试运行器（Integration Test Runner）

用途
----
使用标准库 urllib 对本地各服务发起 HTTP 请求，验证跨服务集成场景：
  - 后端 / AIAgent / 运营后台的健康与首页；
  - 核心的语音任务提交流程（POST /api/v1/tasks）。

服务地址可通过环境变量 BACKEND_URL / AIAGENT_URL / OPS_WEB_URL 覆盖。
退出码：0 = 全部通过；1 = 有失败（服务未启动时失败属正常）。
用法：python3 scripts/verify/test_integration.py
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

# 本文件位于 <root>/scripts/verify/，故上溯三级得到仓库根。
ROOT_DIR = Path(__file__).resolve().parent.parent.parent

# 各服务地址（从环境变量读取，缺省为本地默认端口）。
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8080")
AIAGENT_URL = os.environ.get("AIAGENT_URL", "http://localhost:8000")
OPS_WEB_URL = os.environ.get("OPS_WEB_URL", "http://localhost:3000")

PASS = 0
FAIL = 0


def http_get(url: str, timeout: int = 5) -> tuple:
    """发起 HTTP GET，返回 (状态码, 响应体)。连接异常时返回 (0, 错误信息)。"""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        # 4xx/5xx 也算拿到响应，返回其状态码与响应体。
        return e.code, e.read().decode()
    except Exception as e:
        return 0, str(e)


def http_post(url: str, data: dict, timeout: int = 5) -> tuple:
    """发起 HTTP POST（JSON 请求体），返回 (状态码, 响应体)。异常时返回 (0, 错误信息)。"""
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
    """
    断言一条测试：状态码需等于 expected；
    若指定了 contains，则响应体也必须包含该子串。返回是否通过。
    """
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
    """后端健康检查：GET /health 应返回 200。"""
    print("\n[Backend Health Check]")
    status, body = http_get(f"{BACKEND_URL}/health")
    return check("GET /health", status, 200)


def test_aiagent_health():
    """AIAgent 健康检查：GET /health 应返回 200。"""
    print("\n[AIAgent Health Check]")
    status, body = http_get(f"{AIAGENT_URL}/health")
    return check("GET /health", status, 200)


def test_ops_web_index():
    """运营后台首页：GET / 应返回 200。"""
    print("\n[Ops Web Check]")
    status, body = http_get(f"{OPS_WEB_URL}/")
    return check("GET /", status, 200)


def test_voice_task_flow():
    """核心语音任务流程：提交任务后响应体应包含 task_id。"""
    print("\n[Voice Task Flow]")

    # 用时间戳保证 task_id 唯一，避免重复提交冲突。
    task_data = {
        "user_id": 1,
        "s3_path": "/integration-test/audio.mp3",
        "task_id": f"integration-test-{int(time.time())}",
    }
    status, body = http_post(f"{BACKEND_URL}/api/v1/tasks", task_data)
    return check("POST /api/v1/tasks (submit voice task)", status, 200, body, "task_id")


def main() -> int:
    """按顺序运行所有集成测试并汇总结果。"""
    print("=" * 60)
    print("  GuineaPig Integration Tests")
    print("=" * 60)

    global PASS, FAIL

    # 测试清单：名称 -> 测试函数。
    tests = [
        ("Backend Health", test_backend_health),
        ("AIAgent Health", test_aiagent_health),
        ("Ops Web Index", test_ops_web_index),
        ("Voice Task Flow", test_voice_task_flow),
    ]

    # 逐个执行，捕获异常并按失败计数。
    for name, test_fn in tests:
        try:
            if test_fn():
                PASS += 1
            else:
                FAIL += 1
        except Exception as e:
            print(f"  ✗ {name}: Exception - {e}")
            FAIL += 1

    # 汇总。
    total = PASS + FAIL
    print("\n" + "=" * 60)
    print(f"  Results: {PASS}/{total} passed, {FAIL} failed")
    print("=" * 60)

    # 提示：若服务未在本地启动，出现失败是预期情况。
    if FAIL > 0:
        print("\n  Note: If services are not running locally, failures are expected.")
        print("  Start services with: make dev")

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
