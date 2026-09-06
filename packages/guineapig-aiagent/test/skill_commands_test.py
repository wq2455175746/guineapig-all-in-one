"""parse_commands 回归测试 — 容忍 LLM 输出不闭合的 <commands> 块"""

import pytest

from app.services.skill_load_service import parse_commands


class TestParseCommands:
    def test_closed_block(self):
        content = (
            "好的，我来帮你。\n"
            "<commands>\n"
            '[{"type": "shell", "description": "打开本地默认浏览器", '
            '"command": "open http://www.baidu.com", "cwd": "", "risk": "low"}]\n'
            "</commands>"
        )
        clean, cmds = parse_commands(content)
        assert clean == "好的，我来帮你。"
        assert len(cmds) == 1
        assert cmds[0]["command"] == "open http://www.baidu.com"
        assert cmds[0]["risk"] == "low"

    def test_missing_closing_tag(self):
        """回归：LLM 输出缺 </commands> 闭合标签时也应解析成功"""
        content = (
            "打开默认浏览器：\n"
            "<commands> "
            '[{"type": "shell", "description": "打开本地默认浏览器", '
            '"command": "open http://www.baidu.com", "cwd": "", "risk": "low"}]'
        )
        clean, cmds = parse_commands(content)
        assert clean == "打开默认浏览器："
        assert len(cmds) == 1
        assert cmds[0]["description"] == "打开本地默认浏览器"

    def test_no_commands_returns_unchanged(self):
        content = "这是普通回复，没有命令。"
        clean, cmds = parse_commands(content)
        assert clean == content
        assert cmds == []

    def test_nested_json_arrays(self):
        """命令参数里含嵌套数组时，应以平衡括号正确截断"""
        content = (
            "<commands> "
            '[{"type": "python", "description": "跑脚本", '
            '"command": "python run.py --items [1,2,3]", "cwd": "", "risk": "low"}]'
            " 后面还有文本"
        )
        clean, cmds = parse_commands(content)
        assert "后面还有文本" in clean
        assert len(cmds) == 1
        assert cmds[0]["command"] == "python run.py --items [1,2,3]"

    def test_case_insensitive_tag(self):
        content = (
            "<COMMANDS>\n"
            '[{"type": "shell", "description": "x", "command": "ls", '
            '"cwd": "", "risk": "low"}]\n'
            "</COMMANDS>"
        )
        clean, cmds = parse_commands(content)
        assert len(cmds) == 1

    def test_invalid_json_returns_unchanged(self):
        content = "<commands> [not valid json] </commands>"
        clean, cmds = parse_commands(content)
        assert cmds == []

    def test_incomplete_command_fields_filtered(self):
        content = (
            "<commands>\n"
            '[{"type": "shell", "description": "ok", "command": "ls", '
            '"cwd": "", "risk": "low"}, {"type": "shell", "command": "no-desc"}]\n'
            "</commands>"
        )
        clean, cmds = parse_commands(content)
        assert len(cmds) == 1
        assert cmds[0]["command"] == "ls"