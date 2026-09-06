"""
Skill Load 服务 — 两阶段 skill 上下文加载：
Phase 1: LLM 选择与用户问题相关的 skills
Phase 2: 下载/读取选中 skill 的完整内容，注入 system prompt
Commands 解析：从 LLM 回复中提取 <commands> 块
"""

import asyncio
import json
import os
import re
import shutil
import zipfile

from app.config import settings
from app.core.log import logger
from app.core.llm_clients import get_async_llm_client
from app.core.oss_wrapper_utils import download_file_from_s3
from app.schemas.llm_models import SkillInfo
from app.services.langfuse_client import get_langfuse, is_langfuse_enabled
from app.services.zip_utils import extract_zip_safe

# 匹配 <commands>[JSON 数组]</commands>
COMMANDS_PATTERN = re.compile(
    r"<commands>\s*(\[[\s\S]*?\])\s*</commands>", re.IGNORECASE
)


# ========== Phase 1: Skill Selection ==========


async def select_relevant_skills(
    user_message: str,
    skills: list[SkillInfo],
    api_key: str,
    base_url: str,
    model: str,
    trace_id: str | None = None,
) -> list[str]:
    """
    Phase 1: 让 LLM 判断哪些 skill 与用户问题相关。
    返回选中 skill 的 name 列表，空列表表示无相关 skill。
    """
    if not skills:
        return []

    skill_list = "\n".join([f"- {s.name}: {s.description}" for s in skills])

    messages = [
        {
            "role": "system",
            "content": (
                "You are a skill selector. Given the user's message and available skills, "
                "determine which skills are relevant. "
                "Return ONLY a JSON array of skill names. "
                "If none are relevant, return an empty array []. "
                "Do not include any other text in your response."
            ),
        },
        {
            "role": "user",
            "content": f"Available skills:\n{skill_list}\n\nUser message: {user_message}",
        },
    ]

    client = get_async_llm_client(api_key=api_key, base_url=base_url, timeout=60.0)

    # ── Langfuse Generation Span ──
    langfuse_gen = None
    if is_langfuse_enabled():
        langfuse = get_langfuse()
        trace_ctx = {"trace_id": trace_id} if trace_id else None
        langfuse_gen = langfuse.start_observation(
            name="select-relevant-skills",
            as_type="generation",
            trace_context=trace_ctx,
            model=model,
            input={
                "system": messages[0]["content"][:200],
                "user": messages[1]["content"][:500],
            },
            metadata={"source": "skill_load_service.select_relevant_skills"},
        )

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.1,
            max_tokens=500,
        )
    except Exception as e:
        logger.error(f"[SkillLoad] Phase 1 LLM call failed: {e}")
        if langfuse_gen:
            langfuse_gen.update(level="ERROR", status_message=str(e))
            langfuse_gen.end()
        return []

    text = response.choices[0].message.content or "[]"
    if langfuse_gen:
        usage = response.usage
        update_kwargs = {"output": text}
        if usage:
            update_kwargs["usage_details"] = {
                "input": usage.prompt_tokens,
                "output": usage.completion_tokens,
            }
        langfuse_gen.update(**update_kwargs)
        langfuse_gen.end()
    # 尝试从响应中提取 JSON 数组
    try:
        match = re.search(r"\[.*?\]", text, re.DOTALL)
        if match:
            result = json.loads(match.group(0))
            return [name for name in result if isinstance(name, str)]
    except (json.JSONDecodeError, ValueError):
        logger.warning(f"[SkillLoad] Phase 1 parse failed: {text}")

    return []


# ========== Phase 2: Skill Context Loading ==========


def _get_skill_dir(user_id: int, skill_name: str) -> str:
    """计算 skill 本地缓存目录"""
    return os.path.join(settings.DATA_DIR, "skills", str(user_id), skill_name)


def _ensure_skill_extracted(skill: SkillInfo, user_id: int) -> str:
    """确保 skill 已提取到本地，如不存在则从 S3 下载并解压。返回 skill 目录路径。"""
    skill_dir = _get_skill_dir(user_id, skill.name)
    if os.path.exists(skill_dir) and os.listdir(skill_dir):
        return skill_dir

    # 从 S3 下载并解压
    parent_dir = os.path.dirname(skill_dir)
    os.makedirs(parent_dir, exist_ok=True)
    zip_filename = skill.object_key.rstrip("/").split("/")[-1]
    if not zip_filename:
        zip_filename = f"{skill.name}.zip"
    local_zip_path = os.path.join(parent_dir, zip_filename)

    try:
        logger.info(f"[SkillLoad] Downloading from S3: {skill.object_key}")
        success = download_file_from_s3(skill.object_key, local_zip_path)
        if not success:
            logger.error(f"[SkillLoad] S3 download failed: {skill.object_key}")
            return skill_dir  # 返回可能存在的空目录

        # 解压，处理可能的公共顶层目录
        if os.path.exists(skill_dir):
            shutil.rmtree(skill_dir)
        os.makedirs(skill_dir, exist_ok=True)

        with zipfile.ZipFile(local_zip_path, "r") as zf:
            extract_zip_safe(zf, skill_dir)

        logger.info(f"[SkillLoad] Extracted to: {skill_dir}")

    except Exception as e:
        logger.error(f"[SkillLoad] Extract failed for {skill.name}: {e}")
    finally:
        if os.path.exists(local_zip_path):
            os.remove(local_zip_path)

    return skill_dir


def _read_skill_context(skill_dir: str) -> str:
    """读取 skill 目录内容，返回格式化上下文文本"""
    parts = []

    # 读取 SKILL.md
    md_path = os.path.join(skill_dir, "SKILL.md")
    if os.path.exists(md_path):
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()
        # 去除 YAML frontmatter
        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                content = content[end + 3 :].strip()
        parts.append(f"### Description\n{content[:2000]}")
    else:
        parts.append("### Description\n(No SKILL.md found)")

    # 读取 scripts 目录
    scripts_dir = os.path.join(skill_dir, "scripts")
    if os.path.exists(scripts_dir) and os.path.isdir(scripts_dir):
        scripts = []
        for fname in sorted(os.listdir(scripts_dir)):
            fpath = os.path.join(scripts_dir, fname)
            if os.path.isfile(fpath) and fname.endswith((".py", ".sh", ".js", ".md")):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    scripts.append(f"#### `{fname}`\n```\n{content[:2000]}\n```")
                except Exception:
                    scripts.append(f"#### `{fname}`\n(could not read)")
        if scripts:
            parts.append("### Scripts\n" + "\n\n".join(scripts))

    # 列出文件清单（限制 20 个）
    file_list = []
    for root, dirs, files in os.walk(skill_dir):
        for fname in files:
            rel = os.path.relpath(os.path.join(root, fname), skill_dir)
            if not rel.startswith("."):
                file_list.append(rel)
    if file_list:
        parts.append("### Files\n" + "\n".join(f"- `{f}`" for f in file_list[:20]))

    return "\n\n".join(parts)


async def load_skill_context(
    skill_names: list[str],
    user_id: int,
    skills: list[SkillInfo],
) -> str:
    """
    Phase 2: 加载选中 skill 的完整上下文。
    返回格式化的 context 字符串，用于注入 system prompt。
    """
    context_parts = []

    for skill in skills:
        if skill.name not in skill_names:
            continue

        # S3 下载 + 本地文件读取均为阻塞 I/O，放到线程池避免阻塞事件循环
        skill_dir = await asyncio.to_thread(_ensure_skill_extracted, skill, user_id)
        skill_context = await asyncio.to_thread(_read_skill_context, skill_dir)
        context_parts.append(f"## Skill: {skill.name}\n{skill_context}")

    return "\n\n---\n\n".join(context_parts)


def inject_skill_system_prompt(
    messages: list[dict],
    skill_context: str,
) -> list[dict]:
    """
    将 skill 上下文和命令生成规则注入到 system prompt。
    如果已有 system 消息则追加，否则插入新 system 消息。
    """
    commands_instruction = (
        "\n\n## Command Generation Rules\n"
        "You have the ability to execute shell/python/npx commands on the user's local machine. "
        "Only generate commands when the user's request genuinely requires local execution "
        "(e.g. open a file, run a script, query local data, install software, modify files).\n\n"
        "When to include commands:\n"
        "- User asks to open a file/folder/URL\n"
        "- User asks to run a local script or program\n"
        "- User asks to query or modify local data\n"
        "- User asks to install or update software\n\n"
        "When NOT to include commands:\n"
        "- General conversation, questions, or advice\n"
        "- Knowledge-based questions that don't need local execution\n\n"
        "If you decide to execute commands, "
        "include a commands block at the end of your response. "
        "Each command must include a risk level.\n"
        "- low: Read/query operations (ls, cat, open, read file, API query)\n"
        "- medium: Write/update operations (cp, mv, sed -i, install package, modify config)\n"
        "- high: Delete/destroy operations (rm -rf, drop, del, shutdown, format, clear data)\n\n"
        "Format:\n"
        "<commands>\n"
        '[{"type": "shell", "description": "what this does", '
        '"command": "the actual command", '
        '"cwd": "optional/relative/path", "risk": "low"}]\n'
        "</commands>"
    )

    if skill_context:
        skill_block = (
            f"\n\n## Available Skills\n{skill_context}\n{commands_instruction}"
        )
    else:
        skill_block = f"\n\n{commands_instruction}"

    for msg in messages:
        if msg.get("role") == "system":
            msg["content"] += skill_block
            return messages

    # 没有 system 消息，插入到最前面
    messages.insert(0, {"role": "system", "content": skill_block})
    return messages


# ========== Commands Parsing ==========


def parse_commands(full_content: str) -> tuple[str, list[dict]]:
    """
    从 LLM 回复中提取 <commands> 块。
    返回 (清理后的纯文本, commands 列表)。
    """
    match = COMMANDS_PATTERN.search(full_content)
    if not match:
        return full_content, []

    try:
        commands_data = json.loads(match.group(1))
        if not isinstance(commands_data, list):
            return full_content, []
        valid = []
        for cmd in commands_data:
            if all(k in cmd for k in ("type", "description", "command", "risk")):
                valid.append(
                    {
                        "type": cmd["type"],
                        "description": cmd["description"],
                        "command": cmd["command"],
                        "cwd": cmd.get("cwd", ""),
                        "risk": cmd["risk"],
                    }
                )
        commands = valid
    except (json.JSONDecodeError, ValueError):
        logger.warning(
            f"[SkillLoad] Commands parse failed, content: {full_content[-200:]}"
        )
        return full_content, []

    clean_content = COMMANDS_PATTERN.sub("", full_content).strip()
    return clean_content, commands
