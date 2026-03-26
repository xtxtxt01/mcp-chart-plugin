from __future__ import annotations

import json
from typing import Any

from ..config import SCHEMAS_ROOT


def schema_file_path(name: str) -> str:
    return (SCHEMAS_ROOT / name).as_posix()


def schema_file_text(name: str) -> str:
    return (SCHEMAS_ROOT / name).read_text(encoding="utf-8")


def _load_schema_json(name: str) -> Any:
    return json.loads(schema_file_text(name))


def plan_chart_retrieval_tools() -> list[dict[str, Any]]:
    payload = _load_schema_json("plan_chart_retrieval.tools.json")
    if not isinstance(payload, list):
        raise TypeError("plan_chart_retrieval.tools.json must contain a JSON array.")
    return payload
