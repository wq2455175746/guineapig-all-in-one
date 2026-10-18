#!/usr/bin/env python3
"""
GuineaPig 记忆更新器（Memory Updater）

用途
----
维护 .ai/ 工作区中的记忆类文件，提供三种操作：
  --checkpoint    保存当前任务状态快照（基于 .ai/CURRENT_FOCUS）；
  --add           交互式向 lessons.json 追加一条经验教训；
  --failure MSG   向 traces/failures.log 记录一条失败。

用法：
  python3 scripts/update_memory.py --checkpoint
  python3 scripts/update_memory.py --add
  python3 scripts/update_memory.py --failure "报错信息" --service <服务名>
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# 仓库根目录（本文件位于 <root>/scripts/）。
ROOT_DIR = Path(__file__).resolve().parent.parent


def get_current_focus() -> dict:
    """读取 .ai/CURRENT_FOCUS；不存在时返回空字典。"""
    focus_file = ROOT_DIR / ".ai/CURRENT_FOCUS"
    if not focus_file.exists():
        return {}
    with open(focus_file) as fh:
        return json.load(fh)


def save_current_focus(data: dict) -> None:
    """将给定数据写回 .ai/CURRENT_FOCUS（UTF-8、保留中文）。"""
    focus_file = ROOT_DIR / ".ai/CURRENT_FOCUS"
    with open(focus_file, "w") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def save_checkpoint() -> None:
    """基于当前 focus 保存一份 checkpoint 到 .ai/checkpoints/。"""
    focus = get_current_focus()
    if not focus:
        print("✗ No CURRENT_FOCUS found. Run 'make init' first.")
        return

    task_id = focus.get("task_id", "unknown")
    checkpoint_dir = ROOT_DIR / ".ai/checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    checkpoint_file = checkpoint_dir / f"task-{task_id}-{timestamp}.json"

    checkpoint_data = {
        "timestamp": datetime.now().isoformat(),
        "focus": focus,
        "files_changed": [],  # 可由 CI 后续填充变更文件列表
    }

    with open(checkpoint_file, "w") as fh:
        json.dump(checkpoint_data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    print(f"✓ Checkpoint saved: {checkpoint_file.relative_to(ROOT_DIR)}")


def add_lesson(lesson_type: str, title: str, context: str, action: str, tags: list) -> None:
    """向 lessons.json 追加一条经验教训，并自动分配递增 ID（如 L001）。"""
    lessons_file = ROOT_DIR / ".ai/memory/lessons.json"

    # 读取已有教训；文件不存在或内容非法时从空结构开始。
    try:
        with open(lessons_file) as fh:
            content = fh.read().strip()
            data = json.loads(content) if content else {"lessons": []}
    except (FileNotFoundError, json.JSONDecodeError):
        data = {"lessons": []}

    # 扫描已有 ID，计算下一个序号（ID 形如 L001、L002 ...）。
    existing_ids = [l.get("id", "") for l in data["lessons"]]
    max_num = 0
    for lid in existing_ids:
        if lid.startswith("L"):
            try:
                max_num = max(max_num, int(lid[1:]))
            except ValueError:
                pass

    # 组装新教训记录。
    lesson = {
        "id": f"L{max_num + 1:03d}",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "type": lesson_type,
        "title": title,
        "context": context,
        "action": action,
        "tags": tags,
    }

    data["lessons"].append(lesson)

    with open(lessons_file, "w") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    print(f"✓ Lesson {lesson['id']} added: {title}")


def add_failure(service: str, task_id: str, message: str, severity: str = "ERROR") -> None:
    """向 traces/failures.log 追加一条失败记录。"""
    failures_file = ROOT_DIR / ".ai/traces/failures.log"
    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    # 统一格式：[时间] [级别] [服务] [任务ID] 消息
    entry = f"[{timestamp}] [{severity}] [{service}] [{task_id}] {message}\n"

    with open(failures_file, "a") as fh:
        fh.write(entry)

    print(f"✓ Failure logged: {message[:80]}...")


def interactive_add() -> None:
    """交互式收集字段并调用 add_lesson 追加教训。"""
    print("=== Add New Lesson ===")
    print()

    # 选择教训类型。
    types = ["architecture", "pattern", "config", "design", "bugfix", "deployment"]
    print("Lesson types:")
    for i, t in enumerate(types):
        print(f"  [{i}] {t}")
    type_idx = input("Select type [0]: ").strip()
    try:
        # 直接回车取默认（第 0 项），越界或非数字也回退到第 0 项。
        lesson_type = types[int(type_idx)] if type_idx else types[0]
    except (ValueError, IndexError):
        lesson_type = types[0]

    title = input("Title: ").strip()
    if not title:
        print("✗ Title is required")
        return

    context = input("Context (when/where this was learned): ").strip()
    action = input("Action (what to do in future): ").strip()
    tags_input = input("Tags (comma-separated): ").strip()
    # 将逗号分隔的标签串拆成去空白的列表。
    tags = [t.strip() for t in tags_input.split(",") if t.strip()] if tags_input else []

    add_lesson(lesson_type, title, context, action, tags)


def main() -> int:
    """解析命令行参数并分派到 checkpoint / add / failure 三种操作。"""
    parser = argparse.ArgumentParser(
        description="GuineaPig Memory Updater"
    )
    parser.add_argument(
        "--checkpoint",
        action="store_true",
        help="Save a checkpoint of current task state",
    )
    parser.add_argument(
        "--add",
        action="store_true",
        help="Interactively add a new lesson to memory",
    )
    parser.add_argument(
        "--failure",
        metavar="MESSAGE",
        help="Log a failure to traces/failures.log",
    )
    parser.add_argument(
        "--service",
        default="unknown",
        help="Service name for failure logging",
    )

    args = parser.parse_args()

    # 按优先级分派：checkpoint > add > failure。
    if args.checkpoint:
        save_checkpoint()
    elif args.add:
        interactive_add()
    elif args.failure:
        # 失败记录需要 task_id，从当前 focus 中读取。
        focus = get_current_focus()
        task_id = focus.get("task_id", "unknown")
        add_failure(args.service, task_id, args.failure)
    else:
        # 未给任何操作时打印帮助并以非零退出。
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
