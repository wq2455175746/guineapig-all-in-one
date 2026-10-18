#!/usr/bin/env python3
"""
Harness 自动更新器（Harness Auto-Updater）

用途
----
作为 PostCompact 钩子运行。当一次 AI 会话被压缩（compact）后，本脚本会：
  1. 从 stdin 读取钩子传入的 JSON；
  2. 以当前 .ai/CURRENT_FOCUS 状态保存一份 checkpoint；
  3. 向 .ai/traces/failures.log 追加一条会话事件；
  4. 刷新 CURRENT_FOCUS 的 updated_at 时间戳（不改动其它内容）；
  5. 清理同一 task_id 下过旧的 checkpoint（仅保留最近 MAX_CHECKPOINTS 个）。

它由 .claude/settings.local.json 的 PostCompact 钩子调用。
用法：echo '<hook json>' | python3 scripts/harness_autoupdate.py
      python3 scripts/harness_autoupdate.py --reason=<原因>
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# 仓库根目录；每个 task_id 保留的最大 checkpoint 数量。
ROOT_DIR = Path(__file__).resolve().parent.parent
MAX_CHECKPOINTS = 3  # 每个 task_id 仅保留最近 N 个 checkpoint


def read_stdin_input() -> dict:
    """从 stdin 读取钩子输入的 JSON。读取失败或为空时返回空字典。"""
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, Exception):
        return {}


def get_current_focus() -> dict:
    """读取 .ai/CURRENT_FOCUS；文件缺失或非法 JSON 时返回空字典。"""
    focus_file = ROOT_DIR / ".ai/CURRENT_FOCUS"
    if not focus_file.exists():
        return {}
    try:
        with open(focus_file) as f:
            return json.load(f)
    except (json.JSONDecodeError, Exception):
        return {}


def touch_current_focus(focus: dict) -> None:
    """仅更新 CURRENT_FOCUS 的 updated_at 时间戳，其它字段保持不变。"""
    focus_file = ROOT_DIR / ".ai/CURRENT_FOCUS"
    focus["updated_at"] = datetime.now().isoformat()
    with open(focus_file, "w") as f:
        json.dump(focus, f, indent=2, ensure_ascii=False)
        f.write("\n")


def save_checkpoint(focus: dict, reason: str = "compact") -> Path:
    """
    保存一份包含当前 focus 的 checkpoint 文件。

    文件名格式：task-<task_id>-<时间戳>.json，位于 .ai/checkpoints/。
    若 stdin 有钩子输入，则一并记录到 hook_input 字段。
    """
    task_id = focus.get("task_id", "unknown")
    checkpoint_dir = ROOT_DIR / ".ai/checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    checkpoint_file = checkpoint_dir / f"task-{task_id}-{timestamp}.json"

    summary = {
        "timestamp": datetime.now().isoformat(),
        "reason": reason,          # 触发原因（如 compact）
        "focus": focus,            # 当时的任务焦点快照
        "session_end": True,       # 标记为一次会话结束
    }

    # 若 PostCompact 钩子传入了输入，则附带到快照中。
    stdin_input = read_stdin_input()
    if stdin_input:
        summary["hook_input"] = stdin_input

    with open(checkpoint_file, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
        f.write("\n")

    return checkpoint_file


def clean_old_checkpoints(focus: dict) -> int:
    """删除同一 task_id 的旧 checkpoint，仅保留最近 MAX_CHECKPOINTS 个。返回删除数量。"""
    task_id = focus.get("task_id", "unknown")
    checkpoint_dir = ROOT_DIR / ".ai/checkpoints"

    # 按修改时间倒序列出该 task 的所有 checkpoint。
    checkpoints = sorted(
        [f for f in checkpoint_dir.glob(f"task-{task_id}-*.json")],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )

    # 保留前 MAX_CHECKPOINTS 个，其余删除。
    removed = 0
    for old_cp in checkpoints[MAX_CHECKPOINTS:]:
        old_cp.unlink()
        removed += 1

    return removed


def log_session_event(focus: dict, reason: str = "compact") -> None:
    """向 .ai/traces/failures.log 追加一条会话事件日志。"""
    log_file = ROOT_DIR / ".ai/traces/failures.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    task_id = focus.get("task_id", "unknown")
    task_name = focus.get("task_name", "unknown")
    status = focus.get("status", "unknown")

    # 统一日志格式：[时间] [级别] [来源] [触发方式] 详情
    entry = (
        f"[{timestamp}] [INFO] [harness] [auto] "
        f"Session {reason}: task={task_id} name={task_name} "
        f"status={status}\n"
    )

    with open(log_file, "a") as f:
        f.write(entry)


def main() -> int:
    reason = "compact"
    # 支持 --reason=xxx 覆盖默认原因（便于手动触发时标记）。
    if len(sys.argv) > 1 and sys.argv[1].startswith("--reason="):
        reason = sys.argv[1].split("=", 1)[1]

    focus = get_current_focus()
    # 没有 CURRENT_FOCUS 说明 harness 未初始化，直接跳过。
    if not focus:
        print("No CURRENT_FOCUS found, skipping harness auto-update")
        return 0

    # 保存 checkpoint。
    checkpoint_file = save_checkpoint(focus, reason)
    print(f"Checkpoint saved: {checkpoint_file.relative_to(ROOT_DIR)}")

    # 记录会话事件。
    log_session_event(focus, reason)

    # 刷新 CURRENT_FOCUS 时间戳。
    touch_current_focus(focus)
    print(f"CURRENT_FOCUS timestamp updated")

    # 清理旧 checkpoint。
    removed = clean_old_checkpoints(focus)
    if removed > 0:
        print(f"Cleaned {removed} old checkpoint(s) (max {MAX_CHECKPOINTS} kept per task)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
