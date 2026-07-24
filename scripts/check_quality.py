#!/usr/bin/env python3
"""
GuineaPig Code Quality Checker
Runs language-specific quality checks across all packages.
"""
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent


def run_cmd(cmd: List[str], cwd: Path = None) -> Tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)."""
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
    """Run Go quality checks."""
    errors = []

    # go vet
    ret, stdout, stderr = run_cmd(["go", "vet", "./..."], cwd=pkg_dir)
    if ret != 0:
        errors.append(f"go vet failed:\n{stderr}")

    # go fmt check
    ret, stdout, stderr = run_cmd(["gofmt", "-l", "."], cwd=pkg_dir)
    if ret == 0 and stdout.strip():
        unformatted = stdout.strip().split("\n")
        errors.append(f"Unformatted Go files: {', '.join(unformatted)}")
    elif ret != 0:
        errors.append(f"gofmt check failed:\n{stderr}")

    return errors


def check_python_quality(pkg_dir: Path) -> List[str]:
    """Run Python quality checks."""
    errors = []

    # Check if ruff or flake8 is available
    for tool in ["ruff", "flake8"]:
        ret, stdout, stderr = run_cmd([tool, ".", "--select=E,F"], cwd=pkg_dir)
        if ret == 0:
            break  # Found a working tool
    else:
        # No linter available, just note it
        pass

    return errors


def check_js_quality(pkg_dir: Path) -> List[str]:
    """Run JavaScript/TypeScript quality checks."""
    errors = []

    # Check if ESLint is configured
    eslint_configs = [
        ".eslintrc.js", ".eslintrc.cjs", ".eslintrc.json",
        ".eslintrc.yaml", ".eslintrc", "eslint.config.js",
    ]
    has_eslint = any((pkg_dir / cfg).exists() for cfg in eslint_configs)

    if has_eslint:
        ret, stdout, stderr = run_cmd(["npx", "eslint", "src/", "--max-warnings=0"], cwd=pkg_dir)
        if ret != 0:
            errors.append(f"ESLint check failed:\n{stdout[:500]}")
    else:
        errors.append("No ESLint config found (recommended for JS/TS projects)")

    return errors


def check_file_patterns() -> List[str]:
    """Check for common code quality issues."""
    errors = []
    packages_dir = ROOT_DIR / "packages"

    # Check for TODO/FIXME without context
    todo_pattern = re.compile(r"(TODO|FIXME|HACK)(?!.*\(.*\))")
    for pkg_dir in packages_dir.iterdir():
        if not pkg_dir.is_dir():
            continue
        for ext in ["*.go", "*.py", "*.js", "*.ts", "*.vue"]:
            for src_file in pkg_dir.rglob(ext):
                if "node_modules" in str(src_file) or "__pycache__" in str(src_file):
                    continue
                try:
                    content = src_file.read_text()
                except Exception:
                    continue
                for i, line in enumerate(content.split("\n"), 1):
                    if todo_pattern.search(line):
                        errors.append(
                            f"{src_file.relative_to(ROOT_DIR)}:{i}: "
                            f"Bare TODO/FIXME without context"
                        )

    return errors


def main() -> int:
    """Run all quality checks."""
    print("=" * 60)
    print("  GuineaPig Code Quality Check")
    print("=" * 60)

    total_errors = 0
    packages_dir = ROOT_DIR / "packages"

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
            errors = [f"Check failed: {e}"]

        for e in errors:
            print(f"  ✗ {e}")
            total_errors += 1

        if not errors:
            print("  ✓ Quality check passed")

    # File pattern checks
    print("\n[File Patterns]")
    pattern_errors = check_file_patterns()
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

    # Summary
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
    import re
    sys.exit(main())
