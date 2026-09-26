"""parse_commands 回归测试 — 容忍 LLM 输出不闭合的 <commands> 块"""

import pytest

from app.services.skill_load_service import inject_skill_system_prompt, parse_commands


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


class TestCommandGenerationRulesPrompt:
    """命令生成规则 prompt 必须约束 LLM 不要使用 shell 重定向/管道等元字符。

    回归：LLM 曾生成 `cat > ~/Downloads/x.doc << 'EOF' ... EOF`，
    被 client 端 execute-command 参数安全校验拒绝（SAFE_ARG_TOKEN）。
    """

    def _system_prompt(self) -> str:
        messages = inject_skill_system_prompt(
            [{"role": "user", "content": "hi"}],
            skill_context="",
        )
        system = next(m for m in messages if m.get("role") == "system")
        return system["content"]

    def test_prompt_forbids_shell_redirection(self):
        prompt = self._system_prompt()
        assert "redirection" in prompt
        assert "heredoc" in prompt
        assert ">>" in prompt
        assert "|" in prompt

    def test_prompt_instructs_file_write_with_whitelisted_binaries(self):
        prompt = self._system_prompt()
        assert "python3" in prompt
        assert "printf" in prompt
        assert "cp" in prompt

    def test_prompt_appends_to_existing_system_message(self):
        messages = [
            {"role": "system", "content": "base system"},
            {"role": "user", "content": "hi"},
        ]
        out = inject_skill_system_prompt(messages, skill_context="")
        assert len(out) == 2
        assert "base system" in out[0]["content"]
        assert "Command Generation Rules" in out[0]["content"]