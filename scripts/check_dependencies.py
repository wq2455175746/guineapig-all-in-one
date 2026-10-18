#!/usr/bin/env python3
"""
GuineaPig 分层依赖检查器（Layer Dependency Checker）

用途
----
保证 monorepo 的架构分层不被破坏。检查两类规则：

  1) 依赖方向：客户端/运营后台只能依赖 backend，backend 只能通过 API 调用 aiagent，
     aiagent 不依赖其它包（见 VALID_DEPENDENCIES，目前主要作为文档约定）。
  2) 禁止越界：
     - backend 不得直接引入 AI/ML 库（必须经 aiagent）；
     - 任何包不得直接 import 其它包的内部代码（应通过 HTTP/WS 通信）。

退出码：0 = 全部通过；1 = 存在违规。
用法：python3 scripts/check_dependencies.py
"""
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Set

# 仓库根目录（本文件位于 <root>/scripts/）。
ROOT_DIR = Path(__file__).resolve().parent.parent

# 合法的依赖方向（只允许向下游依赖）：
#   backend 依赖 aiagent（通过其 API 调用）
#   client / ops-web 依赖 backend
# 注意：这里记录的是「允许的」关系，供阅读与后续扩展；当前脚本重点在下方禁用项。
VALID_DEPENDENCIES = {
    "guineapig-backend": set(),  # 除标准库外不应依赖别的包
    "guineapig-client": {"guineapig-backend"},  # 仅通过 HTTP/WS
    "guineapig-ops-web": {"guineapig-backend"},  # 仅通过 HTTP
    "guineapig-aiagent": set(),  # 不依赖其它包
}

# 禁用：以下包不得直接 import AI/ML 库（AI 能力统一收敛到 aiagent）。
FORBIDDEN_AI_IMPORTS = {
    "guineapig-backend": [
        "openai", "anthropic", "langchain", "llamaindex",
        "whisper", "faster-whisper", "sensevoice", "funasr",
        "chattts", "cosyvoice", "voxcpm",
        "transformers", "torch", "tensorflow",
        "mcp", "agent-skills",
    ],
}

# 禁用：跨包直接 import 其它包的代码（尤其 backend 的 internal 实现）。
FORBIDDEN_CROSS_IMPORTS = {
    "guineapig-backend": ["guineapig-client", "guineapig-ops-web"],
    "guineapig-client": ["guineapig-backend/internal", "guineapig-aiagent"],
    "guineapig-ops-web": ["guineapig-backend/internal", "guineapig-aiagent"],
    "guineapig-aiagent": ["guineapig-backend/internal", "guineapig-client", "guineapig-ops-web"],
}


def check_go_dependencies(pkg_dir: Path, pkg_name: str) -> List[str]:
    """检查 Go 包的 go.mod 是否引入了被禁用的 AI 库。返回错误消息列表。"""
    errors = []
    gomod = pkg_dir / "go.mod"

    # 没有 go.mod 说明不是 Go 包，直接跳过。
    if not gomod.exists():
        return errors

    content = gomod.read_text()

    # 逐个匹配禁用库（统一转小写，避免大小写差异漏检）。
    forbidden = FORBIDDEN_AI_IMPORTS.get(pkg_name, [])
    for lib in forbidden:
        if lib in content.lower():
            errors.append(
                f"{pkg_name}/go.mod: imports AI library '{lib}'. "
                f"AI operations must go through guineapig-aiagent"
            )

    return errors


def check_python_dependencies(pkg_dir: Path, pkg_name: str) -> List[str]:
    """检查 Python 包的 requirements.txt 是否引入被禁用的 AI 库。"""
    errors = []
    req_file = pkg_dir / "requirements.txt"

    if not req_file.exists():
        return errors

    # aiagent 是唯一允许引入 AI 库的包，其余包都会被检查。
    if pkg_name != "guineapig-aiagent":
        forbidden = FORBIDDEN_AI_IMPORTS.get(pkg_name, [])
        content = req_file.read_text().lower()
        for lib in forbidden:
            if lib in content:
                errors.append(
                    f"{pkg_name}/requirements.txt: imports AI library '{lib}'. "
                    f"AI operations must go through guineapig-aiagent"
                )

    return errors


def check_js_dependencies(pkg_dir: Path, pkg_name: str) -> List[str]:
    """检查前端包 package.json 的依赖中是否出现被禁用的 AI 库。"""
    errors = []
    pkg_json = pkg_dir / "package.json"

    if not pkg_json.exists():
        return errors

    import json
    with open(pkg_json) as fh:
        data = json.load(fh)

    # 合并运行时依赖与开发依赖一起检查。
    all_deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}

    # 前端/客户端同样不得直接依赖 AI 库。
    if pkg_name != "guineapig-aiagent":
        forbidden = FORBIDDEN_AI_IMPORTS.get(pkg_name, [])
        for lib in forbidden:
            if lib in all_deps:
                errors.append(
                    f"{pkg_name}/package.json: depends on AI library '{lib}'. "
                    f"AI operations must go through guineapig-aiagent"
                )

    return errors


def _check_go_imports(content: str, forbidden_pkgs: List[str]) -> bool:
    """判断 Go 源码中是否 import 了任何被禁用的包路径。命中返回 True。"""
    import re
    # 匹配多行 import 块：import ( ... )
    import_pattern = re.compile(r'import\s*\(\s*(.*?)\s*\)', re.DOTALL)
    # 匹配单行 import "path"
    single_import = re.compile(r'import\s+"([^"]+)"')

    # 检查 import 块内的每一行。
    for match in import_pattern.finditer(content):
        block = match.group(1)
        for forbidden in forbidden_pkgs:
            if forbidden in block:
                return True

    # 检查单行 import。
    for match in single_import.finditer(content):
        path = match.group(1)
        for forbidden in forbidden_pkgs:
            if forbidden in path:
                return True

    return False


def _check_py_imports(content: str, forbidden_pkgs: List[str]) -> bool:
    """判断 Python 源码中是否 import 了任何被禁用的包。命中返回 True。"""
    import re
    for forbidden in forbidden_pkgs:
        # Python 包名用下划线，故先把连字符替换为下划线。
        pkg = forbidden.replace("-", "_")
        # 匹配 `import pkg` 或 `from pkg import ...`。
        if re.search(rf'(import\s+{pkg}|from\s+{pkg}\s+import)', content):
            return True
    return False


def check_cross_package_imports() -> List[str]:
    """扫描所有包源码，检查是否存在跨包直接 import 的违规。"""
    errors = []
    packages_dir = ROOT_DIR / "packages"

    for pkg_name, forbidden_pkgs in FORBIDDEN_CROSS_IMPORTS.items():
        pkg_dir = packages_dir / pkg_name
        if not pkg_dir.exists():
            continue

        # 检查 Go 源码（只看真实 import，不误判 URL 字符串等）。
        for go_file in pkg_dir.rglob("*.go"):
            content = go_file.read_text()
            if _check_go_imports(content, forbidden_pkgs):
                errors.append(
                    f"{go_file.relative_to(ROOT_DIR)}: imports forbidden package"
                )

        # 检查 Python 源码（跳过 __pycache__ 缓存目录）。
        for py_file in pkg_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            content = py_file.read_text()
            if _check_py_imports(content, forbidden_pkgs):
                errors.append(
                    f"{py_file.relative_to(ROOT_DIR)}: imports forbidden package"
                )

    return errors


def main() -> int:
    """依次检查每个包的依赖声明，再做跨包 import 扫描，最后汇总退出码。"""
    print("=" * 60)
    print("  GuineaPig Layer Dependency Check")
    print("=" * 60)

    total_errors = 0
    packages_dir = ROOT_DIR / "packages"

    # 逐个包按其语言选择对应的检查器。
    for pkg_name in ["guineapig-backend", "guineapig-aiagent", "guineapig-ops-web", "guineapig-client"]:
        pkg_dir = packages_dir / pkg_name
        if not pkg_dir.exists():
            print(f"\n  ⚠ {pkg_name}: package not found (skipping)")
            continue

        print(f"\n[{pkg_name}]")

        # 依据存在的清单文件判断语言并分派检查。
        if (pkg_dir / "go.mod").exists():
            errors = check_go_dependencies(pkg_dir, pkg_name)
        elif (pkg_dir / "requirements.txt").exists() or (pkg_dir / "pyproject.toml").exists():
            errors = check_python_dependencies(pkg_dir, pkg_name)
        elif (pkg_dir / "package.json").exists():
            errors = check_js_dependencies(pkg_dir, pkg_name)
        else:
            print("  ⚠ Cannot determine package language")
            continue

        for e in errors:
            print(f"  ✗ {e}")
            total_errors += 1

        if not errors:
            print("  ✓ No dependency violations")

    # 跨包 import 扫描。
    print("\n[Cross-Package Import Check]")
    cross_errors = check_cross_package_imports()
    for e in cross_errors:
        print(f"  ✗ {e}")
        total_errors += 1
    if not cross_errors:
        print("  ✓ No cross-package import violations")

    # 汇总。
    print("\n" + "=" * 60)
    if total_errors == 0:
        print("  All dependency checks passed!")
        print("=" * 60)
        return 0
    else:
        print(f"  {total_errors} dependency violation(s) found")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
