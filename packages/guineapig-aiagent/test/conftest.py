"""
pytest 全局 fixtures — 必须在导入 app.main 前注入测试用 ADMIN_TOKEN。

鉴权中间件对 settings.ADMIN_TOKEN 为空的情况 fail-closed（拒绝所有非白名单请求），
因此测试环境需要显式配置一个测试 token。conftest.py 由 pytest 在收集测试模块前加载，
确保测试模块顶层 `from app.main import app` 时环境变量已就绪。
"""

import os

os.environ["ADMIN_TOKEN"] = "test-admin-token"