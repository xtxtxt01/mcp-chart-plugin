from __future__ import annotations

import sys
from typing import Any

from ..config import LOG_HELPER_ROOT, SEARCH_AUDIT_ROOT


for path in [LOG_HELPER_ROOT, SEARCH_AUDIT_ROOT]:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from chart_input_diagnosis_helper import CSV_FILES, load_log, parse_chart_question, parse_chart_answer  # noqa: E402
from chart_search_recall_helper import _extract_case_queries  # noqa: E402


def resolve_file_name(file_name: str | None = None, file_index: int | None = None) -> str:
    if file_name:
        return file_name
    if file_index is None:
        raise ValueError("Either file_name or file_index must be provided.")
    if file_index < 1 or file_index > len(CSV_FILES):
        raise IndexError(f"file_index out of range: {file_index}")
    return CSV_FILES[file_index - 1]


def load_chart_case(file_name: str | None = None, row_id: int = 150, file_index: int | None = None) -> dict[str, Any]:
    resolved = resolve_file_name(file_name=file_name, file_index=file_index)
    df = load_log(resolved)
    matched = df.loc[df["row_id"].eq(row_id)]
    if matched.empty:
        raise ValueError(f"Row {row_id} not found in {resolved}")

    row = matched.iloc[0]
    chart_question = parse_chart_question(row["question"])
    chart_answer = parse_chart_answer(row["answer"])
    trace = _extract_case_queries(resolved, row_id)

    return {
        "file_name": resolved,
        "row_id": int(row_id),
        "raw_row": row.to_dict(),
        "chart_description": chart_question.get("description", ""),
        "existing_refs": chart_question.get("references", []),
        "chart_answer": chart_answer,
        "raw_question": str(row["question"] or ""),
        "raw_answer": str(row["answer"] or ""),
        "trace": trace,
        "base_queries": trace.get("queries", []),
        "write_requirement": trace.get("write_requirement", ""),
        "trace_method": trace.get("trace_method", ""),
        "research_row_id": trace.get("research_row_id"),
        "gap_search_row_ids": trace.get("gap_search_row_ids", []),
    }
