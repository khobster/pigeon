"""Minimal template renderer. {{key}} placeholders, {{#key}}...{{/key}} optional blocks."""
import re

BLOCK = re.compile(r"\{\{#(\w+)\}\}(.*?)\{\{/\1\}\}", re.S)


def render(template: str, context: dict) -> str:
    """Fill {{key}} slots. A {{#key}}...{{/key}} block is dropped entirely
    when context[key] is falsy. Blocks may nest: outer blocks resolve first,
    then the scan repeats until no block markers remain."""
    out = template
    while True:
        m = BLOCK.search(out)
        if not m:
            break
        body = m.group(2) if context.get(m.group(1)) else ""
        out = out[: m.start()] + body + out[m.end():]
    for key, value in context.items():
        out = out.replace("{{" + key + "}}", str(value) if value is not None else "")
    return out
