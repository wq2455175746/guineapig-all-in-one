#!/usr/bin/env python3
"""
GuineaPig Memory Updater
Manages .ai/memory files with --checkpoint and --add commands.
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parent.parent


def get_current_focus() -> dict:
    """Read current focus from .ai/CURRENT_FOCUS."""
    focus_file = ROOT_DIR / ".ai/CURRENT_FOCUS"
    if not focus_file.exists():
        return {}
    with open(focus_file) as fh:
        return json.load(fh)


def save_current_focus(data: dict) -> None:
    """Save current focus to .ai/CURRENT_FOCUS."""
    focus_file = ROOT_DIR / ".ai/CURRENT_FOCUS"
    with open(focus_file, "w") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def save_checkpoint() -> None:
    """Save a checkpoint of current task state."""
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
        "files_changed": [],  # Can be populated by CI
    }

    with open(checkpoint_file, "w") as fh:
        json.dump(checkpoint_data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    print(f"✓ Checkpoint saved: {checkpoint_file.relative_to(ROOT_DIR)}")


def add_lesson(lesson_type: str, title: str, context: str, action: str, tags: list) -> None:
    """Add a new lesson to lessons.json."""
    lessons_file = ROOT_DIR / ".ai/memory/lessons.json"

    # Read existing lessons
    try:
        with open(lessons_file) as fh:
            content = fh.read().strip()
            data = json.loads(content) if content else {"lessons": []}
    except (FileNotFoundError, json.JSONDecodeError):
        data = {"lessons": []}

    # Generate new lesson ID
    existing_ids = [l.get("id", "") for l in data["lessons"]]
    max_num = 0
    for lid in existing_ids:
        if lid.startswith("L"):
            try:
                max_num = max(max_num, int(lid[1:]))
            except ValueError:
                pass

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
    """Log a failure to traces/failures.log."""
    failures_file = ROOT_DIR / ".ai/traces/failures.log"
    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    entry = f"[{timestamp}] [{severity}] [{service}] [{task_id}] {message}\n"

    with open(failures_file, "a") as fh:
        fh.write(entry)

    print(f"✓ Failure logged: {message[:80]}...")


def interactive_add() -> None:
    """Interactive mode to add a lesson."""
    print("=== Add New Lesson ===")
    print()

    # Lesson type
    types = ["architecture", "pattern", "config", "design", "bugfix", "deployment"]
    print("Lesson types:")
    for i, t in enumerate(types):
        print(f"  [{i}] {t}")
    type_idx = input("Select type [0]: ").strip()
    try:
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
    tags = [t.strip() for t in tags_input.split(",") if t.strip()] if tags_input else []

    add_lesson(lesson_type, title, context, action, tags)


def main() -> int:
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

    if args.checkpoint:
        save_checkpoint()
    elif args.add:
        interactive_add()
    elif args.failure:
        focus = get_current_focus()
        task_id = focus.get("task_id", "unknown")
        add_failure(args.service, task_id, args.failure)
    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
