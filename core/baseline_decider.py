from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..clients.llm import SecureLLMClient
from ..config import BASELINE_PROMPT_PATH, DemoConfig


SUPPORTED_CHART_TAGS = [
    "empty",
    "radar",
    "bar-line",
    "sankey",
    "pie",
    "treemap",
    "sunburst",
    "funnel",
]

EMPTY_CHARTDATA_LITERALS = {"", "{}", "空", "empty", "none", "null", "n/a"}


def _load_text_multi(path: Path) -> str:
    for encoding in ["utf-8", "utf-8-sig", "gb18030", "gbk"]:
        try:
            return path.read_text(encoding=encoding)
        except Exception:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def load_baseline_prompt() -> str:
    return _load_text_multi(BASELINE_PROMPT_PATH)


def _compact(value: Any) -> str:
    return str(value or "").strip()


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _extract_tag_text(block: str, tag: str) -> str:
    match = re.search(rf"<{tag}>\s*(.*?)\s*</{tag}>", block, re.S | re.I)
    return match.group(1).strip() if match else ""


def _clean_json_text(raw: str) -> str:
    text = _compact(raw)
    if text.startswith("```"):
        text = re.sub(r"^```(?:json|xml)?", "", text, flags=re.I).strip()
        text = re.sub(r"```$", "", text).strip()
    return text


def _parse_chart_data(chart_tag: str, raw_text: str) -> dict[str, Any]:
    text = _clean_json_text(raw_text)
    if chart_tag == "empty" and text.casefold() in {item.casefold() for item in EMPTY_CHARTDATA_LITERALS}:
        return {}
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _parse_reference(raw_text: str) -> list[int]:
    text = _clean_json_text(raw_text)
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            refs: list[int] = []
            for item in parsed:
                index = _safe_int(item)
                if index is not None:
                    refs.append(index)
            return refs
    except Exception:
        return []
    return []


def _parse_chart_spec_xml(raw_text: str) -> dict[str, Any] | None:
    for chart_tag in SUPPORTED_CHART_TAGS:
        pattern = re.compile(rf"<{re.escape(chart_tag)}>\s*(.*?)\s*</{re.escape(chart_tag)}>", re.S | re.I)
        match = pattern.search(raw_text)
        if not match:
            continue
        block = match.group(1)
        chart_data = _parse_chart_data(chart_tag, _extract_tag_text(block, "chartData"))
        explain = _extract_tag_text(block, "explain")
        reference = _parse_reference(_extract_tag_text(block, "reference"))
        return {
            "chart_tag": chart_tag,
            "chart_data": chart_data,
            "explain": explain,
            "reference": reference,
        }
    return None


def _reference_payload(docs: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for idx, doc in enumerate(docs or []):
        payload.append(
            {
                "id": _safe_int(doc.get("prompt_id")) if _safe_int(doc.get("prompt_id")) is not None else idx,
                "content": _compact(doc.get("content")),
            }
        )
    return payload


def _build_llm_decision_user_prompt(task: dict[str, Any], docs: list[dict[str, Any]] | None) -> str:
    description = _compact(task.get("chart_description") or task.get("chart_title"))
    context = _compact(task.get("write_requirement"))
    references = _reference_payload(docs)
    return (
        "## 图表描述<description>\n"
        f"{description}\n\n"
        "## 上文内容\n"
        "```markdown\n"
        f"{context}\n"
        "```\n\n"
        "## 参考资料\n"
        "(如下资料中id为参考资料序号，content为资料内容)\n"
        f"{json.dumps(references, ensure_ascii=False, indent=2)}"
    )


def _empty_spec(reason: str, *, mode: str, error: str = "", raw_output: str = "") -> dict[str, Any]:
    spec = {
        "chart_tag": "empty",
        "chart_data": {},
        "explain": reason,
        "reference": [],
        "_decision_mode": mode,
    }
    if error:
        spec["_decision_error"] = error
    if raw_output:
        spec["_decision_raw_output"] = raw_output
    return spec


def decide_chart_spec(
    task: dict[str, Any],
    facts: list[dict[str, Any]],
    config: DemoConfig | None = None,
    docs: list[dict[str, Any]] | None = None,
    retrieval_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del facts
    del retrieval_plan

    cfg = config or DemoConfig()
    llm = SecureLLMClient(cfg, stage="chart_generation")
    ok, message = llm.available()
    if not ok:
        return _empty_spec(
            "模型不可用，无法完成基于 baseline prompt 的图表决策，因此返回 empty。",
            mode="llm_unavailable",
            error=message,
        )

    response = llm.call_text(
        system_prompt=load_baseline_prompt(),
        user_prompt=_build_llm_decision_user_prompt(task, docs),
        temperature=0.0,
    )
    if not response.ok or not response.content:
        return _empty_spec(
            "模型图表决策失败，无法得到合法 XML，因此返回 empty。",
            mode="llm_failed",
            error=_compact(response.error),
            raw_output=_compact(response.content),
        )

    parsed = _parse_chart_spec_xml(response.content)
    if parsed is None:
        return _empty_spec(
            "模型返回内容不是合法的图表 XML，无法继续渲染，因此返回 empty。",
            mode="llm_parse_failed",
            error="invalid_chart_xml",
            raw_output=response.content,
        )

    parsed["_decision_mode"] = "llm"
    parsed["_decision_raw_output"] = response.content
    parsed["_decision_error"] = ""
    return parsed


__all__ = ["SUPPORTED_CHART_TAGS", "load_baseline_prompt", "decide_chart_spec"]
