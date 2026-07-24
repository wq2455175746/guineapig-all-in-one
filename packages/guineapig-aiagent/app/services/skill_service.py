"""
Skill 处理服务 — 从 S3 下载 zip，解压，解析 SKILL.md，分析文件结构
"""

import json
import os
import re
import zipfile
import shutil

from app.config import settings
from app.core.log import logger
from app.core.oss_wrapper_utils import download_file_from_s3


def process_skill_zip(object_key: str) -> dict:
    """
    从 S3 下载 skill zip 文件，解压并解析 SKILL.md。

    Args:
        object_key: S3 对象键，格式 skills/{user_id}/{date}/{skill-name}.zip

    Returns:
        包含 name, desc, version, file_stat, metadata 的字典

    Raises:
        ValueError: objectKey 格式无效或 SKILL.md 缺少必填字段
        RuntimeError: 下载或解压失败
    """
    # 解析 objectKey: skills/{user_id}/{date}/{skill-name}.zip
    parts = object_key.split("/")
    if len(parts) < 4:
        raise ValueError(
            f"objectKey 格式无效: {object_key}，预期: skills/{{user_id}}/{{date}}/{{skill-name}}.zip"
        )

    user_id = parts[-3]
    date_str = parts[-2]
    zip_filename = parts[-1]

    # 去掉 .zip 后缀作为 skill 名称
    skill_name = os.path.splitext(zip_filename)[0]

    # 计算本地路径
    base_dir = settings.DATA_DIR
    skill_dir = os.path.join(base_dir, "skills", user_id)
    local_zip_path = os.path.join(skill_dir, zip_filename)
    extract_dir = os.path.join(skill_dir, skill_name)

    try:
        # Step 1: 下载 zip 文件
        os.makedirs(skill_dir, exist_ok=True)
        logger.info(f"[Skill] 从 S3 下载 zip: {object_key}")
        success = download_file_from_s3(object_key, local_zip_path)
        if not success:
            raise RuntimeError(f"从 S3 下载失败: {object_key}")

        # Step 2: 解压 zip — 自动处理 zip 内多一层顶层目录的情况
        logger.info(f"[Skill] 解压到: {extract_dir}")
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)
        os.makedirs(extract_dir, exist_ok=True)

        file_categories = {
            "scripts": [],
            "references": [],
            "assets": [],
            "others": [],
        }
        total_size = 0
        file_count = 0

        with zipfile.ZipFile(local_zip_path, "r") as zf:
            # 检测 zip 内所有文件是否共享一个公共顶级目录（如 skill-name/xxx）
            all_entries = [
                info for info in zf.infolist() if not info.filename.endswith("/")
            ]
            common_prefix = None
            if all_entries:
                first_slash = all_entries[0].filename.find("/")
                if first_slash != -1:
                    candidate = all_entries[0].filename[: first_slash + 1]
                    if all(e.filename.startswith(candidate) for e in all_entries):
                        common_prefix = candidate

            for info in zf.infolist():
                if info.filename.endswith("/"):
                    continue  # 跳过目录

                # 如果 zip 内有公共顶层目录，解压时去掉这层
                member_path = info.filename
                if common_prefix and member_path.startswith(common_prefix):
                    member_path = member_path[len(common_prefix) :]

                target_path = os.path.join(extract_dir, member_path)
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with zf.open(info) as source, open(target_path, "wb") as target:
                    target.write(source.read())

                file_count += 1
                total_size += info.file_size

                # 分类文件（使用去掉公共前缀后的相对路径）
                ext = os.path.splitext(member_path)[1].lower()
                name_lower = member_path.lower()
                if ext in (
                    ".py",
                    ".js",
                    ".ts",
                    ".go",
                    ".rs",
                    ".java",
                    ".sh",
                    ".bat",
                    ".ps1",
                    ".lua",
                ):
                    file_categories["scripts"].append(member_path)
                elif ext in (
                    ".md",
                    ".txt",
                    ".yaml",
                    ".yml",
                    ".json",
                    ".toml",
                    ".cfg",
                    ".ini",
                    ".conf",
                    ".env",
                    ".xml",
                ):
                    file_categories["references"].append(member_path)
                elif ext in (
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".gif",
                    ".svg",
                    ".ico",
                    ".wav",
                    ".mp3",
                    ".ogg",
                    ".ttf",
                    ".woff",
                    ".woff2",
                ):
                    file_categories["assets"].append(member_path)
                else:
                    # 按目录猜测: scripts/, references/, assets/
                    if name_lower.startswith("scripts") or name_lower.startswith(
                        "script"
                    ):
                        file_categories["scripts"].append(member_path)
                    elif name_lower.startswith("references") or name_lower.startswith(
                        "ref"
                    ):
                        file_categories["references"].append(member_path)
                    elif name_lower.startswith("assets") or name_lower.startswith(
                        "asset"
                    ):
                        file_categories["assets"].append(member_path)
                    else:
                        file_categories["others"].append(member_path)

        # Step 3: 读取 SKILL.md
        skill_md_path = os.path.join(extract_dir, "SKILL.md")
        logger.info(f"skill_md_path:{skill_md_path}")
        if not os.path.exists(skill_md_path):
            raise ValueError("SKILL.md 文件不存在")

        with open(skill_md_path, "r", encoding="utf-8") as f:
            skill_content = f.read()

        # 解析 SKILL.md
        parsed = _parse_skill_md(skill_content)
        name = parsed.get("name", "")
        description = parsed.get("description", "")
        version = parsed.get("version", "1.0.0")

        if not name:
            raise ValueError("SKILL.md 缺少必填字段: name")
        if not description:
            raise ValueError("SKILL.md 缺少必填字段: description")

        # Step 4: 构建 file_stat
        file_stat = {
            "scripts": file_categories["scripts"],
            "references": file_categories["references"],
            "assets": file_categories["assets"],
            "others": file_categories["others"],
        }

        # Step 5: 构建 metadata
        metadata = {
            "total_size": total_size,
            "file_count": file_count,
            "version": version,
        }

        logger.info(
            f"[Skill] 解析完成: name={name}, desc={description}, "
            f"version={version}, files={file_count}, size={total_size}"
        )

        return {
            "name": name,
            "description": description,
            "version": version,
            "file_stat": json.dumps(file_stat, ensure_ascii=False),
            "metadata": json.dumps(metadata, ensure_ascii=False),
        }

    except (ValueError, RuntimeError) as e:
        logger.error(f"[Skill] 处理失败: {e}")
        raise
    finally:
        # 清理临时 zip 文件
        if os.path.exists(local_zip_path):
            os.remove(local_zip_path)
            logger.debug(f"[Skill] 临时 zip 已删除: {local_zip_path}")


def _parse_skill_md(content: str) -> dict:
    """
    解析 SKILL.md 内容，提取 name, description, version 等字段。

    支持的格式：
    - YAML frontmatter: ---\nname: xxx\ndescription: xxx\nversion: x.x.x\n---
    - Markdown 标题: # skill-name\n\n## Description\n...\n## Version\nx.x.x
    - 键值对: name: xxx\ndescription: xxx

    Args:
        content: SKILL.md 文件内容

    Returns:
        包含 name, description, version 的字典
    """
    result = {"name": "", "description": "", "version": "1.0.0"}
    content = content.strip()

    # 尝试 YAML frontmatter — 正确处理 | 和 > 块标量
    if content.startswith("---"):
        end_idx = content.find("---", 3)
        if end_idx != -1:
            frontmatter = content[3:end_idx].strip()
            lines = frontmatter.split("\n")
            i = 0
            while i < len(lines):
                raw_line = lines[i]
                stripped = raw_line.strip()
                if not stripped or ":" not in stripped:
                    i += 1
                    continue

                key, _, value_head = stripped.partition(":")
                key = key.strip().lower()
                value_head = value_head.strip()

                if value_head == "|":
                    # Literal block scalar — 保留换行
                    block_lines = []
                    i += 1
                    while i < len(lines) and (
                        lines[i].startswith(" ") or lines[i].startswith("\t")
                    ):
                        block_lines.append(lines[i].strip())
                        i += 1
                    value = "\n".join(block_lines)
                elif value_head == ">":
                    # Folded block scalar — 合并为空格
                    block_lines = []
                    i += 1
                    while i < len(lines) and (
                        lines[i].startswith(" ") or lines[i].startswith("\t")
                    ):
                        block_lines.append(lines[i].strip())
                        i += 1
                    value = " ".join(block_lines)
                else:
                    # 普通单行值，去除引号
                    value = value_head.strip("\"'")
                    i += 1

                if key == "name":
                    result["name"] = value
                elif key in ("description", "desc"):
                    result["description"] = value
                elif key == "version":
                    result["version"] = value

            if result["name"] and result["description"]:
                return result

    # 尝试键值对解析（第一段）
    lines = content.split("\n")
    for line in lines[:30]:  # 只检查前30行
        line = line.strip()
        # 跳过空行和标题
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip().lower()
            value = value.strip()
            if key == "name" and not result["name"]:
                result["name"] = value
            elif key in ("description", "desc") and not result["description"]:
                result["description"] = value
            elif key == "version" and not result["version"]:
                result["version"] = value

    # 如果还找不到 name，尝试从 Markdown 标题提取
    if not result["name"]:
        for line in lines:
            line = line.strip()
            if line.startswith("# ") and not result["name"]:
                # 第一个 H1 作为 name
                result["name"] = line.lstrip("# ").strip()

    # 尝试从 Markdown 段落提取 description
    if not result["description"]:
        found_desc = False
        for line in lines:
            line_stripped = line.strip()
            if line_stripped.startswith("## Description") or line_stripped.startswith(
                "## description"
            ):
                found_desc = True
                continue
            if found_desc and line_stripped and not line_stripped.startswith("#"):
                result["description"] = line_stripped
                break

    return result
