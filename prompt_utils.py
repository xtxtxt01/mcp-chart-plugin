from __future__ import annotations

import re
from pathlib import Path
from typing import Any


_TEMPLATE_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def load_text_multi(path: Path) -> str:
    for encoding in ["utf-8", "utf-8-sig", "gb18030", "gbk"]:
        try:
            return path.read_text(encoding=encoding)
        except Exception:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def render_prompt_template(path: Path, values: dict[str, Any]) -> str:
    template = load_text_multi(path)
    missing: set[str] = set()

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            missing.add(key)
            return ""
        return str(values.get(key) or "")

    rendered = _TEMPLATE_VAR_RE.sub(_replace, template)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise KeyError(f"Missing prompt template values for {path.name}: {missing_text}")
    return rendered
