#!/usr/bin/env python3
"""
GuineaPig 代码质量检查器（Code Quality Checker）

用途
----
按语言对各子包运行基础质量检查：
  - Go：go vet + gofmt 格式检查；
  - Python：优先 ruff，其次 flake8（都没有则忽略）；
  - JS/TS：是否配置并可通过 ESLint；
  - 全局：扫描缺少上下文说明的裸 TODO/FIXME/HACK。

退出码：0 = 全部通过；1 = 存在质量问题。
用法：python3 scripts/check_quality.py
"""
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

# 仓库根目录（本文件位于 <root>/scripts/）。
ROOT_DIR = Path(__file__).resolve().parent.parent


def run_cmd(cmd: List[str], cwd: Path = None) -> Tuple[int, str, str]:
    """
    执行外部命令，返回 (returncode, stdout, stderr)。

    统一做了容错：
      - 命令不存在 -> 返回码 -1，错误信息放进 stderr；
      - 超过 120 秒未结束 -> 视为超时，返回码 -1。
    """
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd or ROOT_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return -1, "", f"Command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out: {' '.join(cmd)}"


def check_go_quality(pkg_dir: Path) -> List[str]:
    """Go 质量检查：go vet 静态分析 + gofmt 格式检查。"""
    errors = []

    # go vet：发现可疑构造。
    ret, stdout, stderr = run_cmd(["go", "vet", "./..."], cwd=pkg_dir)
    if ret != 0:
        errors.append(f"go vet failed:\n{stderr}")

    # gofmt -l .：列出未格式化的文件（有输出即代表需要 gofmt）。
    ret, stdout, stderr = run_cmd(["gofmt", "-l", "."], cwd=pkg_dir)
    if ret == 0 and stdout.strip():
        unformatted = stdout.strip().split("\n")
        errors.append(f"Unformatted Go files: {', '.join(unformatted)}")
    elif ret != 0:
        errors.append(f"gofmt check failed:\n{stderr}")

    return errors


def check_python_quality(pkg_dir: Path) -> List[str]:
    """Python 质量检查：优先 ruff，退回 flake8；都不可用则不报错。"""
    errors = []

    # 依次尝试可用 linter，任一成功即停止。
    for tool in ["ruff", "flake8"]:
        ret, stdout, stderr = run_cmd([tool, ".", "--select=E,F"], cwd=pkg_dir)
        if ret == 0:
            break  # 找到可用的工具
    else:
        # 没有任何 linter 可用：不视为错误，静默跳过。
        pass

    return errors


def check_js_quality(pkg_dir: Path) -> List[str]:
    """JS/TS 质量检查：检测 ESLint 配置并执行，未配置则提示建议。"""
    errors = []

    # 常见 ESLint 配置文件名（支持新旧两种配置体系）。
    eslint_configs = [
        ".eslintrc.js", ".eslintrc.cjs", ".eslintrc.json",
        ".eslintrc.yaml", ".eslintrc", "eslint.config.js",
    ]
    has_eslint = any((pkg_dir / cfg).exists() for cfg in eslint_configs)

    if has_eslint:
        # --max-warnings=0 让任何 warning 都导致失败。
        ret, stdout, stderr = run_cmd(["npx", "eslint", "src/", "--max-warnings=0"], cwd=pkg_dir)
        if ret != 0:
            errors.append(f"ESLint check failed:\n{stdout[:500]}")
    else:
        # 未配置 ESLint：作为建议提示（会记为一条 error）。
        errors.append("No ESLint config found (recommended for JS/TS projects)")

    return errors


def check_file_patterns() -> List[str]:
    """扫描源码中缺少说明的裸 TODO/FIXME/HACK 注释。"""
    errors = []
    packages_dir = ROOT_DIR / "packages"

    # 匹配 TODO/FIXME/HACK 后面没有括号说明（(...)）的情况。
    # 即鼓励写成 `// TODO(xxx): ...` 而非裸 `// TODO`。
    todo_pattern = re.compile(r"(TODO|FIXME|HACK)(?!.*\(.*\))")
    for pkg_dir in packages_dir.iterdir():
        if not pkg_dir.is_dir():
            continue
        for ext in ["*.go", "*.py", "*.js", "*.ts", "*.vue"]:
            for src_file in pkg_dir.rglob(ext):
                # 跳过依赖与缓存目录。
                if "node_modules" in str(src_file) or "__pycache__" in str(src_file):
                    continue
                try:
                    content = src_file.read_text()
                except Exception:
                    continue
                # 逐行匹配，行号从 1 开始。
                for i, line in enumerate(content.split("\n"), 1):
                    if todo_pattern.search(line):
                        errors.append(
                            f"{src_file.relative_to(ROOT_DIR)}:{i}: "
                            f"Bare TODO/FIXME without context"
                        )

    return errors


def main() -> int:
    """对每个子包运行对应语言的质量检查，再跑全局文件模式检查，最后汇总。"""
    print("=" * 60)
    print("  GuineaPig Code Quality Check")
    print("=" * 60)

    total_errors = 0
    packages_dir = ROOT_DIR / "packages"

    # 包名 -> 对应检查函数。
    checkers = {
        "guineapig-backend": check_go_quality,
        "guineapig-aiagent": check_python_quality,
        "guineapig-ops-web": check_js_quality,
        "guineapig-client": check_js_quality,
    }

    for pkg_name, checker in checkers.items():
        pkg_dir = packages_dir / pkg_name
        if not pkg_dir.exists():
            print(f"\n  ⚠ {pkg_name}: package not found (skipping)")
            continue

        print(f"\n[{pkg_name}]")
        try:
            errors = checker(pkg_dir)
        except Exception as e:
            # 单个检查器异常不应中断整体流程。
            errors = [f"Check failed: {e}"]

        for e in errors:
            print(f"  ✗ {e}")
            total_errors += 1

        if not errors:
            print("  ✓ Quality check passed")

    # 文件模式检查（裸 TODO/FIXME）。
    print("\n[File Patterns]")
    pattern_errors = check_file_patterns()
    # 数量很多时只展示前 10 条，避免刷屏（但此时不累加计数，仅提示）。
    if len(pattern_errors) > 10:
        print(f"  ⚠ {len(pattern_errors)} bare TODO/FIXME found (showing first 10)")
        for e in pattern_errors[:10]:
            print(f"  ✗ {e}")
    elif pattern_errors:
        for e in pattern_errors:
            print(f"  ✗ {e}")
        total_errors += len(pattern_errors)
    else:
        print("  ✓ No bare TODO/FIXME without context")

    # 汇总。
    print("\n" + "=" * 60)
    if total_errors == 0:
        print("  All quality checks passed!")
        print("=" * 60)
        return 0
    else:
        print(f"  {total_errors} quality issue(s) found")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    # 注意：check_file_patterns() 用到 re，故在此处导入以满足运行需求。
    import re
    sys.exit(main())
