#!/usr/bin/env python3
"""
GuineaPig 校验流水线（Validation Pipeline）

用途
----
在 `make validate` 时被调用（见根目录 Makefile 的 validate 目标），
用于对整个 monorepo 的「结构 / 必需文件 / 配置」做静态自检。

它不编译、不运行服务，只检查：
  1. 仓库根目录的关键文件是否存在（README、Makefile、.gitignore 等）；
  2. `.ai/` AI 工作区文件是否齐全、且其中的 JSON 合法；
  3. `docs/` 文档是否齐全、设计文档是否为空；
  4. `scripts/` 下的辅助脚本是否齐全且非空；
  5. `packages/` 下各子包是否包含各自语言所需的关键文件与目录；
  6. 全局配置文件（pre-commit、docker-compose、Makefile 目标）是否就绪；
  7. 针对 Go 后端、Vue 前端的额外规则检查。

退出码
------
  0 = 无错误（可能有 warning）；1 = 存在 error。
  也就是说 warning 只提示，不会让 CI / 命令失败。

约定
----
  error(...) —— 计入 total_errors，最终导致退出码为 1；
  warn(...)  —— 仅提示，不影响退出码；
  check(...) —— 表示该项检查通过。
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

# 项目根目录：本文件位于 <root>/scripts/validate.py，因此 parent.parent 即仓库根。
ROOT_DIR = Path(__file__).resolve().parent.parent

# 各子包的校验规则表：
#   key           = packages/ 下的目录名
#   language      = 该包语言（目前仅作为元数据记录，未参与判断）
#   required_files= 该包内必须存在的文件（相对于包目录）
#   required_dirs = 该包内必须存在的目录（相对于包目录）
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

# `.ai/` AI 工作区必须包含的文件：
# 用于跨会话保存项目上下文（当前焦点、经验教训、反模式、架构规则、失败记录等）。
AI_REQUIRED_FILES = [
    ".ai/AGENTS.md",
    ".ai/CURRENT_FOCUS",
    ".ai/memory/lessons.json",
    ".ai/memory/anti-patterns.md",
    ".ai/memory/successful-patterns.md",
    ".ai/traces/failures.log",
    ".ai/rules/architecture.md",
]

# `docs/` 必须存在的文档文件（架构、开发、产品感知，以及设计/执行计划模板）。
DOCS_REQUIRED_FILES = [
    "docs/ARCHITECTURE.md",
    "docs/DEVELOPMENT.md",
    "docs/PRODUCT_SENSE.md",
    "docs/design-docs/template.md",
    "docs/exec-plans/active/README.md",
    "docs/exec-plans/completed/README.md",
]

# `scripts/` 下的辅助脚本白名单，缺一不可（且内容不能为空）。
SCRIPTS_REQUIRED_FILES = [
    "scripts/validate.py",
    "scripts/check_dependencies.py",
    "scripts/check_quality.py",
    "scripts/update_memory.py",
    "scripts/generate-from-template.py",
    "scripts/harness_autoupdate.py",
]

# `templates/` 下必须存在的模板文件。
TEMPLATES_REQUIRED_FILES = [
    "templates/architecture-schema.json",
]


def check(message: str) -> None:
    """打印「通过」标记：✓ + 消息。"""
    print(f"  ✓ {message}")


def warn(message: str) -> None:
    """打印「警告」标记：⚠ + 消息（不导致校验失败）。"""
    print(f"  ⚠ {message}")


def error(message: str) -> None:
    """打印「错误」标记：✗ + 消息（会导致校验失败）。"""
    print(f"  ✗ {message}")


def validate_package(pkg_dir: Path, config: dict) -> List[str]:
    """
    校验单个子包是否满足其配置中声明的必需文件 / 目录。

    参数:
        pkg_dir: 子包目录（如 packages/guineapig-backend）
        config:  来自 PACKAGES 的该包规则字典

    返回:
        错误消息列表；列表为空表示通过。
    """
    errors = []
    pkg_name = pkg_dir.name

    # 包目录本身都要不存在，则直接返回，后续检查无意义。
    if not pkg_dir.exists():
        errors.append(f"Package directory not found: {pkg_dir}")
        return errors

    # 检查必需文件（普通文件即可，不校验内容）。
    for rf in config.get("required_files", []):
        if not (pkg_dir / rf).exists():
            errors.append(f"{pkg_name}: missing required file '{rf}'")

    # 检查必需目录（必须是目录，而非同名文件）。
    for rd in config.get("required_dirs", []):
        if not (pkg_dir / rd).is_dir():
            errors.append(f"{pkg_name}: missing required directory '{rd}'")

    return errors


def validate_ai_files() -> List[str]:
    """
    校验 `.ai/` 工作区：
      - 必需文件是否齐全；
      - CURRENT_FOCUS 是否为合法 JSON 且包含约定字段；
      - lessons.json 是否为合法 JSON；
      - 顺带检查「新鲜度」（见 check_harness_freshness），其结果为 warning。
    """
    errors = []
    for f in AI_REQUIRED_FILES:
        if not (ROOT_DIR / f).exists():
            errors.append(f"Missing AI file: {f}")

    # 校验 CURRENT_FOCUS 是合法 JSON，并包含 service / task_id / status 等键。
    focus_file = ROOT_DIR / ".ai/CURRENT_FOCUS"
    if focus_file.exists():
        try:
            with open(focus_file) as fh:
                data = json.load(fh)
            # 期望的键：service（当前聚焦的服务）、task_id（任务 ID）、status（状态）。
            required_keys = ["service", "task_id", "status"]
            for key in required_keys:
                if key not in data:
                    errors.append(f"CURRENT_FOCUS missing key: {key}")
            # service 若已填写，应当是已知包名，或 None / "all"。
            # 未知值只提示，不报错（便于临时使用）。
            if data.get("service") and data["service"] not in [p for p in PACKAGES] + [None, "all"]:
                warn(f"CURRENT_FOCUS.service '{data['service']}' is not a known package")
        except json.JSONDecodeError as e:
            errors.append(f"CURRENT_FOCUS is invalid JSON: {e}")

    # 校验 lessons.json 为合法 JSON；允许空文件（视为无内容，不报错）。
    lessons_file = ROOT_DIR / ".ai/memory/lessons.json"
    if lessons_file.exists():
        try:
            with open(lessons_file) as fh:
                content = fh.read().strip()
                if content:
                    json.loads(content)
        except json.JSONDecodeError as e:
            errors.append(f"lessons.json is invalid JSON: {e}")

    # 检查 harness 数据是否过期，过期只产生 warning。
    freshness_warnings = check_harness_freshness()
    for w in freshness_warnings:
        warn(w)

    return errors


def check_harness_freshness() -> List[str]:
    """
    检查 AI 工作区数据是否「太久没更新」，用于提醒维护。

    规则:
      - CURRENT_FOCUS 超过 14 天未修改 -> warning；
      - lessons.json 中最新教训日期超过 30 天 -> warning。

    返回:
        warning 消息列表。
    """
    warnings = []

    # 依据 CURRENT_FOCUS 文件的最后修改时间判断新鲜度。
    focus_file = ROOT_DIR / ".ai/CURRENT_FOCUS"
    if focus_file.exists():
        mtime = datetime.fromtimestamp(focus_file.stat().st_mtime)
        days_old = (datetime.now() - mtime).days
        if days_old > 14:
            warnings.append(
                f"CURRENT_FOCUS last modified {days_old} days ago "
                f"({mtime.strftime('%Y-%m-%d')}) — consider updating"
            )

    # 依据 lessons.json 中最新一条经验的 date 字段判断新鲜度。
    lessons_file = ROOT_DIR / ".ai/memory/lessons.json"
    if lessons_file.exists():
        try:
            with open(lessons_file) as fh:
                data = json.load(fh)
            lessons = data.get("lessons", [])
            if lessons:
                # 取所有含 date 字段的条目中最新的日期（字符串按 ISO 格式可直接比较）。
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
            # 这里是「新鲜度」软检查，格式异常不在此处报错（合法性由 validate_ai_files 负责）。
            pass

    return warnings


def validate_docs_files() -> List[str]:
    """
    校验 `docs/` 目录：
      - 必需文档文件是否齐全；
      - docs/design-docs/*.md 是否都不为空文件。
    """
    errors = []
    for f in DOCS_REQUIRED_FILES:
        if not (ROOT_DIR / f).exists():
            errors.append(f"Missing docs file: {f}")

    # 设计文档目录存在时，逐个检查 *.md 是否有实际内容（空文件视为错误）。
    design_docs_dir = ROOT_DIR / "docs/design-docs"
    if design_docs_dir.exists():
        md_files = list(design_docs_dir.glob("*.md"))
        for mf in md_files:
            content = mf.read_text().strip()
            if not content:
                errors.append(f"Design doc is empty: {mf.relative_to(ROOT_DIR)}")

    return errors


def validate_configs() -> List[str]:
    """
    校验全局配置文件：
      - .pre-commit-config.yaml 是否存在；
      - docker-compose.dev.yml 是否存在；
      - Makefile 是否包含关键目标（缺少只 warning）。
    """
    errors = []

    # pre-commit 钩子配置（提交前自动检查）。
    precommit = ROOT_DIR / ".pre-commit-config.yaml"
    if not precommit.exists():
        errors.append("Missing .pre-commit-config.yaml")

    # 至少要有开发用的 docker compose 文件。
    docker_dev = ROOT_DIR / "docker-compose.dev.yml"
    if not docker_dev.exists():
        errors.append("Missing docker-compose.dev.yml")

    # Makefile 若存在，检查是否声明了约定目标（用 "target:" 子串粗略判断）。
    makefile = ROOT_DIR / "Makefile"
    if makefile.exists():
        content = makefile.read_text()
        expected_targets = ["validate", "test", "build-all", "clean", "init"]
        for target in expected_targets:
            if target + ":" not in content:
                warn(f"Makefile missing target: {target}")

    return errors


def validate_go_backend() -> List[str]:
    """
    针对 Go 后端（packages/guineapig-backend）的额外规则：
      - go.mod 的 module 名应合理（不符仅 warning）；
      - go.mod 不应引入 AI 相关依赖（AI 能力应放在 aiagent，违反则 error）。
    """
    errors = []
    backend_dir = ROOT_DIR / "packages/guineapig-backend"

    # 模块名应包含 guineapig 或 guineapig-backend。
    gomod = backend_dir / "go.mod"
    if gomod.exists():
        content = gomod.read_text()
        if "module guineapig" not in content and "module guineapig-backend" not in content:
            warn("go.mod module name may be incorrect")

    # 后端 go.mod 中若出现 AI 库名（openai/anthropic/whisper/tts/asr）则报错，
    # 强制把这些依赖隔离到 aiagent，保持后端职责单一。
    if gomod.exists():
        ai_imports = ["openai", "anthropic", "whisper", "tts", "asr"]
        for ai_import in ai_imports:
            if ai_import in content.lower():
                errors.append(
                    f"backend go.mod should not import AI library '{ai_import}' - use aiagent instead"
                )

    return errors


def validate_frontend() -> List[str]:
    """
    针对前端（packages/guineapig-ops-web）的额外规则：
      - package.json 若是合法 JSON，应包含 vue 依赖（否则 warning）；
      - package.json 若是非法 JSON，则报错。
    """
    errors = []
    frontend_dir = ROOT_DIR / "packages/guineapig-ops-web"

    pkg_json = frontend_dir / "package.json"
    if pkg_json.exists():
        try:
            with open(pkg_json) as fh:
                data = json.load(fh)
            # 粗略检查依赖声明里是否提到 vue。
            if "vue" not in str(data.get("dependencies", {})):
                warn("frontend package.json may not have Vue dependency")
        except json.JSONDecodeError:
            errors.append("frontend package.json is invalid JSON")

    return errors


def main() -> int:
    """
    校验流水线主入口，依次执行 6 个阶段的检查并汇总。

    返回:
        0 = 通过（可能有 warning）；1 = 存在 error。
    """
    print("=" * 60)
    print("  GuineaPig Validation Pipeline")
    print("=" * 60)

    total_errors = 0
    total_warnings = 0

    # 阶段 1：仓库根目录的关键文件是否存在。
    print("\n[1/6] Root-level files")
    for f in ["README.md", "Makefile", ".gitignore", ".pre-commit-config.yaml"]:
        if (ROOT_DIR / f).exists():
            check(f)
        else:
            error(f)
            total_errors += 1

    # 阶段 2：AI 工作区 .ai/ 的文件与内容合法性。
    print("\n[2/6] AI workspace (.ai/)")
    ai_errors = validate_ai_files()
    for e in ai_errors:
        error(e)
        total_errors += 1
    if not ai_errors:
        check("All AI workspace files present and valid")

    # 阶段 3：docs/ 文档齐全且非空。
    print("\n[3/6] Documentation (docs/)")
    doc_errors = validate_docs_files()
    for e in doc_errors:
        error(e)
        total_errors += 1
    if not doc_errors:
        check("All documentation files present")

    # 阶段 4：scripts/ 辅助脚本齐全且非空（空文件仅 warning）。
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

    # 阶段 5：packages/ 下各子包按 PACKAGES 规则校验。
    # 注意：包目录缺失只 warning（可能尚未创建），其余缺失项为 error。
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

    # 阶段 6：全局配置文件。
    print("\n[6/6] Configurations")
    config_errors = validate_configs()
    for e in config_errors:
        error(e)
        total_errors += 1

    # 附加检查：Go 后端专属规则（仅在包存在时执行）。
    if (ROOT_DIR / "packages/guineapig-backend").exists():
        go_errors = validate_go_backend()
        for e in go_errors:
            error(e)
            total_errors += 1

    # 附加检查：前端专属规则（仅在包存在时执行）。
    if (ROOT_DIR / "packages/guineapig-ops-web").exists():
        fe_errors = validate_frontend()
        for e in fe_errors:
            error(e)
            total_errors += 1

    # 汇总：无错误且无警告 -> 直接成功；
    # 有错误 -> 返回 1；仅有警告 -> 返回 0（不阻断流程）。
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
    # 以退出码作为 CI / make 的成败信号。
    sys.exit(main())
