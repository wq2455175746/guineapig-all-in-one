#!/usr/bin/env python3
"""
GuineaPig Layer Dependency Checker
Ensures architecture layer rules are followed:
- backend does NOT import AI libraries directly
- Packages do NOT import internal modules from other packages
- Dependency direction is correct (client -> backend -> aiagent)
"""
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Set

ROOT_DIR = Path(__file__).resolve().parent.parent

# Valid dependency direction (downstream only)
# backend depends on aiagent (calls its API)
# client/ops-web depend on backend
VALID_DEPENDENCIES = {
    "guineapig-backend": set(),  # can depend on nothing except standard libs
    "guineapig-client": {"guineapig-backend"},  # via HTTP/WS only
    "guineapig-ops-web": {"guineapig-backend"},  # via HTTP only
    "guineapig-aiagent": set(),  # no dependencies on other packages
}

# Forbidden: these packages must NOT directly import AI/ML libraries
FORBIDDEN_AI_IMPORTS = {
    "guineapig-backend": [
        "openai", "anthropic", "langchain", "llamaindex",
        "whisper", "faster-whisper", "sensevoice", "funasr",
        "chattts", "cosyvoice", "voxcpm",
        "transformers", "torch", "tensorflow",
        "mcp", "agent-skills",
    ],
}

# Forbidden: cross-package code imports
FORBIDDEN_CROSS_IMPORTS = {
    "guineapig-backend": ["guineapig-client", "guineapig-ops-web"],
    "guineapig-client": ["guineapig-backend/internal", "guineapig-aiagent"],
    "guineapig-ops-web": ["guineapig-backend/internal", "guineapig-aiagent"],
    "guineapig-aiagent": ["guineapig-backend/internal", "guineapig-client", "guineapig-ops-web"],
}


def check_go_dependencies(pkg_dir: Path, pkg_name: str) -> List[str]:
    """Check Go module dependencies."""
    errors = []
    gomod = pkg_dir / "go.mod"

    if not gomod.exists():
        return errors

    content = gomod.read_text()

    # Check forbidden AI imports
    forbidden = FORBIDDEN_AI_IMPORTS.get(pkg_name, [])
    for lib in forbidden:
        if lib in content.lower():
            errors.append(
                f"{pkg_name}/go.mod: imports AI library '{lib}'. "
                f"AI operations must go through guineapig-aiagent"
            )

    return errors


def check_python_dependencies(pkg_dir: Path, pkg_name: str) -> List[str]:
    """Check Python dependencies."""
    errors = []
    req_file = pkg_dir / "requirements.txt"

    if not req_file.exists():
        return errors

    # aiagent is allowed to import AI libraries, others are not
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
    """Check JavaScript/Node dependencies."""
    errors = []
    pkg_json = pkg_dir / "package.json"

    if not pkg_json.exists():
        return errors

    import json
    with open(pkg_json) as fh:
        data = json.load(fh)

    all_deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}

    # Frontend/client should not import AI libraries directly
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
    """Check if any forbidden package appears as a Go import."""
    import re
    # Match Go import paths: "guineapig-backend/internal/..."
    import_pattern = re.compile(r'import\s*\(\s*(.*?)\s*\)', re.DOTALL)
    single_import = re.compile(r'import\s+"([^"]+)"')

    # Check multi-line imports
    for match in import_pattern.finditer(content):
        block = match.group(1)
        for forbidden in forbidden_pkgs:
            if forbidden in block:
                return True

    # Check single-line imports
    for match in single_import.finditer(content):
        path = match.group(1)
        for forbidden in forbidden_pkgs:
            if forbidden in path:
                return True

    return False


def _check_py_imports(content: str, forbidden_pkgs: List[str]) -> bool:
    """Check if any forbidden package appears as a Python import."""
    import re
    for forbidden in forbidden_pkgs:
        pkg = forbidden.replace("-", "_")
        if re.search(rf'(import\s+{pkg}|from\s+{pkg}\s+import)', content):
            return True
    return False


def check_cross_package_imports() -> List[str]:
    """Check for cross-package code imports."""
    errors = []
    packages_dir = ROOT_DIR / "packages"

    for pkg_name, forbidden_pkgs in FORBIDDEN_CROSS_IMPORTS.items():
        pkg_dir = packages_dir / pkg_name
        if not pkg_dir.exists():
            continue

        # Check Go files (check actual imports, not URL strings)
        for go_file in pkg_dir.rglob("*.go"):
            content = go_file.read_text()
            if _check_go_imports(content, forbidden_pkgs):
                errors.append(
                    f"{go_file.relative_to(ROOT_DIR)}: imports forbidden package"
                )

        # Check Python files (skip __pycache__)
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
    """Run all dependency checks."""
    print("=" * 60)
    print("  GuineaPig Layer Dependency Check")
    print("=" * 60)

    total_errors = 0
    packages_dir = ROOT_DIR / "packages"

    # Check each package's dependencies
    for pkg_name in ["guineapig-backend", "guineapig-aiagent", "guineapig-ops-web", "guineapig-client"]:
        pkg_dir = packages_dir / pkg_name
        if not pkg_dir.exists():
            print(f"\n  ⚠ {pkg_name}: package not found (skipping)")
            continue

        print(f"\n[{pkg_name}]")

        # Check based on language
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

    # Check cross-package imports
    print("\n[Cross-Package Import Check]")
    cross_errors = check_cross_package_imports()
    for e in cross_errors:
        print(f"  ✗ {e}")
        total_errors += 1
    if not cross_errors:
        print("  ✓ No cross-package import violations")

    # Summary
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
