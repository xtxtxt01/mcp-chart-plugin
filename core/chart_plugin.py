from __future__ import annotations

import json
from typing import Any

from ..clients.agg_search import AggSearchClient
from ..clients.llm import SecureLLMClient, ToolCallResult
from ..config import (
    DemoConfig,
    QUERY_PLANNING_PROMPT_PATH,
)
from ..prompt_utils import load_text_multi
from ..core.baseline_decider import decide_chart_spec
from ..core.renderer import render_chart_artifacts
from ..schemas.function_schemas import plan_chart_retrieval_tools


def _compact(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> float | None:
    if value in [None, ""]:
        return None
    try:
        return float(str(value).replace(",", ""))
    except Exception:
        return None


def _safe_int(value: Any) -> int | None:
    number = _safe_float(value)
    return int(number) if number is not None else None


def _ordered_unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = _compact(value)
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _config_from_dict(config_dict: dict[str, Any] | None) -> DemoConfig:
    cfg = DemoConfig()
    cfg.apply_overrides(config_dict)
    return cfg


def _fallback_queries(task: dict[str, Any], config: DemoConfig) -> list[str]:
    queries: list[str] = []
    queries.extend([str(item) for item in (task.get("base_queries") or []) if _compact(item)])
    for field in ["chart_title", "chart_description"]:
        value = _compact(task.get(field))
        if value:
            queries.append(value)
    return _ordered_unique(queries)[: config.chart_max_queries]


def _normalize_knowledge(item: dict[str, Any]) -> dict[str, Any]:
    insight = _compact(item.get("insight"))
    if not insight:
        return {}
    snippets = item.get("snippets")
    normalized_snippets: list[str] = []
    if isinstance(snippets, list):
        for snippet in snippets:
            value = _compact(snippet)
            if value:
                normalized_snippets.append(value)
    return {
        "insight": insight,
        "snippets": normalized_snippets,
    }


def _knowledge_signature(item: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    return (
        _compact(item.get("insight")),
        tuple(str(snippet) for snippet in item.get("snippets") or []),
    )


def merge_and_dedupe_knowledges(knowledges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for raw_item in knowledges:
        item = _normalize_knowledge(raw_item)
        if not item:
            continue
        signature = _knowledge_signature(item)
        if signature in seen:
            continue
        seen.add(signature)
        result.append(item)
    return result


def _existing_refs_to_knowledges(task: dict[str, Any]) -> list[dict[str, Any]]:
    knowledges: list[dict[str, Any]] = []
    for idx, ref in enumerate(task.get("existing_refs") or []):
        content = _compact(ref.get("content"))
        if not content:
            continue
        source_index = _safe_int(ref.get("id"))
        knowledges.append(
            {
                "insight": content,
                "snippets": [str(source_index if source_index is not None else idx)],
            }
        )
    return merge_and_dedupe_knowledges(knowledges)


def _knowledge_doc(item: dict[str, Any], prompt_id: int, *, source_kind: str) -> dict[str, Any]:
    insight = _compact(item.get("insight"))
    return {
        "prompt_id": prompt_id,
        "source_kind": source_kind,
        "source_index": prompt_id,
        "title": f"{source_kind}_{prompt_id}",
        "summary": insight[:240],
        "content": insight,
        "url": "",
        "query": "",
        "query_index": -1,
    }


def _knowledge_docs(
    existing_knowledges: list[dict[str, Any]],
    new_knowledges: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    prompt_id = 0
    for item in existing_knowledges:
        docs.append(_knowledge_doc(item, prompt_id, source_kind="existing_knowledge"))
        prompt_id += 1
    for item in new_knowledges or []:
        docs.append(_knowledge_doc(item, prompt_id, source_kind="live_knowledge"))
        prompt_id += 1
    return docs


def _compose_generation_docs(
    existing_knowledges: list[dict[str, Any]],
    live_docs: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    docs = _knowledge_docs(existing_knowledges)
    prompt_id = len(docs)
    for raw_doc in live_docs or []:
        doc = dict(raw_doc)
        doc["prompt_id"] = prompt_id
        doc["source_kind"] = "live_search"
        doc["source_index"] = _safe_int(doc.get("source_index")) if _safe_int(doc.get("source_index")) is not None else prompt_id
        doc["title"] = _compact(doc.get("title")) or f"live_search_doc_{prompt_id}"
        doc["summary"] = _compact(doc.get("summary") or doc.get("content") or doc.get("title"))[:400]
        doc["content"] = _compact(doc.get("content") or doc.get("summary") or doc.get("title"))
        doc["url"] = _compact(doc.get("url"))
        doc["query"] = _compact(doc.get("query"))
        doc["query_index"] = _safe_int(doc.get("query_index")) if _safe_int(doc.get("query_index")) is not None else -1
        docs.append(doc)
        prompt_id += 1
    return docs


def _knowledge_preview(knowledges: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    preview: list[dict[str, Any]] = []
    for idx, item in enumerate(knowledges[:limit]):
        preview.append(
            {
                "index": idx,
                "insight": _compact(item.get("insight"))[:240],
                "snippets": [str(snippet) for snippet in (item.get("snippets") or [])],
            }
        )
    return preview


def _build_gap_report(task: dict[str, Any], spec: dict[str, Any], knowledges: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "chart_title": _compact(task.get("chart_title")),
        "chart_description": _compact(task.get("chart_description")),
        "first_attempt_chart_tag": _compact(spec.get("chart_tag") or "empty"),
        "failure_reason": _compact(spec.get("explain") or spec.get("_decision_error")),
        "decision_mode": _compact(spec.get("_decision_mode") or "unknown"),
        "existing_knowledge_count": len(knowledges),
        "existing_knowledge_preview": _knowledge_preview(knowledges),
        "first_attempt_raw_output": _compact(spec.get("_decision_raw_output") or spec.get("_raw_output"))[:1200],
    }


def _build_query_planning_prompt(task: dict[str, Any], gap_report: dict[str, Any] | None = None) -> str:
    ref_preview = []
    for idx, ref in enumerate(task.get("existing_refs") or []):
        ref_preview.append(
            {
                "id": _safe_int(ref.get("id")) if _safe_int(ref.get("id")) is not None else idx,
                "content_preview": _compact(ref.get("content"))[:240],
            }
        )

    gap_section = ""
    if gap_report:
        gap_section = (
            "\n## 第一次成图失败情况\n"
            f"{json.dumps(gap_report, ensure_ascii=False, indent=2)}\n\n"
            "## 额外要求\n"
            "- 你需要结合第一次失败原因，判断还缺哪些关键数据字段。\n"
            "- 本轮 queries 应优先补齐缺口，不要重复搜索已经充分存在的信息。\n"
            "- notes 里请明确写出：第一次为什么没能成图、本轮重点要补什么。\n"
        )

    return (
        "## 图表任务\n"
        f"- 图表标题：{_compact(task.get('chart_title'))}\n"
        f"- 图表描述：{_compact(task.get('chart_description'))}\n"
        f"- 写作要求：{_compact(task.get('write_requirement'))}\n\n"
        "## 已有基础 queries\n"
        f"{json.dumps(task.get('base_queries') or [], ensure_ascii=False, indent=2)}\n\n"
        "## 已有上游 insights 预览\n"
        f"{json.dumps(ref_preview, ensure_ascii=False, indent=2)}\n"
        f"{gap_section}\n"
        "## 输出要求\n"
        "- comparison_mode 仅从 compare/trend/share/flow/hierarchy/funnel/multidim/other 中选择。\n"
        "- queries 返回 3 到 8 条，且语言与任务一致。\n"
        "- intent 中的 entities、metrics、dimensions 只写你能从任务中明确识别到的内容。\n"
    )


def _normalize_retrieval_plan(
    task: dict[str, Any],
    config: DemoConfig,
    tool_result: ToolCallResult | None,
) -> dict[str, Any]:
    raw = tool_result.arguments if tool_result and isinstance(tool_result.arguments, dict) else {}
    intent_raw = raw.get("intent") if isinstance(raw.get("intent"), dict) else {}
    queries_raw = raw.get("queries") if isinstance(raw.get("queries"), list) else []

    plan = {
        "intent": {
            "comparison_mode": _compact(intent_raw.get("comparison_mode")) or "other",
            "entities": [str(item) for item in intent_raw.get("entities", []) if _compact(item)],
            "metrics": [str(item) for item in intent_raw.get("metrics", []) if _compact(item)],
            "dimensions": [str(item) for item in intent_raw.get("dimensions", []) if _compact(item)],
            "chart_type_hints": [str(item) for item in intent_raw.get("chart_type_hints", []) if _compact(item)],
            "must_have_fields": [str(item) for item in intent_raw.get("must_have_fields", []) if _compact(item)],
            "time_hints": [str(item) for item in intent_raw.get("time_hints", []) if _compact(item)],
            "region_hints": [str(item) for item in intent_raw.get("region_hints", []) if _compact(item)],
            "query_language": _compact(intent_raw.get("query_language") or task.get("language") or "zh"),
        },
        "queries": [str(item) for item in queries_raw if _compact(item)],
        "notes": _compact(raw.get("notes")),
    }

    if not plan["queries"]:
        plan["queries"] = _fallback_queries(task, config)
        plan["_planning_mode"] = "fallback_queries"
    else:
        plan["queries"] = _ordered_unique(plan["queries"])[: config.chart_max_queries]
        plan["_planning_mode"] = "llm"

    plan["_planning_error"] = _compact(tool_result.error if tool_result else "")
    plan["_planning_raw_output"] = _compact(tool_result.content if tool_result else "")
    return plan


def plan_chart_retrieval(
    task: dict[str, Any],
    config: DemoConfig,
    gap_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    llm = SecureLLMClient(config)
    result: ToolCallResult | None = None
    if llm.available()[0]:
        result = llm.call_with_tools(
            system_prompt=load_text_multi(QUERY_PLANNING_PROMPT_PATH),
            user_prompt=_build_query_planning_prompt(task, gap_report=gap_report),
            tools=plan_chart_retrieval_tools(),
            tool_name="plan_chart_retrieval",
            temperature=0.0,
        )
    return _normalize_retrieval_plan(task, config, result)


def expand_queries(task: dict[str, Any], retrieval_plan: dict[str, Any], config: DemoConfig) -> list[str]:
    queries = [str(item) for item in (retrieval_plan.get("queries") or []) if _compact(item)]
    if not queries:
        queries = _fallback_queries(task, config)
    return _ordered_unique(queries)[: config.chart_max_queries]


def _live_doc(doc: dict[str, Any], *, query: str, query_index: int) -> dict[str, Any]:
    title = _compact(doc.get("name") or doc.get("title"))
    summary = _compact(doc.get("summary") or doc.get("snippet") or doc.get("abstract"))
    content = _compact(doc.get("content") or doc.get("text") or summary or title)
    url = _compact(doc.get("url") or doc.get("link"))
    return {
        "source_kind": "live_search",
        "source_index": None,
        "title": title or f"live_search_doc_{query_index}",
        "summary": summary[:400],
        "content": content,
        "url": url,
        "query": _compact(query),
        "query_index": query_index,
    }


def search_documents(task: dict[str, Any], queries: list[str], config: DemoConfig) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    documents: list[dict[str, Any]] = []
    client = AggSearchClient(config)
    results = client.search_many(queries, request_id=_compact(task.get("request_id")))

    live_overview: list[dict[str, Any]] = []
    for result in results:
        raw_docs = result.get("documents") or []
        for doc in raw_docs:
            documents.append(
                _live_doc(
                    doc,
                    query=result.get("query", ""),
                    query_index=int(result.get("query_index") or 0),
                )
            )
        live_overview.append(
            {
                "query_index": result.get("query_index"),
                "query": result.get("query"),
                "success": bool(result.get("success")),
                "status_code": result.get("status_code"),
                "document_count": len(raw_docs),
                "top_titles": [_compact(doc.get("name") or doc.get("title")) for doc in raw_docs[:3]],
                "error": _compact(result.get("error")),
            }
        )
    return documents, results, live_overview


def _doc_identity(doc: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _compact(doc.get("title")).casefold(),
        _compact(doc.get("url")).casefold(),
        _compact(doc.get("content"))[:160].casefold(),
    )


def prepare_live_docs_for_generation(
    documents: list[dict[str, Any]],
    config: DemoConfig,
) -> list[dict[str, Any]]:
    if not documents:
        return []

    live_doc_limit = max(0, min(config.chart_live_docs_quota, 3))
    if live_doc_limit == 0:
        return []

    selected: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for doc in documents:
        identity = _doc_identity(doc)
        if identity in seen:
            continue
        seen.add(identity)
        selected.append(dict(doc))
        if len(selected) >= live_doc_limit:
            break
    return selected


def _brief_reference(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "prompt_id": _safe_int(doc.get("prompt_id")),
        "source_kind": _compact(doc.get("source_kind")),
        "source_index": _safe_int(doc.get("source_index")),
        "title": _compact(doc.get("title")),
        "summary": _compact(doc.get("summary"))[:240],
        "url": _compact(doc.get("url")),
        "query": _compact(doc.get("query")),
    }


def _skipped_retrieval_plan(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "intent": {
            "comparison_mode": "unknown",
            "entities": [],
            "metrics": [],
            "dimensions": [],
            "chart_type_hints": [],
            "must_have_fields": [],
            "time_hints": [],
            "region_hints": [],
            "query_language": _compact(task.get("language") or "zh"),
        },
        "queries": [],
        "notes": "First pass used existing insights directly, so agg retrieval planning was skipped.",
        "_planning_mode": "skipped_existing_insights",
        "_planning_error": "",
        "_planning_raw_output": "",
    }


def _needs_agg_retry(spec: dict[str, Any]) -> bool:
    chart_tag = _compact(spec.get("chart_tag")).casefold()
    if chart_tag in {"", "empty", "null"}:
        return True
    chart_data = spec.get("chart_data")
    return chart_data in [None, {}]


def _attempt_snapshot(
    *,
    stage: str,
    retrieval_plan: dict[str, Any],
    queries: list[str],
    selected_live_docs: list[dict[str, Any]],
    docs_for_generation: list[dict[str, Any]],
    knowledges: list[dict[str, Any]],
    spec: dict[str, Any],
    used_agg_search: bool,
    live_hits_count: int,
) -> dict[str, Any]:
    return {
        "stage": stage,
        "used_agg_search": used_agg_search,
        "planning_mode": _compact(retrieval_plan.get("_planning_mode")),
        "query_count": len(queries),
        "live_hits_count": live_hits_count,
        "selected_live_docs_count": len(selected_live_docs),
        "docs_for_generation_count": len(docs_for_generation),
        "knowledge_count": len(knowledges),
        "chart_tag": _compact(spec.get("chart_tag") or "empty"),
        "decision_mode": _compact(spec.get("_decision_mode") or "unknown"),
    }


def generate_chart_markdown(review_payload: dict[str, Any], config_dict: dict[str, Any] | None = None) -> dict[str, Any]:
    config = _config_from_dict(config_dict)
    task = dict(review_payload)

    generation_attempts: list[dict[str, Any]] = []
    gap_report: dict[str, Any] | None = None

    existing_knowledges = _existing_refs_to_knowledges(task)
    initial_retrieval_plan = _skipped_retrieval_plan(task)
    initial_queries: list[str] = []
    initial_search_results: list[dict[str, Any]] = []
    initial_live_search_overview: list[dict[str, Any]] = []
    initial_selected_live_docs: list[dict[str, Any]] = []
    initial_docs_for_generation = _compose_generation_docs(existing_knowledges)
    initial_spec = decide_chart_spec(
        task,
        existing_knowledges,
        config=config,
        docs=initial_docs_for_generation,
        retrieval_plan=initial_retrieval_plan,
    )
    generation_attempts.append(
        _attempt_snapshot(
            stage="existing_insights_only",
            retrieval_plan=initial_retrieval_plan,
            queries=initial_queries,
            selected_live_docs=initial_selected_live_docs,
            docs_for_generation=initial_docs_for_generation,
            knowledges=existing_knowledges,
            spec=initial_spec,
            used_agg_search=False,
            live_hits_count=0,
        )
    )

    if _needs_agg_retry(initial_spec):
        gap_report = _build_gap_report(task, initial_spec, existing_knowledges)
        retrieval_plan = plan_chart_retrieval(task, config, gap_report=gap_report)
        queries = expand_queries(task, retrieval_plan, config)
        live_documents, search_results, live_search_overview = search_documents(task, queries, config)
        selected_live_docs = prepare_live_docs_for_generation(live_documents, config)
        knowledges = existing_knowledges
        docs_for_generation = _compose_generation_docs(existing_knowledges, selected_live_docs)
        spec = decide_chart_spec(
            task,
            knowledges,
            config=config,
            docs=docs_for_generation,
            retrieval_plan=retrieval_plan,
        )
        live_hits_count = sum(len(result.get("documents") or []) for result in search_results)
        generation_attempts.append(
            _attempt_snapshot(
                stage="existing_insights_plus_top_live_docs",
                retrieval_plan=retrieval_plan,
                queries=queries,
                selected_live_docs=selected_live_docs,
                docs_for_generation=docs_for_generation,
                knowledges=knowledges,
                spec=spec,
                used_agg_search=True,
                live_hits_count=live_hits_count,
            )
        )
    else:
        retrieval_plan = initial_retrieval_plan
        queries = initial_queries
        search_results = initial_search_results
        live_search_overview = initial_live_search_overview
        selected_live_docs = initial_selected_live_docs
        docs_for_generation = initial_docs_for_generation
        knowledges = existing_knowledges
        spec = initial_spec
        live_hits_count = 0

    title = _compact(task.get("chart_title") or task.get("chart_description") or "Chart")
    render_result = render_chart_artifacts(spec, _compact(task.get("request_id")), title)

    decision_mode = _compact(spec.get("_decision_mode") or "unknown")
    decision_error = _compact(spec.get("_decision_error"))
    decision_raw_output = _compact(spec.get("_decision_raw_output") or spec.get("_raw_output"))
    selected_live_doc_refs = [_brief_reference(doc) for doc in selected_live_docs]
    generation_refs = [_brief_reference(doc) for doc in docs_for_generation]

    return {
        "success": True,
        "markdown": render_result["markdown"],
        "relative_path": render_result["relative_path"],
        "chart_tag": _compact(spec.get("chart_tag") or "empty"),
        "retrieval_plan": retrieval_plan,
        "queries": queries,
        "search_results": search_results,
        "live_search_overview": live_search_overview,
        "selected_live_docs": selected_live_doc_refs,
        "docs_for_generation": generation_refs,
        "knowledges": knowledges,
        "facts": knowledges,
        "references": generation_refs,
        "chart_decision_debug": {
            "decision_mode": decision_mode,
            "decision_error": decision_error,
            "decision_raw_output": decision_raw_output,
        },
        "generation_attempts": generation_attempts,
        "retry_gap_report": gap_report,
        "debug_summary": {
            "query_count": len(queries),
            "existing_refs_count": len(task.get("existing_refs") or []),
            "live_hits_count": live_hits_count,
            "selected_live_docs_count": len(selected_live_docs),
            "docs_for_generation_count": len(docs_for_generation),
            "knowledge_count": len(knowledges),
            "chart_tag": _compact(spec.get("chart_tag") or "empty"),
            "decision_mode": decision_mode,
            "used_agg_search": len(generation_attempts) > 1,
            "attempt_count": len(generation_attempts),
            "final_stage": _compact(generation_attempts[-1].get("stage")) if generation_attempts else "",
        },
        **render_result,
    }


__all__ = [
    "plan_chart_retrieval",
    "expand_queries",
    "search_documents",
    "prepare_live_docs_for_generation",
    "merge_and_dedupe_knowledges",
    "generate_chart_markdown",
]
