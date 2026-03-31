from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

from ..clients import AggSearchClient, SecureLLMClient
from ..config import PACKAGE_ROOT, PluginConfig
from ..prompt_utils import load_text_multi
from ..schemas import plan_chart_retrieval_tools
from .baseline_decider import decide_chart_spec
from .renderer import build_no_chart_result, render_chart_artifacts

NUMERIC_HINT_RE = re.compile(r"\d")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[\u3002\uff01\uff1f!?\uff1b;])")
TITLE_NOISE_RE = re.compile(r"[\s\u3000:：,，.;；()（）\[\]【】'\"<>《》\-—_]+")
CHAPTER_PREFIX_RE = re.compile(
    r"^\s*(?:\u7b2c)?([0-9]+|[\u96f6\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u4e24]+)(?:[\u7ae0\u8282\u90e8\u7bc7])?[\u3001.\uff0e]"
)
KEYWORD_HINTS = [
    "\u5360\u6bd4",
    "\u5e02\u573a",
    "\u89c4\u6a21",
    "\u589e\u957f",
    "\u589e\u901f",
    "\u540c\u6bd4",
    "\u9884\u6d4b",
    "\u6570\u91cf",
    "\u4efd\u989d",
    "\u83b7\u6279",
    "\u7a81\u7834",
    "%",
]
CHINESE_DIGITS = {
    "\u96f6": 0,
    "\u4e00": 1,
    "\u4e8c": 2,
    "\u4e24": 2,
    "\u4e09": 3,
    "\u56db": 4,
    "\u4e94": 5,
    "\u516d": 6,
    "\u4e03": 7,
    "\u516b": 8,
    "\u4e5d": 9,
}


def _compact(value: Any) -> str:
    return str(value or "").strip()


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _ordered_unique(items: list[str], *, limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        text = _compact(item)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(text)
        if limit is not None and len(ordered) >= limit:
            break
    return ordered


def _trim_text(text: str, max_chars: int = 1800) -> str:
    value = _compact(text)
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3].rstrip() + "..."


def _stable_hash(*parts: Any, length: int = 10) -> str:
    joined = "\n".join(_compact(part) for part in parts if _compact(part))
    return hashlib.sha1(joined.encode("utf-8", "ignore")).hexdigest()[:length]


def _safe_path_token(text: str, default: str = "section") -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "-", _compact(text)).strip("-").lower()
    return normalized[:32] or default


def _config_from_dict(config_dict: dict[str, Any] | None) -> PluginConfig:
    cfg = PluginConfig()
    cfg.apply_overrides(config_dict)
    return cfg


def _split_text_units(text: str) -> list[str]:
    blocks = re.split(r"\n\s*\n", _compact(text))
    units: list[str] = []
    for block in blocks:
        block = _compact(block)
        if not block:
            continue
        if len(block) <= 240:
            units.append(block)
            continue
        fragments = [_compact(item) for item in SENTENCE_SPLIT_RE.split(block) if _compact(item)]
        if not fragments:
            units.append(block)
            continue
        current = ""
        for fragment in fragments:
            if not current:
                current = fragment
                continue
            if len(current) + len(fragment) <= 220:
                current += fragment
                continue
            units.append(current)
            current = fragment
        if current:
            units.append(current)
    return units


def _fragment_score(text: str) -> tuple[int, int]:
    value = _compact(text)
    score = 0
    if NUMERIC_HINT_RE.search(value):
        score += 10
    for keyword in KEYWORD_HINTS:
        if keyword in value:
            score += 3
    if 24 <= len(value) <= 220:
        score += 2
    return score, -len(value)


def _prioritized_fragments(*texts: str, limit: int = 6) -> list[str]:
    candidates: list[str] = []
    for text in texts:
        candidates.extend(_split_text_units(text))
    ranked = sorted(_ordered_unique(candidates), key=_fragment_score, reverse=True)
    return ranked[:limit]


def _find_deepreport_work_root() -> Path | None:
    candidates = [
        PACKAGE_ROOT.parent / "ai-deepreport" / "deep-report-go" / "work",
        PACKAGE_ROOT.parent / "deep-report-go" / "work",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _find_latest_report_dir() -> Path | None:
    work_root = _find_deepreport_work_root()
    if work_root is None:
        return None
    report_dirs = [path for path in work_root.glob("report-*") if path.is_dir()]
    if not report_dirs:
        return None
    report_dirs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return report_dirs[0]


def _find_report_dir_for_path(output_path: str | None) -> Path | None:
    if output_path:
        path = Path(output_path).expanduser().resolve()
        probe = path if path.is_dir() else path.parent
        for current in [probe, *probe.parents]:
            if current.name.startswith("report-"):
                return current
    return _find_latest_report_dir()


def _load_json_file(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(load_text_multi(path))


def _normalize_title_key(text: str) -> str:
    return TITLE_NOISE_RE.sub("", _compact(text)).casefold()


def _chinese_numeral_to_int(raw: str) -> int | None:
    text = _compact(raw)
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if text == "\u5341":
        return 10
    if "\u5341" in text:
        left, right = text.split("\u5341", 1)
        tens = CHINESE_DIGITS.get(left, 1 if not left else None)
        ones = CHINESE_DIGITS.get(right, 0 if not right else None)
        if tens is None or ones is None:
            return None
        return tens * 10 + ones
    if len(text) == 1 and text in CHINESE_DIGITS:
        return CHINESE_DIGITS[text]
    return None


def _extract_chapter_index_from_title(chapter_title: str) -> int | None:
    title = _compact(chapter_title)
    match = CHAPTER_PREFIX_RE.search(title)
    if not match:
        return None
    number = _chinese_numeral_to_int(match.group(1))
    if number is None or number <= 0:
        return None
    return number - 1


def _match_deepreport_chapter_index(report_dir: Path | None, chapter_title: str) -> int | None:
    direct = _extract_chapter_index_from_title(chapter_title)
    if direct is not None:
        return direct
    if report_dir is None:
        return None
    chapters = _load_json_file(report_dir / "chapters.json")
    if not isinstance(chapters, list):
        return None
    target_key = _normalize_title_key(chapter_title)
    if not target_key:
        return None
    for idx, item in enumerate(chapters):
        if not isinstance(item, dict):
            continue
        title = _compact(item.get("title"))
        title_key = _normalize_title_key(title)
        if not title_key:
            continue
        if title_key == target_key or target_key in title_key or title_key in target_key:
            return idx
    return None


def _build_fallback_refs(paragraph_text: str, chapter_context: str, *, limit: int = 4) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    fragments = _prioritized_fragments(paragraph_text, chapter_context, limit=limit)
    for idx, fragment in enumerate(fragments):
        refs.append({"id": idx, "content": _trim_text(fragment)})
    if not refs and _compact(paragraph_text):
        refs.append({"id": 0, "content": _trim_text(paragraph_text)})
    return refs


def _build_knowledge_refs(report_dir: Path | None, chapter_index: int | None, *, limit: int = 6) -> list[dict[str, Any]]:
    if report_dir is None or chapter_index is None:
        return []
    knowledge_path = report_dir / "knowledge" / f"ch{chapter_index}.json"
    payload = _load_json_file(knowledge_path)
    if not isinstance(payload, list):
        return []

    candidates: list[tuple[tuple[int, int], dict[str, Any]]] = []
    for idx, item in enumerate(payload):
        if not isinstance(item, dict):
            continue
        insight = _compact(item.get("insight") or item.get("summary") or item.get("content"))
        if not insight:
            continue
        source_title = _compact(item.get("sourceTitle"))
        source_url = _compact(item.get("sourceUrl"))
        content = insight
        if source_title:
            content += f"\n\nSource: {source_title}"
        if source_url:
            content += f"\nURL: {source_url}"
        candidates.append((_fragment_score(insight), {"id": idx, "content": _trim_text(content)}))

    candidates.sort(key=lambda item: item[0], reverse=True)
    return [item for _, item in candidates[:limit]]


def _merge_ref_lists(primary: list[dict[str, Any]], secondary: list[dict[str, Any]], *, limit: int = 10) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in [primary, secondary]:
        for item in source:
            if not isinstance(item, dict):
                continue
            content = _compact(item.get("content"))
            if not content:
                continue
            key = hashlib.sha1(content.encode("utf-8", "ignore")).hexdigest()
            if key in seen:
                continue
            seen.add(key)
            merged.append({"id": len(merged), "content": content})
            if len(merged) >= limit:
                return merged
    return merged


def _fallback_queries(query: str, chapter_title: str, paragraph_text: str, chapter_context: str, *, limit: int = 6) -> list[str]:
    fragments = _prioritized_fragments(paragraph_text, chapter_context, limit=3)
    queries = [
        f"{_compact(query)} {_compact(chapter_title)}",
        f"{_compact(chapter_title)} \u6570\u636e \u5bf9\u6bd4",
        f"{_compact(chapter_title)} \u5e02\u573a \u89c4\u6a21 \u5360\u6bd4",
    ]
    for fragment in fragments:
        queries.append(f"{_compact(chapter_title)} {fragment[:72]}")
    return _ordered_unique(queries, limit=limit)


def build_deepreport_review_payload(
    *,
    query: str,
    chapter_title: str,
    paragraph_text: str,
    paragraph_id: int | None,
    chapter_context: str,
    output_path: str | None,
    language: str,
    config_dict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = _config_from_dict(config_dict)
    report_dir = _find_report_dir_for_path(output_path)
    chapter_index = _match_deepreport_chapter_index(report_dir, chapter_title)
    knowledge_refs = _build_knowledge_refs(report_dir, chapter_index)
    fallback_refs = _build_fallback_refs(paragraph_text, chapter_context)
    existing_refs = _merge_ref_lists(knowledge_refs, fallback_refs, limit=8)

    chapter_token = f"ch{chapter_index + 1}" if chapter_index is not None else _safe_path_token(chapter_title)
    para_token = f"p{paragraph_id if paragraph_id is not None else 0}"
    request_id = f"deepreport-{chapter_token}-{para_token}-{_stable_hash(query, chapter_title, paragraph_text, length=8)}"

    fragments = _prioritized_fragments(paragraph_text, chapter_context, limit=3)
    if fragments:
        description = "\n".join(fragments)
    else:
        description = _trim_text(paragraph_text, 320)

    return {
        "request_id": request_id,
        "report_id": report_dir.name if report_dir else "deep-report-go",
        "section_title": _compact(chapter_title),
        "chart_title": f"{_compact(chapter_title)}\uff1a\u5173\u952e\u6570\u636e\u56fe\u793a",
        "chart_description": description,
        "write_requirement": "\n\n".join(
            [
                f"Query: {_compact(query)}",
                f"Section: {_compact(chapter_title)}",
                _trim_text(_compact(chapter_context), 2400),
            ]
        ).strip(),
        "existing_refs": existing_refs,
        "base_queries": _fallback_queries(query, chapter_title, paragraph_text, chapter_context, limit=cfg.chart_max_queries),
        "language": _compact(language) or "zh",
        "source_case": {
            "report_dir": str(report_dir) if report_dir else "",
            "chapter_index": chapter_index,
            "paragraph_id": paragraph_id,
        },
        "_deepreport_context": {
            "report_dir": str(report_dir) if report_dir else "",
            "chapter_index": chapter_index,
            "output_path": _compact(output_path),
        },
    }


def _refs_to_docs(existing_refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for idx, item in enumerate(existing_refs):
        content = _compact(item.get("content"))
        if not content:
            continue
        docs.append(
            {
                "prompt_id": idx,
                "source_kind": "existing_knowledge",
                "source_index": idx,
                "title": f"existing_knowledge_{idx}",
                "summary": _trim_text(content, 1000),
                "content": content,
                "url": "",
                "query": "",
            }
        )
    return docs


def _document_content(doc: dict[str, Any]) -> str:
    for key in ("content", "text", "summary", "abstract", "desc", "snippet", "full_text"):
        value = _compact(doc.get(key))
        if value:
            return value
    values: list[str] = []
    for key in ("segments", "snippets", "contentList"):
        raw = doc.get(key)
        if isinstance(raw, list):
            values.extend(_compact(item) for item in raw if _compact(item))
    return "\n".join(values)


def _normalize_retrieval_plan(raw_args: dict[str, Any] | None, payload: dict[str, Any], cfg: PluginConfig, *, mode: str, error: str = "", raw_output: str = "") -> dict[str, Any]:
    args = raw_args or {}
    intent = args.get("intent") if isinstance(args.get("intent"), dict) else {}
    raw_queries = args.get("queries") if isinstance(args.get("queries"), list) else []
    queries = [str(item).strip() for item in raw_queries if str(item).strip()]
    if not queries:
        queries = payload.get("base_queries") or []
    queries = _ordered_unique(queries, limit=cfg.chart_max_queries)
    return {
        "intent": intent,
        "queries": queries,
        "notes": _compact(args.get("notes")),
        "_planning_mode": mode,
        "_planning_error": error,
        "_planning_raw_output": raw_output,
    }


def plan_chart_retrieval(payload: dict[str, Any], cfg: PluginConfig) -> dict[str, Any]:
    llm = SecureLLMClient(cfg)
    ok, message = llm.available()
    if not ok:
        return _normalize_retrieval_plan(None, payload, cfg, mode="fallback", error=message)

    refs_block = []
    for item in payload.get("existing_refs") or []:
        if isinstance(item, dict):
            refs_block.append(f"[{item.get('id', 0)}] {_trim_text(_compact(item.get('content')), 420)}")

    system_prompt = (
        "You are a chart retrieval planner. Return focused supplementary search queries for a single charting task. "
        "Keep the plan narrow and retrieval-oriented."
    )
    user_prompt = "\n\n".join(
        [
            f"Chart title:\n{_compact(payload.get('chart_title'))}",
            f"Chart description:\n{_compact(payload.get('chart_description'))}",
            f"Write requirement:\n{_compact(payload.get('write_requirement'))}",
            "Existing refs:\n" + ("\n".join(refs_block) if refs_block else "None"),
            "Seed queries:\n" + "\n".join(payload.get("base_queries") or []),
        ]
    )
    response = llm.call_with_tools(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        tools=plan_chart_retrieval_tools(),
        tool_name="plan_chart_retrieval",
        temperature=0.0,
    )
    if not response.ok or not isinstance(response.arguments, dict):
        return _normalize_retrieval_plan(
            None,
            payload,
            cfg,
            mode="fallback",
            error=_compact(response.error),
            raw_output=_compact(response.content),
        )
    return _normalize_retrieval_plan(
        response.arguments,
        payload,
        cfg,
        mode="llm",
        error=_compact(response.error),
        raw_output=_compact(response.content),
    )


def search_documents(queries: list[str], request_id: str, cfg: PluginConfig) -> list[dict[str, Any]]:
    if not queries:
        return []
    client = AggSearchClient(cfg)
    return client.search_many(queries, request_id=request_id)


def prepare_live_docs_for_generation(search_results: list[dict[str, Any]], *, start_prompt_id: int, quota: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    prompt_id = start_prompt_id
    for result in search_results:
        query = _compact(result.get("query"))
        for doc in result.get("documents") or []:
            if not isinstance(doc, dict):
                continue
            content = _compact(_document_content(doc))
            if not content:
                continue
            title = _compact(doc.get("title") or doc.get("name")) or "live_search"
            url = _compact(doc.get("url") or doc.get("link"))
            identity = hashlib.sha1(f"{title}\n{url}\n{content}".encode("utf-8", "ignore")).hexdigest()
            if identity in seen:
                continue
            seen.add(identity)
            selected.append(
                {
                    "prompt_id": prompt_id,
                    "source_kind": "live_search",
                    "source_index": prompt_id,
                    "title": title,
                    "summary": _trim_text(content, 1000),
                    "content": _trim_text(content, 3000),
                    "url": url,
                    "query": query,
                }
            )
            prompt_id += 1
            if len(selected) >= quota:
                return selected
    return selected


def _is_empty_chart(spec: dict[str, Any]) -> bool:
    return _compact(spec.get("chart_tag")) == "empty"


def _absolute_render_path(render_result: dict[str, Any]) -> Path | None:
    relative_path = _compact(render_result.get("png_path") or render_result.get("relative_path"))
    if not relative_path:
        return None
    return (PACKAGE_ROOT / relative_path).resolve()


def _default_output_path(report_dir: Path | None, request_id: str, rendered_path: Path | None) -> Path | None:
    if report_dir is not None:
        return (report_dir / "charts" / f"{request_id}.png").resolve()
    return rendered_path.resolve() if rendered_path is not None else None


def _markdown_target(report_dir: Path | None, absolute_path: Path | None) -> str:
    if absolute_path is None:
        return ""
    if report_dir is None:
        return absolute_path.resolve().as_uri()
    relative = os.path.relpath(absolute_path, report_dir)
    relative_posix = Path(relative).as_posix()
    return relative_posix if relative_posix.startswith(".") else f"./{relative_posix}"


def generate_chart_for_deepreport(
    *,
    query: str,
    chapter_title: str,
    paragraph_text: str,
    paragraph_id: int | None = None,
    chapter_context: str = "",
    output_path: str | None = None,
    language: str = "zh",
    config_dict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = _config_from_dict(config_dict)
    payload = build_deepreport_review_payload(
        query=query,
        chapter_title=chapter_title,
        paragraph_text=paragraph_text,
        paragraph_id=paragraph_id,
        chapter_context=chapter_context,
        output_path=output_path,
        language=language,
        config_dict=config_dict,
    )
    request_id = _compact(payload.get("request_id")) or f"deepreport-{_stable_hash(query, chapter_title, paragraph_text)}"
    chart_title = _compact(payload.get("chart_title")) or _compact(chapter_title) or "Chart"
    report_dir_raw = _compact((payload.get("_deepreport_context") or {}).get("report_dir"))
    report_dir = Path(report_dir_raw) if report_dir_raw else _find_report_dir_for_path(output_path)

    retrieval_plan = plan_chart_retrieval(payload, cfg)
    existing_docs = _refs_to_docs(payload.get("existing_refs") or [])
    docs_for_generation = list(existing_docs)
    first_spec = decide_chart_spec(payload, [], config=cfg, docs=docs_for_generation, retrieval_plan=retrieval_plan)
    final_spec = first_spec
    search_results: list[dict[str, Any]] = []
    live_docs: list[dict[str, Any]] = []

    if _is_empty_chart(first_spec) and retrieval_plan.get("queries"):
        search_results = search_documents(retrieval_plan.get("queries") or [], request_id, cfg)
        live_docs = prepare_live_docs_for_generation(
            search_results,
            start_prompt_id=len(existing_docs),
            quota=cfg.chart_live_docs_quota,
        )
        if live_docs:
            docs_for_generation = existing_docs + live_docs
            final_spec = decide_chart_spec(payload, [], config=cfg, docs=docs_for_generation, retrieval_plan=retrieval_plan)

    if _is_empty_chart(final_spec):
        bundle = build_no_chart_result(final_spec, request_id, chart_title)
        return {
            "success": True,
            "request_id": request_id,
            "chart_tag": "empty",
            "should_insert": False,
            "empty_reason": _compact(final_spec.get("explain") or final_spec.get("_decision_error")),
            "relative_path": "",
            "absolute_path": "",
            "markdown": "",
            "markdown_for_deepreport": "",
            "retrieval_plan": retrieval_plan,
            "queries": retrieval_plan.get("queries") or [],
            "docs_for_generation": docs_for_generation,
            "chart_decision_debug": {
                "decision_mode": _compact(final_spec.get("_decision_mode")),
                "decision_error": _compact(final_spec.get("_decision_error")),
                "decision_raw_output": _compact(final_spec.get("_decision_raw_output")),
            },
            "debug_summary": {
                "existing_refs_count": len(payload.get("existing_refs") or []),
                "query_count": len(retrieval_plan.get("queries") or []),
                "live_hits_count": sum(len(item.get("documents") or []) for item in search_results),
                "selected_live_docs_count": len(live_docs),
                "docs_for_generation_count": len(docs_for_generation),
                "chart_tag": "empty",
                "decision_mode": _compact(final_spec.get("_decision_mode")),
            },
            **bundle,
        }

    render_result = render_chart_artifacts(final_spec, request_id, chart_title)
    rendered_path = _absolute_render_path(render_result)
    target_path = Path(output_path).resolve() if _compact(output_path) else _default_output_path(report_dir, request_id, rendered_path)
    if target_path is not None and rendered_path is not None and rendered_path.exists() and target_path.resolve() != rendered_path.resolve():
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rendered_path, target_path)
    elif target_path is None:
        target_path = rendered_path

    markdown_target = _markdown_target(report_dir, target_path)
    markdown = f"![{chart_title}]({markdown_target})" if markdown_target else ""

    return {
        "success": True,
        "request_id": request_id,
        "chart_tag": _compact(final_spec.get("chart_tag")),
        "should_insert": True,
        "empty_reason": "",
        "relative_path": markdown_target,
        "absolute_path": str(target_path) if target_path else "",
        "markdown": markdown,
        "markdown_for_deepreport": markdown,
        "retrieval_plan": retrieval_plan,
        "queries": retrieval_plan.get("queries") or [],
        "docs_for_generation": docs_for_generation,
        "chart_decision_debug": {
            "decision_mode": _compact(final_spec.get("_decision_mode")),
            "decision_error": _compact(final_spec.get("_decision_error")),
            "decision_raw_output": _compact(final_spec.get("_decision_raw_output")),
        },
        "debug_summary": {
            "existing_refs_count": len(payload.get("existing_refs") or []),
            "query_count": len(retrieval_plan.get("queries") or []),
            "live_hits_count": sum(len(item.get("documents") or []) for item in search_results),
            "selected_live_docs_count": len(live_docs),
            "docs_for_generation_count": len(docs_for_generation),
            "chart_tag": _compact(final_spec.get("chart_tag")),
            "decision_mode": _compact(final_spec.get("_decision_mode")),
        },
        **render_result,
    }


__all__ = ["build_deepreport_review_payload", "generate_chart_for_deepreport"]
