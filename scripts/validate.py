#!/usr/bin/env python3
"""
GuineaPig Validation Pipeline
Validates project structure, required files, and configuration across all packages.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent

PACKAGES = {
    "guineapig-backend": {
        "language": "go",
        "required_files": ["main.go", "go.mod", "config.yaml", ".env.example", "Dockerfile", "Makefile"],
        "required_dirs": ["internal", "pkg", "config"],
    },
    "guineapig-aiagent": {
        "language": "python",
        "required_files": ["requirements.txt", "Dockerfile", "pyproject.toml"],
        "required_dirs": ["app"],
    },
    "guineapig-ops-web": {
        "language": "javascript",
        "required_files": ["package.json", "Dockerfile", "index.html"],
        "required_dirs": ["src"],
    },
    "guineapig-client": {
        "language": "javascript",
        "required_files": ["package.json"],
        "required_dirs": ["src"],
    },
}

AI_REQUIRED_FILES = [
    ".ai/AGENTS.md",
    ".ai/CURRENT_FOCUS",
    ".ai/memory/lessons.json",
    ".ai/memory/anti-patterns.md",
    ".ai/memory/successful-patterns.md",
    ".ai/traces/failures.log",
    ".ai/rules/architecture.md",
]

DOCS_REQUIRED_FILES = [
    "docs/ARCHITECTURE.md",
    "docs/DEVELOPMENT.md",
    "docs/PRODUCT_SENSE.md",
    "docs/design-docs/template.md",
    "docs/exec-plans/active/README.md",
    "docs/exec-plans/completed/README.md",
]

SCRIPTS_REQUIRED_FILES = [
    "scripts/validate.py",
    "scripts/check_dependencies.py",
    "scripts/check_quality.py",
    "scripts/update_memory.py",
    "scripts/generate-from-template.py",
    "scripts/harness_autoupdate.py",
]

TEMPLATES_REQUIRED_FILES = [
    "templates/architecture-schema.json",
]


def check(message: str) -> None:
    """Print a check message."""
    print(f"  ✓ {message}")


def warn(message: str) -> None:
    """Print a warning message."""
    print(f"  ⚠ {message}")


def error(message: str) -> None:
    """Print an error message."""
    print(f"  ✗ {message}")


def validate_package(pkg_dir: Path, config: dict) -> List[str]:
    """Validate a single package."""
    errors = []
    pkg_name = pkg_dir.name

    if not pkg_dir.exists():
        errors.append(f"Package directory not found: {pkg_dir}")
        return errors

    # Check required files
    for rf in config.get("required_files", []):
        if not (pkg_dir / rf).exists():
            errors.append(f"{pkg_name}: missing required file '{rf}'")

    # Check required directories
    for rd in config.get("required_dirs", []):
        if not (pkg_dir / rd).is_dir():
            errors.append(f"{pkg_name}: missing required directory '{rd}'")

    return errors


def validate_ai_files() -> List[str]:
    """Validate .ai/ directory files."""
    errors = []
    for f in AI_REQUIRED_FILES:
        if not (ROOT_DIR / f).exists():
            errors.append(f"Missing AI file: {f}")

    # Validate CURRENT_FOCUS is valid JSON
    focus_file = ROOT_DIR / ".ai/CURRENT_FOCUS"
    if focus_file.exists():
        try:
            with open(focus_file) as fh:
                data = json.load(fh)
            required_keys = ["service", "task_id", "status"]
            for key in required_keys:
                if key not in data:
                    errors.append(f"CURRENT_FOCUS missing key: {key}")
            if data.get("service") and data["service"] not in [p for p in PACKAGES] + [None, "all"]:
                warn(f"CURRENT_FOCUS.service '{data['service']}' is not a known package")
        except json.JSONDecodeError as e:
            errors.append(f"CURRENT_FOCUS is invalid JSON: {e}")

    # Validate lessons.json
    lessons_file = ROOT_DIR / ".ai/memory/lessons.json"
    if lessons_file.exists():
        try:
            with open(lessons_file) as fh:
                content = fh.read().strip()
                if content:
                    json.loads(content)
        except json.JSONDecodeError as e:
            errors.append(f"lessons.json is invalid JSON: {e}")

    # Check harness freshness
    freshness_warnings = check_harness_freshness()
    for w in freshness_warnings:
        warn(w)

    return errors


def check_harness_freshness() -> List[str]:
    """Check if harness files are up to date."""
    warnings = []

    # Check CURRENT_FOCUS last modified time
    focus_file = ROOT_DIR / ".ai/CURRENT_FOCUS"
    if focus_file.exists():
        mtime = datetime.fromtimestamp(focus_file.stat().st_mtime)
        days_old = (datetime.now() - mtime).days
        if days_old > 14:
            warnings.append(
                f"CURRENT_FOCUS last modified {days_old} days ago "
                f"({mtime.strftime('%Y-%m-%d')}) — consider updating"
            )

    # Check lessons.json for recency
    lessons_file = ROOT_DIR / ".ai/memory/lessons.json"
    if lessons_file.exists():
        try:
            with open(lessons_file) as fh:
                data = json.load(fh)
            lessons = data.get("lessons", [])
            if lessons:
                latest_date = max(l.get("date", "") for l in lessons if l.get("date"))
                if latest_date:
                    latest = datetime.strptime(latest_date, "%Y-%m-%d")
                    days_old = (datetime.now() - latest).days
                    if days_old > 30:
                        warnings.append(
                            f"lessons.json last updated {latest_date} "
                            f"({days_old} days ago) — consider adding recent lessons"
                        )
        except (json.JSONDecodeError, KeyError):
            pass

    return warnings


def validate_docs_files() -> List[str]:
    """Validate docs/ directory files."""
    errors = []
    for f in DOCS_REQUIRED_FILES:
        if not (ROOT_DIR / f).exists():
            errors.append(f"Missing docs file: {f}")

    # Check design-docs
    design_docs_dir = ROOT_DIR / "docs/design-docs"
    if design_docs_dir.exists():
        md_files = list(design_docs_dir.glob("*.md"))
        for mf in md_files:
            content = mf.read_text().strip()
            if not content:
                errors.append(f"Design doc is empty: {mf.relative_to(ROOT_DIR)}")

    return errors


def validate_configs() -> List[str]:
    """Validate configuration files."""
    errors = []

    # Check .pre-commit-config.yaml
    precommit = ROOT_DIR / ".pre-commit-config.yaml"
    if not precommit.exists():
        errors.append("Missing .pre-commit-config.yaml")

    # Check docker-compose files exist (at least dev)
    docker_dev = ROOT_DIR / "docker-compose.dev.yml"
    if not docker_dev.exists():
        errors.append("Missing docker-compose.dev.yml")

    # Check Makefile
    makefile = ROOT_DIR / "Makefile"
    if makefile.exists():
        content = makefile.read_text()
        expected_targets = ["validate", "test", "build-all", "clean", "init"]
        for target in expected_targets:
            if target + ":" not in content:
                warn(f"Makefile missing target: {target}")

    return errors


def validate_go_backend() -> List[str]:
    """Validate Go backend specifics."""
    errors = []
    backend_dir = ROOT_DIR / "packages/guineapig-backend"

    # Check go.mod has correct module name
    gomod = backend_dir / "go.mod"
    if gomod.exists():
        content = gomod.read_text()
        if "module guineapig" not in content and "module guineapig-backend" not in content:
            warn("go.mod module name may be incorrect")

    # Check no AI dependencies in go.mod
    if gomod.exists():
        ai_imports = ["openai", "anthropic", "whisper", "tts", "asr"]
        for ai_import in ai_imports:
            if ai_import in content.lower():
                errors.append(
                    f"backend go.mod should not import AI library '{ai_import}' - use aiagent instead"
                )

    return errors


def validate_frontend() -> List[str]:
    """Validate frontend specifics."""
    errors = []
    frontend_dir = ROOT_DIR / "packages/guineapig-ops-web"

    pkg_json = frontend_dir / "package.json"
    if pkg_json.exists():
        try:
            with open(pkg_json) as fh:
                data = json.load(fh)
            if "vue" not in str(data.get("dependencies", {})):
                warn("frontend package.json may not have Vue dependency")
        except json.JSONDecodeError:
            errors.append("frontend package.json is invalid JSON")

    return errors


def main() -> int:
    """Run full validation pipeline."""
    print("=" * 60)
    print("  GuineaPig Validation Pipeline")
    print("=" * 60)

    total_errors = 0
    total_warnings = 0

    # 1. Validate root-level files
    print("\n[1/6] Root-level files")
    for f in ["README.md", "Makefile", ".gitignore", ".pre-commit-config.yaml"]:
        if (ROOT_DIR / f).exists():
            check(f)
        else:
            error(f)
            total_errors += 1

    # 2. Validate .ai/ directory
    print("\n[2/6] AI workspace (.ai/)")
    ai_errors = validate_ai_files()
    for e in ai_errors:
        error(e)
        total_errors += 1
    if not ai_errors:
        check("All AI workspace files present and valid")

    # 3. Validate docs/
    print("\n[3/6] Documentation (docs/)")
    doc_errors = validate_docs_files()
    for e in doc_errors:
        error(e)
        total_errors += 1
    if not doc_errors:
        check("All documentation files present")

    # 4. Validate scripts/
    print("\n[4/6] Scripts (scripts/)")
    for f in SCRIPTS_REQUIRED_FILES:
        script_path = ROOT_DIR / f
        if script_path.exists():
            content = script_path.read_text().strip()
            if not content:
                warn(f"{f} is empty")
                total_warnings += 1
            else:
                check(f)
        else:
            error(f"Missing script: {f}")
            total_errors += 1

    # 5. Validate packages
    print("\n[5/6] Packages")
    for pkg_name, config in PACKAGES.items():
        pkg_dir = ROOT_DIR / "packages" / pkg_name
        if not pkg_dir.exists():
            warn(f"Package directory not found: {pkg_name} (may not be created yet)")
            total_warnings += 1
            continue

        pkg_errors = validate_package(pkg_dir, config)
        if pkg_errors:
            for e in pkg_errors:
                error(e)
                total_errors += 1
        else:
            check(f"{pkg_name}: all required files present")

    # 6. Validate configurations
    print("\n[6/6] Configurations")
    config_errors = validate_configs()
    for e in config_errors:
        error(e)
        total_errors += 1

    # Go backend specific checks
    if (ROOT_DIR / "packages/guineapig-backend").exists():
        go_errors = validate_go_backend()
        for e in go_errors:
            error(e)
            total_errors += 1

    # Frontend specific checks
    if (ROOT_DIR / "packages/guineapig-ops-web").exists():
        fe_errors = validate_frontend()
        for e in fe_errors:
            error(e)
            total_errors += 1

    # Summary
    print("\n" + "=" * 60)
    if total_errors == 0 and total_warnings == 0:
        print("  All validations passed!")
        print("=" * 60)
        return 0
    else:
        print(f"  Errors: {total_errors}, Warnings: {total_warnings}")
        print("=" * 60)
        if total_errors > 0:
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(main())
