#!/usr/bin/env python3
"""
Harness Auto-Updater — runs on PostCompact hook.

Reads stdin JSON (hook input), saves checkpoint, logs session events,
and keeps CURRENT_FOCUS up to date automatically.

Called from .claude/settings.local.json PostCompact hook.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
MAX_CHECKPOINTS = 3  # Keep only the N most recent checkpoints per task_id


def read_stdin_input() -> dict:
    """Read hook input JSON from stdin."""
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, Exception):
        return {}


def get_current_focus() -> dict:
    """Read current focus from .ai/CURRENT_FOCUS."""
    focus_file = ROOT_DIR / ".ai/CURRENT_FOCUS"
    if not focus_file.exists():
        return {}
    try:
        with open(focus_file) as f:
            return json.load(f)
    except (json.JSONDecodeError, Exception):
        return {}


def touch_current_focus(focus: dict) -> None:
    """Update the updated_at timestamp in CURRENT_FOCUS without changing content."""
    focus_file = ROOT_DIR / ".ai/CURRENT_FOCUS"
    focus["updated_at"] = datetime.now().isoformat()
    with open(focus_file, "w") as f:
        json.dump(focus, f, indent=2, ensure_ascii=False)
        f.write("\n")


def save_checkpoint(focus: dict, reason: str = "compact") -> Path:
    """Save a checkpoint with current focus state."""
    task_id = focus.get("task_id", "unknown")
    checkpoint_dir = ROOT_DIR / ".ai/checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    checkpoint_file = checkpoint_dir / f"task-{task_id}-{timestamp}.json"

    summary = {
        "timestamp": datetime.now().isoformat(),
        "reason": reason,
        "focus": focus,
        "session_end": True,
    }

    # Capture stdin input summary if available (from PostCompact hook)
    stdin_input = read_stdin_input()
    if stdin_input:
        summary["hook_input"] = stdin_input

    with open(checkpoint_file, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
        f.write("\n")

    return checkpoint_file


def clean_old_checkpoints(focus: dict) -> int:
    """Remove old checkpoints for the same task_id, keeping only MAX_CHECKPOINTS."""
    task_id = focus.get("task_id", "unknown")
    checkpoint_dir = ROOT_DIR / ".ai/checkpoints"

    # List all checkpoints for this task_id, sorted by mtime
    checkpoints = sorted(
        [f for f in checkpoint_dir.glob(f"task-{task_id}-*.json")],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )

    removed = 0
    for old_cp in checkpoints[MAX_CHECKPOINTS:]:
        old_cp.unlink()
        removed += 1

    return removed


def log_session_event(focus: dict, reason: str = "compact") -> None:
    """Log a session event to traces/failures.log."""
    log_file = ROOT_DIR / ".ai/traces/failures.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    task_id = focus.get("task_id", "unknown")
    task_name = focus.get("task_name", "unknown")
    status = focus.get("status", "unknown")

    entry = (
        f"[{timestamp}] [INFO] [harness] [auto] "
        f"Session {reason}: task={task_id} name={task_name} "
        f"status={status}\n"
    )

    with open(log_file, "a") as f:
        f.write(entry)


def main() -> int:
    reason = "compact"
    # Check if called with --reason flag (for flexibility)
    if len(sys.argv) > 1 and sys.argv[1].startswith("--reason="):
        reason = sys.argv[1].split("=", 1)[1]

    focus = get_current_focus()
    if not focus:
        print("No CURRENT_FOCUS found, skipping harness auto-update")
        return 0

    # Save checkpoint
    checkpoint_file = save_checkpoint(focus, reason)
    print(f"Checkpoint saved: {checkpoint_file.relative_to(ROOT_DIR)}")

    # Log session event
    log_session_event(focus, reason)

    # Update CURRENT_FOCUS timestamp
    touch_current_focus(focus)
    print(f"CURRENT_FOCUS timestamp updated")

    # Clean old checkpoints
    removed = clean_old_checkpoints(focus)
    if removed > 0:
        print(f"Cleaned {removed} old checkpoint(s) (max {MAX_CHECKPOINTS} kept per task)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
