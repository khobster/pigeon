"""Minimal template renderer. {{key}} placeholders, {{#key}}...{{/key}} optional blocks."""
import re


def render(template: str, context: dict) -> str:
    """Fill {{key}} slots. A {{#key}}...{{/key}} block is dropped entirely
    when context[key] is falsy, so a missing section leaves no residue."""
    out = template
    for m in re.finditer(r"\{\{#(\w+)\}\}(.*?)\{\{/\1\}\}", template, re.S):
        block = m.group(0)
        out = out.replace(block, m.group(2) if context.get(m.group(1)) else "")
    for key, value in context.items():
        out = out.replace("{{" + key + "}}", str(value) if value is not None else "")
    return out
