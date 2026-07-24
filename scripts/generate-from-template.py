#!/usr/bin/env python3
"""
GuineaPig Code Generator
Generates code from Jinja2 templates in templates/ directory.
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT_DIR / "templates"


def check_jinja2() -> bool:
    """Check if Jinja2 is available."""
    try:
        import jinja2
        return True
    except ImportError:
        return False


def render_template(template_name: str, context: dict) -> str:
    """Render a Jinja2 template with context."""
    try:
        from jinja2 import Environment, FileSystemLoader, TemplateNotFound
    except ImportError:
        print("✗ Jinja2 is not installed. Run: pip install jinja2")
        sys.exit(1)

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template(template_name)
    return template.render(**context)


def list_templates() -> None:
    """List available templates."""
    print("Available templates:")
    for tmpl in sorted(TEMPLATES_DIR.glob("*.j2")):
        print(f"  {tmpl.name}")
    for tmpl in sorted(TEMPLATES_DIR.glob("*.json")):
        print(f"  {tmpl.name}")


def generate_from_template(template_name: str, output_path: str, context_file: str = None) -> None:
    """Generate code from a template."""
    # Load context
    context = {}
    if context_file:
        with open(context_file) as fh:
            if context_file.endswith(".json"):
                context = json.load(fh)
            else:
                print("✗ Context file must be JSON")
                sys.exit(1)

    # Check if template exists
    template_path = TEMPLATES_DIR / template_name
    if not template_path.exists():
        print(f"✗ Template not found: {template_name}")
        print("  Available templates:")
        list_templates()
        sys.exit(1)

    # Prompt for missing context values
    template_content = template_path.read_text()
    jinja_vars = set()
    for line in template_content.split("\n"):
        # Simple extraction of {{ variable }} patterns
        import re
        matches = re.findall(r'\{\{\s*(\w+)\s*\}\}', line)
        jinja_vars.update(matches)
        # Also find {% if var %} patterns
        matches = re.findall(r'\{%\s*if\s+(\w+)', line)
        jinja_vars.update(matches)

    for var in sorted(jinja_vars):
        if var not in context:
            value = input(f"  Enter value for '{var}': ").strip()
            if value:
                context[var] = value
            else:
                context[var] = var  # Use var name as default

    # Render
    try:
        output = render_template(template_name, context)
    except Exception as e:
        print(f"✗ Template render failed: {e}")
        sys.exit(1)

    # Write output
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

    if args.list:
        list_templates()
        return 0

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
