from __future__ import annotations

from typing import Any

from .csv_cases import load_chart_case


def _guess_chart_title(description: str, file_name: str, row_id: int) -> str:
    description = (description or "").strip()
    if not description:
        return f"{file_name} row {row_id} chart"
    for splitter in ["；", ";", "。"]:
        if splitter in description:
            title = description.split(splitter, 1)[0].strip()
            if title:
                return title
    return description[:80].strip() or f"{file_name} row {row_id} chart"


def build_review_payload(file_name: str, row_id: int) -> dict[str, Any]:
    case = load_chart_case(file_name=file_name, row_id=row_id)
    request_id = f"demo-{file_name.replace(' ', '_').replace('.csv', '')}-row{row_id}"
    return {
        "request_id": request_id,
        "report_id": "demo-report-001",
        "section_title": "图表增强演示",
        "chart_title": _guess_chart_title(case["chart_description"], file_name, row_id),
        "chart_description": case["chart_description"],
        "write_requirement": case["write_requirement"],
        "existing_refs": case["existing_refs"],
        "base_queries": case["base_queries"],
        "language": "zh",
        "source_case": {
            "file_name": case["file_name"],
            "row_id": case["row_id"],
            "trace_method": case["trace_method"],
            "research_row_id": case["research_row_id"],
            "gap_search_row_ids": case["gap_search_row_ids"],
        },
    }
