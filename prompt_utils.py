from __future__ import annotations

from pathlib import Path


def load_text_multi(path: Path) -> str:
    for encoding in ["utf-8", "utf-8-sig", "gb18030", "gbk"]:
        try:
            return path.read_text(encoding=encoding)
        except Exception:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")
