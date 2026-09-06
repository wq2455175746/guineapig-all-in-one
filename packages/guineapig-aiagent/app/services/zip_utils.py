"""
ZIP 安全解压工具 — 防止 ZIP Slip 路径穿越与 zip bomb。

skill 解压（skill_load_service / skill_service）共用此模块，
统一校验成员路径、限制解压总大小与条目数。
"""

import os
import zipfile

# 解压总大小上限（100MB）
MAX_EXTRACT_TOTAL_SIZE = 100 * 1024 * 1024
# 解压条目数上限
MAX_EXTRACT_FILE_COUNT = 1000


class UnsafeZipError(RuntimeError):
    """ZIP 校验失败（路径穿越或超出大小/条目数上限）。"""


def _detect_common_prefix(file_infos: list) -> str | None:
    """检测 zip 条目是否共享一个公共顶层目录（如 skill-name/），返回含尾部斜杠的前缀。"""
    if not file_infos:
        return None
    first_slash = file_infos[0].filename.find("/")
    if first_slash == -1:
        return None
    candidate = file_infos[0].filename[: first_slash + 1]
    if all(f.filename.startswith(candidate) for f in file_infos):
        return candidate
    return None


def safe_zip_target(extract_dir: str, member_path: str) -> str | None:
    """
    校验 zip 成员路径并返回其安全的绝对目标路径。

    拒绝绝对路径与含 `..` 段（ZIP Slip）的路径；非法时返回 None。
    解析后的目标路径必须位于 extract_dir 之下（防止前缀误匹配）。
    """
    member_path = member_path.replace("\\", "/")
    if member_path.startswith("/") or member_path.split("/", 1)[0] == "..":
        return None
    if any(part == ".." for part in member_path.split("/")):
        return None
    extract_dir_norm = os.path.normpath(extract_dir)
    target_path = os.path.normpath(os.path.join(extract_dir, member_path))
    if not target_path.startswith(extract_dir_norm + os.sep):
        return None
    return target_path


def extract_zip_safe(
    zf: zipfile.ZipFile,
    extract_dir: str,
    max_total_size: int = MAX_EXTRACT_TOTAL_SIZE,
    max_file_count: int = MAX_EXTRACT_FILE_COUNT,
) -> tuple[list, int]:
    """
    安全解压 zip 到 extract_dir，自动剥离公共顶层目录。

    逐条目校验路径（拒绝路径穿越），流式写入并统计实际字节数，
    超过总大小或条目数上限时抛 UnsafeZipError。

    Returns:
        (条目列表, 实际写入总字节数)；条目为 (ZipInfo, 去除公共前缀后的相对路径)。
    """
    os.makedirs(extract_dir, exist_ok=True)

    file_infos = [f for f in zf.infolist() if not f.filename.endswith("/")]
    if len(file_infos) > max_file_count:
        raise UnsafeZipError(f"zip 文件数超过上限 {max_file_count}，拒绝解压")

    common_prefix = _detect_common_prefix(file_infos)

    extracted = []
    total_written = 0
    for info in file_infos:
        raw_name = info.filename.replace("\\", "/")
        if (
            raw_name.startswith("/")
            or raw_name.split("/", 1)[0] == ".."
            or any(part == ".." for part in raw_name.split("/"))
        ):
            raise UnsafeZipError(f"非法 zip 条目路径: {info.filename}")

        member_path = info.filename
        if common_prefix and member_path.startswith(common_prefix):
            member_path = member_path[len(common_prefix) :]

        target_path = safe_zip_target(extract_dir, member_path)
        if target_path is None:
            raise UnsafeZipError(f"非法 zip 条目路径: {info.filename}")

        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with zf.open(info) as source, open(target_path, "wb") as target:
            while chunk := source.read(64 * 1024):
                total_written += len(chunk)
                if total_written > max_total_size:
                    raise UnsafeZipError(
                        f"zip 解压总大小超过上限 {max_total_size} 字节，拒绝解压"
                    )
                target.write(chunk)

        extracted.append((info, member_path))

    return extracted, total_written