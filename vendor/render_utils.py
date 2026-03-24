from __future__ import annotations

import json
import importlib.util
import re
import sys
import uuid
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = REPO_ROOT / "DR" if (REPO_ROOT / "DR" / "src").exists() else REPO_ROOT
SRC_ROOT = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

try:
    from src.tools.md2html import markdown2html
except ModuleNotFoundError:
    md2html_path = SRC_ROOT / "tools" / "md2html.py"
    spec = importlib.util.spec_from_file_location("chart_module_lab_md2html", md2html_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load md2html from {md2html_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    markdown2html = module.markdown2html


SUPPORTED_TAGS = (
    "empty",
    "radar",
    "bar-line",
    "sankey",
    "pie",
    "treemap",
    "sunburst",
    "funnel",
)

PALETTE = [
    "#113f67",
    "#4d8fac",
    "#f4a259",
    "#c8553d",
    "#6b8f71",
    "#7a6c5d",
]


INSIDE_LABEL_STYLE = {
    "fontSize": 14,
    "fontWeight": "bold",
    "textBorderWidth": 2,
    "textShadowBlur": 2,
}


def _hex_to_rgb(color: str) -> tuple[int, int, int] | None:
    text = str(color or "").strip()
    if not text.startswith("#"):
        return None
    value = text[1:]
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6:
        return None
    try:
        return tuple(int(value[i : i + 2], 16) for i in range(0, 6, 2))
    except Exception:
        return None


def _is_dark_color(color: str) -> bool:
    rgb = _hex_to_rgb(color)
    if rgb is None:
        return True
    r, g, b = rgb
    brightness = (r * 299 + g * 587 + b * 114) / 1000
    return brightness < 150


def _inside_label_style_for_fill(color: str) -> dict:
    if _is_dark_color(color):
        return {
            **INSIDE_LABEL_STYLE,
            "color": "#ffffff",
            "textBorderColor": "rgba(15,23,42,0.35)",
            "textShadowColor": "rgba(15,23,42,0.18)",
        }
    return {
        **INSIDE_LABEL_STYLE,
        "color": "#0f172a",
        "textBorderColor": "rgba(255,255,255,0.72)",
        "textShadowColor": "rgba(255,255,255,0.18)",
    }


def _decorate_series_items(data: list, *, formatter: str, child_key: str | None = None) -> list:
    decorated = []
    for idx, item in enumerate(data or []):
        if not isinstance(item, dict):
            decorated.append(item)
            continue
        color = (
            ((item.get("itemStyle") or {}).get("color"))
            if isinstance(item.get("itemStyle"), dict)
            else None
        ) or PALETTE[idx % len(PALETTE)]
        decorated_item = dict(item)
        item_style = dict(decorated_item.get("itemStyle") or {})
        item_style.setdefault("color", color)
        decorated_item["itemStyle"] = item_style
        decorated_item["label"] = {
            **_inside_label_style_for_fill(color),
            "show": True,
            "formatter": formatter,
        }
        if child_key and isinstance(decorated_item.get(child_key), list):
            decorated_item[child_key] = _decorate_series_items(
                decorated_item.get(child_key) or [],
                formatter=formatter,
                child_key=child_key,
            )
        decorated.append(decorated_item)
    return decorated


def _wrap_axis_label_text(value: str, max_line_chars: int = 12) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if " (" in text:
        text = text.replace(" (", "\n(")
    parts = []
    for line in text.split("\n"):
        current = line
        while len(current) > max_line_chars:
            parts.append(current[:max_line_chars])
            current = current[max_line_chars:]
        if current:
            parts.append(current)
    return "\n".join(parts)


def _extract_xml_content(text: str, tag: str) -> str:
    pattern = re.compile(rf"<{re.escape(tag)}>\s*(.*?)\s*</{re.escape(tag)}>", re.S)
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def _try_json_loads(value: str):
    if not value:
        return None
    try:
        return json.loads(value)
    except Exception:
        return None


def parse_output(raw_output: str) -> dict:
    raw_output = raw_output.strip()
    for tag in SUPPORTED_TAGS:
        pattern = re.compile(rf"<{re.escape(tag)}>\s*(.*?)\s*</{re.escape(tag)}>", re.S)
        match = pattern.search(raw_output)
        if match:
            body = match.group(1).strip()
            chart_data_raw = _extract_xml_content(body, "chartData")
            explain = _extract_xml_content(body, "explain")
            reference = _extract_xml_content(body, "reference")
            return {
                "tag": tag,
                "body": body,
                "chart_data_raw": chart_data_raw,
                "chart_data": _try_json_loads(chart_data_raw),
                "explain": explain,
                "reference_raw": reference,
                "reference": _try_json_loads(reference) if reference else [],
            }
    return {
        "tag": "unknown",
        "body": raw_output,
        "chart_data_raw": "",
        "chart_data": None,
        "explain": "",
        "reference_raw": "",
        "reference": [],
    }


def _base_option(title: str) -> dict:
    return {
        "color": PALETTE,
        "title": {
            "text": title,
            "left": "center",
            "top": 18,
            "textStyle": {
                "fontSize": 20,
                "fontWeight": "bold",
            },
        },
        "animationDuration": 700,
        "animationEasing": "cubicOut",
    }


def _bar_line_option(chart_data: dict) -> dict:
    series = chart_data.get("seriesData", [])
    has_line = any(item.get("type") == "line" for item in series)
    y_axis_name = chart_data.get("yAxisName") or []
    x_axis_data = [_wrap_axis_label_text(item) for item in (chart_data.get("xAxisData") or [])]
    if not isinstance(y_axis_name, list):
        y_axis_name = [str(y_axis_name)]

    y_axes = [
        {
            "type": "value",
            "name": y_axis_name[0] if y_axis_name else "",
            "axisLine": {"show": True},
            "splitLine": {"lineStyle": {"type": "dashed", "opacity": 0.3}},
        }
    ]
    if has_line:
        y_axes.append(
            {
                "type": "value",
                "name": y_axis_name[1] if len(y_axis_name) > 1 else "",
                "axisLine": {"show": True},
                "splitLine": {"show": False},
            }
        )

    normalized_series = []
    line_axis_index = 1 if has_line else 0
    for item in series:
        if item.get("type") == "line":
            normalized_series.append(
                {
                    "name": item.get("name", ""),
                    "type": "line",
                    "data": item.get("data", []),
                    "smooth": True,
                    "showSymbol": True,
                    "symbol": "circle",
                    "symbolSize": 8,
                    "lineStyle": {"width": 3},
                    "yAxisIndex": line_axis_index,
                }
            )
        else:
            normalized_series.append(
                {
                    "name": item.get("name", ""),
                    "type": "bar",
                    "data": item.get("data", []),
                    "barMaxWidth": 40,
                    "itemStyle": {"borderRadius": [8, 8, 0, 0]},
                }
            )

    option = _base_option(chart_data.get("title", ""))
    option.update(
        {
            "tooltip": {"trigger": "axis"},
            "legend": {"top": 56},
            "grid": {"left": 72, "right": 72, "top": 112, "bottom": 108},
            "xAxis": {
                "type": "category",
                "data": x_axis_data,
                "axisLabel": {
                    "interval": 0,
                    "rotate": 18,
                    "fontSize": 11,
                    "lineHeight": 16,
                    "margin": 18,
                },
            },
            "yAxis": y_axes,
            "series": normalized_series,
        }
    )
    return option


def _pie_option(chart_data: dict) -> dict:
    pie_data = _decorate_series_items(chart_data.get("data", []), formatter="{b}\n{c}")
    option = _base_option(chart_data.get("title", ""))
    option.update(
        {
            "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
            "legend": {"top": 56},
            "series": [
                {
                    "type": "pie",
                    "radius": ["42%", "70%"],
                    "center": ["50%", "60%"],
                    "avoidLabelOverlap": True,
                    "itemStyle": {"borderColor": "#fff", "borderWidth": 2},
                    "data": pie_data,
                }
            ],
        }
    )
    return option


def _radar_option(chart_data: dict) -> dict:
    series_data = []
    for name, values in (chart_data.get("data") or {}).items():
        series_data.append({"value": values, "name": name})

    option = _base_option(chart_data.get("title", ""))
    option.update(
        {
            "tooltip": {},
            "legend": {"top": 56},
            "radar": {
                "indicator": chart_data.get("list", []),
                "radius": "60%",
                "splitArea": {"areaStyle": {"opacity": 0.16}},
                "splitLine": {"lineStyle": {"opacity": 0.35}},
                "axisName": {"fontSize": 13},
            },
            "series": [
                {
                    "type": "radar",
                    "data": series_data,
                    "areaStyle": {"opacity": 0.12},
                    "lineStyle": {"width": 3},
                    "symbolSize": 7,
                }
            ],
        }
    )
    return option


def _sankey_option(chart_data: dict) -> dict:
    option = _base_option(chart_data.get("title", ""))
    option.update(
        {
            "tooltip": {"trigger": "item", "triggerOn": "mousemove"},
            "series": [
                {
                    "type": "sankey",
                    "layout": "none",
                    "top": 96,
                    "bottom": 20,
                    "nodeWidth": 18,
                    "nodeGap": 18,
                    "draggable": False,
                    "emphasis": {"focus": "adjacency"},
                    "lineStyle": {
                        "color": "gradient",
                        "curveness": 0.5,
                        "opacity": 0.55,
                    },
                    "label": {"fontSize": 13},
                    "data": chart_data.get("data", []),
                    "links": chart_data.get("links", []),
                }
            ],
        }
    )
    return option


def _treemap_option(chart_data: dict) -> dict:
    treemap_data = _decorate_series_items(chart_data.get("data", []), formatter="{b}\n{c}", child_key="children")
    option = _base_option(chart_data.get("title", ""))
    option.update(
        {
            "tooltip": {"formatter": "{b}: {c}"},
            "series": [
                {
                    "type": "treemap",
                    "top": 84,
                    "data": treemap_data,
                    "breadcrumb": {"show": False},
                }
            ],
        }
    )
    return option


def _sunburst_option(chart_data: dict) -> dict:
    sunburst_data = _decorate_series_items(chart_data.get("data", []), formatter="{b}\n{c}", child_key="children")
    option = _base_option(chart_data.get("title", ""))
    option.update(
        {
            "tooltip": {"formatter": "{b}: {c}"},
            "series": [
                {
                    "type": "sunburst",
                    "radius": ["15%", "82%"],
                    "sort": None,
                    "data": sunburst_data,
                    "label": {"rotate": "radial"},
                }
            ],
        }
    )
    return option


def _funnel_option(chart_data: dict) -> dict:
    funnel_data = _decorate_series_items(chart_data.get("data", []), formatter="{b}\n{c}")
    option = _base_option(chart_data.get("title", ""))
    option.update(
        {
            "tooltip": {"trigger": "item", "formatter": "{b}: {c}"},
            "legend": {"top": 56},
            "series": [
                {
                    "type": "funnel",
                    "left": "10%",
                    "top": 92,
                    "bottom": 24,
                    "width": "80%",
                    "sort": "descending",
                    "gap": 4,
                    "label": {"position": "inside"},
                    "data": funnel_data,
                }
            ],
        }
    )
    return option


def build_echarts_option(parsed: dict) -> dict | None:
    tag = parsed.get("tag")
    chart_data = parsed.get("chart_data")
    if not isinstance(chart_data, dict):
        return None
    if tag == "bar-line":
        return _bar_line_option(chart_data)
    if tag == "pie":
        return _pie_option(chart_data)
    if tag == "radar":
        return _radar_option(chart_data)
    if tag == "sankey":
        return _sankey_option(chart_data)
    if tag == "treemap":
        return _treemap_option(chart_data)
    if tag == "sunburst":
        return _sunburst_option(chart_data)
    if tag == "funnel":
        return _funnel_option(chart_data)
    return None


def _build_chart_html(option: dict) -> str:
    chart_id = f"chart_{uuid.uuid4().hex}"
    option_json = json.dumps(option, ensure_ascii=False)
    return (
        f'<div id="{chart_id}" class="chart-container" style="width:100%; height:560px;"></div>\n'
        "<script>\n"
        "try {\n"
        f'  var chartDom = document.getElementById("{chart_id}");\n'
        "  var myChart = echarts.init(chartDom);\n"
        f"  var option = {option_json};\n"
        "  myChart.setOption(option);\n"
        "  window.addEventListener('resize', function () { myChart.resize(); });\n"
        "} catch (error) {\n"
        f'  document.getElementById("{chart_id}").innerHTML = \'<div style="padding:16px;border:1px solid #d9d9d9;border-radius:12px;background:#fff7e6;color:#8c5a00;">Chart preview failed to render: \' + String(error) + \'</div>\';\n'
        "}\n"
        "</script>"
    )


def render_result_html(
    page_title: str,
    parsed: dict,
    raw_output: str,
    subtitle: str = "",
) -> str:
    lines = [f"# {page_title}"]
    if subtitle:
        lines.extend(["", subtitle])

    lines.extend(["", f"Output Tag: `{parsed.get('tag', 'unknown')}`"])

    explain = parsed.get("explain")
    if explain:
        lines.extend(["", "## Explain", explain])

    reference = parsed.get("reference")
    if reference:
        lines.extend(["", "## Reference", json.dumps(reference, ensure_ascii=False)])

    option = build_echarts_option(parsed)
    if option:
        lines.extend(["", "## Preview", "```custom_html", _build_chart_html(option), "```"])

    lines.extend(["", "## Raw Output", "```xml", raw_output.strip(), "```"])
    return markdown2html(page_title, "\n".join(lines))


def write_result_bundle(
    results_dir: Path,
    prefix: str,
    case_id: str,
    raw_output: str,
    extra: dict | None = None,
) -> dict:
    parsed = parse_output(raw_output)
    payload = {
        "prefix": prefix,
        "case_id": case_id,
        "tag": parsed.get("tag"),
        "chart_data": parsed.get("chart_data"),
        "reference": parsed.get("reference"),
        "explain": parsed.get("explain"),
        "raw_output": raw_output,
    }
    if extra:
        payload.update(extra)

    txt_path = results_dir / f"{prefix}__{case_id}.txt"
    json_path = results_dir / f"{prefix}__{case_id}.json"
    html_path = results_dir / f"{prefix}__{case_id}.html"

    txt_path.write_text(raw_output, encoding="utf-8")
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    html_path.write_text(
        render_result_html(
            f"{prefix} - {case_id}",
            parsed,
            raw_output,
            extra.get("subtitle", "") if extra else "",
        ),
        encoding="utf-8",
    )
    return payload
