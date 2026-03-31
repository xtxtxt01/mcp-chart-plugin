from __future__ import annotations

import json
import importlib.util
import math
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


def _safe_float(value):
    if value in [None, ""]:
        return None
    try:
        return float(str(value).replace(",", ""))
    except Exception:
        return None


def _format_number(value: float | int | None) -> str:
    if value is None:
        return ""
    number = float(value)
    if abs(number - round(number)) < 1e-6:
        return str(int(round(number)))
    if abs(number) >= 100:
        return f"{number:.0f}"
    if abs(number) >= 10:
        return f"{number:.1f}".rstrip("0").rstrip(".")
    return f"{number:.2f}".rstrip("0").rstrip(".")


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


def _contains_numeric_values(series_list: list[dict]) -> bool:
    for item in series_list or []:
        if not isinstance(item, dict):
            continue
        for value in item.get("data", []) or []:
            if _safe_float(value) is not None:
                return True
    return False


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


def _value_label_style(color: str) -> dict:
    return {
        "show": True,
        "fontSize": 12,
        "fontWeight": "bold",
        "color": color,
        "backgroundColor": "rgba(255,255,255,0.92)",
        "borderRadius": 4,
        "padding": [3, 5],
    }


def _inside_bar_label_style() -> dict:
    return {
        "show": True,
        "fontSize": 12,
        "fontWeight": "bold",
        "color": "#ffffff",
        "textBorderColor": "rgba(15,23,42,0.28)",
        "textBorderWidth": 2,
    }


def _plain_value_label_style(color: str) -> dict:
    return {
        "show": True,
        "fontSize": 12,
        "fontWeight": "bold",
        "color": color,
        "textBorderColor": "#ffffff",
        "textBorderWidth": 2,
    }


def _text_graphic(
    x: float,
    y: float,
    text: str,
    color: str,
    *,
    font_size: int = 12,
    text_align: str = "center",
) -> dict:
    return {
        "type": "text",
        "left": x,
        "top": y,
        "silent": True,
        "z": 100,
        "style": {
            "text": text,
            "fill": color,
            "font": f"700 {font_size}px Arial",
            "stroke": "#ffffff",
            "lineWidth": 3,
            "textAlign": text_align,
            "textVerticalAlign": "middle",
        },
    }


def _rect_graphic(x: float, y: float, width: float, height: float, color: str) -> dict:
    return {
        "type": "rect",
        "left": x,
        "top": y,
        "silent": True,
        "shape": {"x": 0, "y": 0, "width": width, "height": height, "r": 4},
        "style": {"fill": color},
    }


def _collect_sunburst_legend_items(nodes: list, depth: int = 0) -> list[dict]:
    items: list[dict] = []
    for node in nodes or []:
        if not isinstance(node, dict):
            continue
        value = _safe_float(node.get("value"))
        color = ((node.get("itemStyle") or {}).get("color")) if isinstance(node.get("itemStyle"), dict) else None
        if value is not None:
            items.append(
                {
                    "name": str(node.get("name") or ""),
                    "value": value,
                    "color": color or PALETTE[len(items) % len(PALETTE)],
                    "depth": depth,
                }
            )
        children = node.get("children")
        if isinstance(children, list):
            items.extend(_collect_sunburst_legend_items(children, depth + 1))
    return items


def _prepare_sunburst_data(nodes: list[dict], depth: int = 0) -> list[dict]:
    prepared: list[dict] = []
    for node in nodes or []:
        if not isinstance(node, dict):
            continue
        prepared_node = dict(node)
        label = dict(prepared_node.get("label") or {})
        if depth == 0:
            label.update(
                {
                    "show": True,
                    "formatter": "{b}\n{c}",
                    "rotate": 0,
                    "fontSize": 13,
                }
            )
        else:
            label["show"] = False
        prepared_node["label"] = label
        children = prepared_node.get("children")
        if isinstance(children, list):
            prepared_node["children"] = _prepare_sunburst_data(children, depth + 1)
        prepared.append(prepared_node)
    return prepared


def _bar_line_option(chart_data: dict) -> dict:
    series = chart_data.get("seriesData", [])
    has_line = any(item.get("type") == "line" for item in series)
    has_bar = any(item.get("type") != "line" for item in series)
    has_any_numeric_values = _contains_numeric_values(series)
    y_axis_name = chart_data.get("yAxisName") or []
    x_axis_data = [_wrap_axis_label_text(item) for item in (chart_data.get("xAxisData") or [])]
    raw_x_axis_data = [str(item or "").strip() for item in (chart_data.get("xAxisData") or [])]
    if not isinstance(y_axis_name, list):
        y_axis_name = [str(y_axis_name)]
    needs_extra_bottom_room = (not has_any_numeric_values) or any(len(item) >= 8 for item in raw_x_axis_data)

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
    for idx, item in enumerate(series):
        color = PALETTE[idx % len(PALETTE)]
        raw_values = item.get("data", []) or []
        numeric_values = [_safe_float(value) for value in raw_values]
        uses_timeline_fallback = (not has_any_numeric_values) and any(
            _safe_float(value) is None and str(value or "").strip() for value in raw_values
        )
        if item.get("type") == "line":
            normalized_series.append(
                {
                    "name": item.get("name", ""),
                    "type": "line",
                    "data": [value if value is not None else None for value in numeric_values],
                    "smooth": True,
                    "showSymbol": True,
                    "symbol": "circle",
                    "symbolSize": 8,
                    "lineStyle": {"width": 3},
                    "itemStyle": {"color": color},
                    "label": {
                        **_plain_value_label_style(color),
                        "position": "top",
                        "distance": 24 if has_bar else 10,
                        "formatter": "{c}",
                    },
                    "yAxisIndex": line_axis_index,
                }
            )
        else:
            if uses_timeline_fallback:
                data = []
                for raw_value in raw_values:
                    label_text = _wrap_axis_label_text(str(raw_value or "").strip(), max_line_chars=9) or "-"
                    data.append(
                        {
                            "value": 1,
                            "label": {
                                **_value_label_style(color),
                                "position": "top",
                                "distance": 8,
                                "formatter": label_text,
                                "fontSize": 11,
                                "lineHeight": 14,
                                "padding": [4, 6],
                            },
                        }
                    )
            else:
                data = [value if value is not None else None for value in numeric_values]
            normalized_series.append(
                {
                    "name": item.get("name", ""),
                    "type": "bar",
                    "data": data,
                    "barMaxWidth": 40,
                    "itemStyle": {"borderRadius": [8, 8, 0, 0], "color": color},
                    "label": (
                        {
                            **_inside_bar_label_style(),
                            "position": "insideTop",
                            "distance": 30,
                            "formatter": "{c}",
                        }
                        if has_line and not uses_timeline_fallback
                        else {
                            **_value_label_style(color),
                            "position": "top",
                            "formatter": "{c}" if not uses_timeline_fallback else "",
                        }
                    ),
                }
            )

    option = _base_option(chart_data.get("title", ""))
    option.update(
        {
            "tooltip": {"trigger": "axis"},
            "legend": {"top": 56},
            "grid": {
                "left": 56,
                "right": 52,
                "top": 100,
                "bottom": 126 if needs_extra_bottom_room else 104,
                "containLabel": True,
            },
            "xAxis": {
                "type": "category",
                "data": x_axis_data,
                "axisLabel": {
                    "interval": 0,
                    "rotate": 18,
                    "fontSize": 11,
                    "lineHeight": 16,
                    "margin": 18,
                    "color": "#475569",
                    "fontWeight": 600,
                },
                "axisLine": {"lineStyle": {"color": "#94a3b8"}},
            },
            "yAxis": y_axes,
            "series": normalized_series,
        }
    )
    for axis in option["yAxis"]:
        axis["axisLabel"] = {**dict(axis.get("axisLabel") or {}), "color": "#475569"}
        axis["axisLine"] = {"show": True, "lineStyle": {"color": "#94a3b8"}}
        axis["nameTextStyle"] = {"color": "#475569", "fontWeight": 600}
    if not has_any_numeric_values:
        option["tooltip"] = {"trigger": "axis"}
        option["yAxis"][0].update(
            {
                "min": 0,
                "max": 1.4,
                "axisLabel": {"show": False},
                "axisTick": {"show": False},
                "splitLine": {"show": False},
            }
        )
    return option


def _pie_option(chart_data: dict) -> dict:
    pie_data = []
    for idx, item in enumerate(chart_data.get("data", []) or []):
        if not isinstance(item, dict):
            continue
        pie_data.append(
            {
                **item,
                "itemStyle": {
                    **dict(item.get("itemStyle") or {}),
                    "color": PALETTE[idx % len(PALETTE)],
                },
            }
        )
    option = _base_option(chart_data.get("title", ""))
    option.update(
        {
            "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
            "legend": {"top": 56},
            "series": [
                {
                    "type": "pie",
                    "radius": ["36%", "60%"],
                    "center": ["50%", "54%"],
                    "avoidLabelOverlap": True,
                    "itemStyle": {"borderColor": "#fff", "borderWidth": 2},
                    "label": {
                        "show": True,
                        "position": "outside",
                        "formatter": "{b}\n{c}",
                        "fontSize": 12,
                        "fontWeight": "bold",
                        "color": "#334155",
                        "backgroundColor": "rgba(255,255,255,0.94)",
                        "borderRadius": 4,
                        "padding": [3, 5],
                        "textBorderColor": "#ffffff",
                        "textBorderWidth": 2,
                    },
                    "labelLine": {
                        "show": True,
                        "length": 12,
                        "length2": 12,
                        "lineStyle": {"color": "#94a3b8", "width": 1.5},
                    },
                    "data": pie_data,
                }
            ],
        }
    )
    return option


def _radar_option(chart_data: dict) -> dict:
    series_data = []
    radar_data = chart_data.get("data") or {}
    indicators = [item for item in (chart_data.get("list") or []) if isinstance(item, dict)]
    for name, values in radar_data.items():
        series_data.append({"value": values, "name": name})

    graphic: list[dict] = []
    indicator_count = len(indicators)
    if indicator_count >= 3:
        cx = 600.0
        cy = 372.0
        radius = 182.0
        angles = [(-math.pi / 2) + math.tau * idx / indicator_count for idx in range(indicator_count)]
        series_items = list(radar_data.items())
        for idx, (angle, indicator) in enumerate(zip(angles, indicators)):
            label_radius = radius + 36
            block_x = cx + label_radius * math.cos(angle)
            block_y = cy + label_radius * math.sin(angle)
            align = "center"
            if block_x < cx - 24:
                align = "right"
            elif block_x > cx + 24:
                align = "left"

            if abs(math.cos(angle)) < 0.42 and math.sin(angle) < -0.82:
                block_y -= 10
            elif abs(math.cos(angle)) < 0.42 and math.sin(angle) > 0.82:
                block_y -= 18

            name_lines = _wrap_axis_label_text(str(indicator.get("name") or ""), max_line_chars=8).split("\n")
            name_start_y = block_y - 12
            for line_idx, line in enumerate(name_lines[:2]):
                graphic.append(
                    _text_graphic(
                        block_x,
                        name_start_y + line_idx * 14,
                        line,
                        "#475569",
                        font_size=12,
                        text_align=align,
                    )
                )

            is_vertical_axis = abs(math.cos(angle)) < 0.42 and abs(math.sin(angle)) > 0.82
            if is_vertical_axis:
                value_start_y = block_y + max(8, len(name_lines[:2]) * 11 - 4)
                split_index = math.ceil(len(series_items) / 2)
                side_offset = 50 if len(series_items) <= 4 else 44
                column_specs = [
                    (series_items[:split_index], block_x - side_offset, "right"),
                    (series_items[split_index:], block_x + side_offset, "left"),
                ]
                for items, column_x, column_align in column_specs:
                    for row_idx, (_, values) in enumerate(items):
                        value = _safe_float(values[idx])
                        if value is None:
                            continue
                        color = PALETTE[(row_idx if column_align == "right" else split_index + row_idx) % len(PALETTE)]
                        graphic.append(
                            _text_graphic(
                                column_x,
                                value_start_y + row_idx * 14,
                                _format_number(value),
                                color,
                                font_size=12,
                                text_align=column_align,
                            )
                        )
            else:
                value_start_y = block_y + max(8, len(name_lines[:2]) * 12)
                for series_idx, (_, values) in enumerate(series_items):
                    value = _safe_float(values[idx])
                    if value is None:
                        continue
                    color = PALETTE[series_idx % len(PALETTE)]
                    graphic.append(
                        _text_graphic(
                            block_x,
                            value_start_y + series_idx * 14,
                            _format_number(value),
                            color,
                            font_size=12,
                            text_align=align,
                        )
                    )

    option = _base_option(chart_data.get("title", ""))
    option.update(
        {
            "tooltip": {},
            "legend": {"top": 56},
            "radar": {
                "indicator": indicators,
                "center": ["50%", "54%"],
                "radius": 182,
                "splitArea": {"areaStyle": {"opacity": 0.16}},
                "splitLine": {"lineStyle": {"opacity": 0.35}},
                "axisName": {"show": False, "fontSize": 1, "color": "rgba(0,0,0,0)"},
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
            "graphic": graphic,
        }
    )
    return option


def _sankey_option(chart_data: dict) -> dict:
    outgoing: dict[str, float] = {}
    incoming: dict[str, float] = {}
    for link in chart_data.get("links", []) or []:
        if not isinstance(link, dict):
            continue
        source = str(link.get("source") or "")
        target = str(link.get("target") or "")
        value = _safe_float(link.get("value"))
        if not source or not target or value is None:
            continue
        outgoing[source] = outgoing.get(source, 0.0) + value
        incoming[target] = incoming.get(target, 0.0) + value

    nodes = []
    for idx, node in enumerate(chart_data.get("data", []) or []):
        if not isinstance(node, dict):
            continue
        name = str(node.get("name") or "")
        if not name:
            continue
        nodes.append(
            {
                **node,
                "value": max(
                    outgoing.get(name, 0.0),
                    incoming.get(name, 0.0),
                    _safe_float(node.get("value")) or 0.0,
                ),
                "itemStyle": {
                    **dict(node.get("itemStyle") or {}),
                    "color": PALETTE[idx % len(PALETTE)],
                },
            }
        )

    option = _base_option(chart_data.get("title", ""))
    option.update(
        {
            "tooltip": {"trigger": "item", "triggerOn": "mousemove"},
            "series": [
                {
                    "type": "sankey",
                    "layout": "none",
                    "left": 56,
                    "right": 170,
                    "top": 104,
                    "bottom": 78,
                    "nodeWidth": 18,
                    "nodeGap": 18,
                    "draggable": False,
                    "emphasis": {"focus": "adjacency"},
                    "lineStyle": {
                        "color": "gradient",
                        "curveness": 0.5,
                        "opacity": 0.55,
                    },
                    "label": {
                        "show": True,
                        "fontSize": 12,
                        "lineHeight": 16,
                        "formatter": "{b}\n{c}",
                    },
                    "edgeLabel": {
                        "show": True,
                        "position": "middle",
                        "fontSize": 11,
                        "color": "#475569",
                        "backgroundColor": "rgba(255,255,255,0.92)",
                        "borderRadius": 4,
                        "padding": [2, 4],
                        "formatter": "{c}",
                    },
                    "data": nodes,
                    "links": chart_data.get("links", []),
                }
            ],
        }
    )
    return option


def _build_treemap_legend_graphics(items: list[dict]) -> list[dict]:
    graphic: list[dict] = []
    legend_x = 944.0
    legend_y = 140.0
    legend_gap = 44.0
    for idx, item in enumerate(items[:8]):
        entry_y = legend_y + idx * legend_gap
        graphic.append(_rect_graphic(legend_x, entry_y - 8, 14, 14, str(item["color"])))
        label_text = "\n".join(
            [line for line in _wrap_axis_label_text(str(item["name"]), max_line_chars=10).split("\n") if line][:2]
            + [_format_number(item["value"])]
        )
        graphic.append(
            _text_graphic(
                legend_x + 24,
                entry_y,
                label_text,
                "#334155",
                font_size=12,
                text_align="left",
            )
        )
    return graphic


def _treemap_option(chart_data: dict) -> dict:
    raw_items = [item for item in (chart_data.get("data", []) or []) if isinstance(item, dict)]
    numeric_values = [_safe_float(item.get("value")) for item in raw_items if _safe_float(item.get("value")) is not None]
    has_extreme_skew = (
        len(numeric_values) >= 3
        and min(numeric_values) > 0
        and max(numeric_values) / min(numeric_values) >= 50
    )
    treemap_data = _decorate_series_items(raw_items, formatter="{b}", child_key="children")
    legend_items = []
    for idx, item in enumerate(raw_items):
        value = _safe_float(item.get("value"))
        if value is None:
            continue
        legend_items.append(
            {
                "name": str(item.get("name") or ""),
                "value": value,
                "color": (((item.get("itemStyle") or {}).get("color")) if isinstance(item.get("itemStyle"), dict) else None)
                or PALETTE[idx % len(PALETTE)],
            }
        )
    legend_items.sort(key=lambda item: item["value"], reverse=True)
    option = _base_option(chart_data.get("title", ""))
    option.update(
        {
            "tooltip": {"formatter": "{b}: {c}"},
            "series": [
                {
                    "type": "treemap",
                    "top": 78,
                    "left": 24,
                    "right": 248 if has_extreme_skew else 24,
                    "bottom": 22,
                    "data": treemap_data,
                    "breadcrumb": {"show": False},
                    "label": {
                        "show": True,
                        "formatter": "{b}\n{c}",
                        "overflow": "breakAll",
                        "fontSize": 12,
                        "lineHeight": 15,
                    },
                }
            ],
            "graphic": _build_treemap_legend_graphics(legend_items) if has_extreme_skew else [],
        }
    )
    return option


def _sunburst_option(chart_data: dict) -> dict:
    sunburst_data = _prepare_sunburst_data(
        _decorate_series_items(chart_data.get("data", []), formatter="{b}\n{c}", child_key="children")
    )
    legend_items = [item for item in _collect_sunburst_legend_items(sunburst_data) if int(item.get("depth") or 0) >= 1]
    if not legend_items:
        legend_items = _collect_sunburst_legend_items(sunburst_data)
    graphic: list[dict] = []
    legend_x = 808.0
    legend_y = 154.0
    legend_gap = 46.0
    for idx, item in enumerate(legend_items[:8]):
        entry_y = legend_y + idx * legend_gap
        graphic.append(_rect_graphic(legend_x, entry_y - 8, 14, 14, str(item["color"])))
        label_text = "\n".join(
            [line for line in _wrap_axis_label_text(str(item["name"]), max_line_chars=10).split("\n") if line][:2]
            + [_format_number(item["value"])]
        )
        graphic.append(
            _text_graphic(
                legend_x + 24,
                entry_y,
                label_text,
                "#334155",
                font_size=12,
                text_align="left",
            )
        )
    option = _base_option(chart_data.get("title", ""))
    option.update(
        {
            "tooltip": {"formatter": "{b}: {c}"},
            "series": [
                {
                    "type": "sunburst",
                    "center": ["36%", "54%"],
                    "radius": ["15%", "56%"],
                    "sort": None,
                    "nodeClick": False,
                    "data": sunburst_data,
                    "label": {"rotate": 0},
                    "labelLayout": {"hideOverlap": True},
                }
            ],
            "graphic": graphic,
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
                    "left": "13%",
                    "top": 96,
                    "bottom": 76,
                    "width": "72%",
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
    preview_html: str = "",
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

    if preview_html:
        lines.extend(["", "## Preview", "```custom_html", preview_html, "```"])
    else:
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
    extra = dict(extra or {})
    preview_html = str(extra.pop("preview_html", "") or "")
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
            preview_html=preview_html,
        ),
        encoding="utf-8",
    )
    return payload
