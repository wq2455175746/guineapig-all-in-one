#!/usr/bin/env python3
"""
GuineaPig 代码生成器（Code Generator）

用途
----
基于 templates/ 目录中的 Jinja2 模板（*.j2 / *.json）生成代码或配置文件。
支持从 JSON 上下文文件读取变量，也支持在终端交互式补全模板中缺失的变量。

命令行：
  --list, -l                 列出可用模板
  -t/--template TEMPLATE     模板文件名（如 component.py.j2）
  -o/--output PATH           输出文件路径
  -c/--context JSON_FILE     （可选）提供模板变量的 JSON 文件

退出码：0 = 成功；1 = 参数缺失 / 出错。
用法：python3 scripts/generate-from-template.py --list
"""
import argparse
import json
import os
import sys
from pathlib import Path

# 仓库根目录与本脚本使用的模板目录。
ROOT_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT_DIR / "templates"


def check_jinja2() -> bool:
    """检测当前环境是否安装了 Jinja2。"""
    try:
        import jinja2
        return True
    except ImportError:
        return False


def render_template(template_name: str, context: dict) -> str:
    """用给定上下文渲染指定 Jinja2 模板，返回渲染后的字符串。"""
    try:
        from jinja2 import Environment, FileSystemLoader, TemplateNotFound
    except ImportError:
        print("✗ Jinja2 is not installed. Run: pip install jinja2")
        sys.exit(1)

    # 以 templates/ 作为模板根目录。
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template(template_name)
    return template.render(**context)


def list_templates() -> None:
    """打印 templates/ 下所有 .j2 与 .json 模板。"""
    print("Available templates:")
    for tmpl in sorted(TEMPLATES_DIR.glob("*.j2")):
        print(f"  {tmpl.name}")
    for tmpl in sorted(TEMPLATES_DIR.glob("*.json")):
        print(f"  {tmpl.name}")


def generate_from_template(template_name: str, output_path: str, context_file: str = None) -> None:
    """从模板生成文件的主逻辑：加载上下文 -> 补全变量 -> 渲染 -> 写文件。"""
    # 1) 加载上下文（若提供了 JSON 上下文文件）。
    context = {}
    if context_file:
        with open(context_file) as fh:
            if context_file.endswith(".json"):
                context = json.load(fh)
            else:
                print("✗ Context file must be JSON")
                sys.exit(1)

    # 2) 确认模板存在。
    template_path = TEMPLATES_DIR / template_name
    if not template_path.exists():
        print(f"✗ Template not found: {template_name}")
        print("  Available templates:")
        list_templates()
        sys.exit(1)

    # 3) 扫描模板中引用的变量，缺失的用交互式输入补全。
    template_content = template_path.read_text()
    jinja_vars = set()
    for line in template_content.split("\n"):
        # 简易提取 {{ variable }} 形式的变量名。
        import re
        matches = re.findall(r'\{\{\s*(\w+)\s*\}\}', line)
        jinja_vars.update(matches)
        # 同时提取 {% if var %} 中用作条件的变量。
        matches = re.findall(r'\{%\s*if\s+(\w+)', line)
        jinja_vars.update(matches)

    # 对每个尚未提供的变量询问用户；留空则用变量名本身作默认值。
    for var in sorted(jinja_vars):
        if var not in context:
            value = input(f"  Enter value for '{var}': ").strip()
            if value:
                context[var] = value
            else:
                context[var] = var  # 用变量名作为默认值

    # 4) 渲染模板。
    try:
        output = render_template(template_name, context)
    except Exception as e:
        print(f"✗ Template render failed: {e}")
        sys.exit(1)

    # 5) 写入输出文件（自动创建父目录；已存在时先确认是否覆盖）。
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.exists():
        confirm = input(f"  File '{output_path}' exists. Overwrite? [y/N]: ").strip().lower()
        if confirm != "y":
            print("  Aborted.")
            return

    with open(out_path, "w") as fh:
        fh.write(output)

    print(f"✓ Generated: {output_path}")


def main() -> int:
    """解析命令行参数并分派到 list 或生成逻辑。"""
    parser = argparse.ArgumentParser(
        description="GuineaPig Code Generator - Generate code from templates"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available templates",
    )
    parser.add_argument(
        "--template", "-t",
        metavar="TEMPLATE",
        help="Template file name (e.g., component.py.j2)",
    )
    parser.add_argument(
        "--output", "-o",
        metavar="PATH",
        help="Output file path",
    )
    parser.add_argument(
        "--context", "-c",
        metavar="JSON_FILE",
        help="JSON context file for template variables",
    )

    args = parser.parse_args()

    # 仅列出模板。
    if args.list:
        list_templates()
        return 0

    # 生成模式下 template 与 output 均为必填。
    if not args.template:
        parser.print_help()
        return 1

    if not args.output:
        parser.print_help()
        return 1

    generate_from_template(args.template, args.output, args.context)
    return 0


if __name__ == "__main__":
    sys.exit(main())
