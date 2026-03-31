from __future__ import annotations

import json
import sys
from typing import Any

from .core.chart_plugin import generate_chart_for_deepreport


def _sanitize_text(value: str) -> str:
    return value.encode("utf-8", "replace").decode("utf-8", "replace")


def _sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, dict):
        return {str(_sanitize(k)): _sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize(item) for item in value)
    return value


def _compact(value: Any) -> str:
    return _sanitize_text(str(value or "")).strip()


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _response(result: dict[str, Any] | None = None, *, request_id: Any, error: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result or {}
    return payload


def _tool_schema() -> dict[str, Any]:
    return {
        "name": "chart_generate",
        "description": (
            "Generate a chart markdown image for the current report paragraph. "
            "Use this when the paragraph contains clear numeric comparison, trend, hierarchy, funnel, "
            "share, or multidimensional evidence that benefits from visualization."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The user's original deep-report query."},
                "chapter_title": {"type": "string", "description": "Current chapter title."},
                "paragraph_text": {"type": "string", "description": "The paragraph content that may need a chart."},
                "paragraph_id": {"type": "integer", "description": "Optional paragraph index used for stable artifact naming."},
                "chapter_context": {"type": "string", "description": "Optional surrounding chapter context to help chart generation."},
                "output_path": {
                    "type": "string",
                    "description": "Optional absolute output image path. When omitted, chart_plugin_mcp stores artifacts under its own artifacts directory.",
                },
                "language": {"type": "string", "description": "Language for chart generation, usually zh or en.", "default": "zh"},
                "config": {"type": "object", "description": "Optional chart-plugin config overrides.", "additionalProperties": True},
            },
            "required": ["query", "chapter_title", "paragraph_text"],
        },
    }


def _handle_initialize(request_id: Any) -> dict[str, Any]:
    return _response(
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "chart-plugin-mcp", "version": "1.0.0"},
        },
        request_id=request_id,
    )


def _handle_list_tools(request_id: Any) -> dict[str, Any]:
    return _response({"tools": [_tool_schema()]}, request_id=request_id)


def _handle_tool_call(request_id: Any, params: dict[str, Any]) -> dict[str, Any]:
    tool_name = _compact(params.get("name"))
    if tool_name != "chart_generate":
        return _response(request_id=request_id, error={"code": -32601, "message": f"Unknown tool: {tool_name}"})

    args = _sanitize(params.get("arguments"))
    if not isinstance(args, dict):
        return _response(request_id=request_id, error={"code": -32602, "message": "Invalid arguments"})

    try:
        result = generate_chart_for_deepreport(
            query=_compact(args.get("query")),
            chapter_title=_compact(args.get("chapter_title")),
            paragraph_text=_compact(args.get("paragraph_text")),
            paragraph_id=_to_int(args.get("paragraph_id")),
            chapter_context=_compact(args.get("chapter_context")),
            output_path=_compact(args.get("output_path")) or None,
            language=_compact(args.get("language")) or "zh",
            config_dict=args.get("config") if isinstance(args.get("config"), dict) else None,
        )
    except Exception as exc:
        return _response(request_id=request_id, error={"code": -32603, "message": _compact(exc)})

    markdown = _compact(result.get("markdown_for_deepreport"))
    payload: dict[str, Any] = {
        "content": ([{"type": "text", "text": markdown}] if markdown else []),
        "meta": {
            "success": bool(result.get("success")),
            "chart_tag": _compact(result.get("chart_tag")),
            "should_insert": bool(result.get("should_insert")),
            "empty_reason": _compact(result.get("empty_reason")),
            "relative_path": _compact(result.get("relative_path")),
            "absolute_path": _compact(result.get("absolute_path")),
        },
    }
    return _response(payload, request_id=request_id)


def _write(payload: dict[str, Any]) -> None:
    serialized = json.dumps(_sanitize(payload), ensure_ascii=False)
    sys.stdout.buffer.write(serialized.encode("utf-8", "replace") + b"\n")
    sys.stdout.buffer.flush()


def main() -> None:
    while True:
        raw_line = sys.stdin.buffer.readline()
        if not raw_line:
            break
        line = raw_line.decode("utf-8", "replace").strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except Exception:
            continue

        method = _compact(request.get("method"))
        request_id = request.get("id")
        params = request.get("params") if isinstance(request.get("params"), dict) else {}

        if method == "notifications/initialized":
            continue
        if method == "initialize":
            _write(_handle_initialize(request_id))
            continue
        if method == "tools/list":
            _write(_handle_list_tools(request_id))
            continue
        if method == "tools/call":
            _write(_handle_tool_call(request_id, params))
            continue

        if request_id is None:
            continue
        _write(_response(request_id=request_id, error={"code": -32601, "message": f"Method not found: {method}"}))


if __name__ == "__main__":
    main()
