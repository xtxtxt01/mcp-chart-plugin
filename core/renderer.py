from __future__ import annotations

import html
import importlib.util
import json
import math
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

from ..config import (
    CHART_ARTIFACTS_ROOT,
    ECHARTS_VENDOR_PATH,
    MD2HTML_PATH,
    OUTPUTS_ROOT,
    RENDER_UTILS_PATH,
    RENDER_TIMEOUT_S,
    RENDER_VIRTUAL_TIME_BUDGET_MS,
    relative_to_demo,
)


def _simple_markdown_to_html(page_title: str, markdown_text: str) -> str:
    body = html.escape(markdown_text).replace("\n", "<br/>\n")
    return (
        "<!doctype html><html><head><meta charset='utf-8'/>"
        f"<title>{html.escape(page_title)}</title>"
        "<style>body{font-family:Arial,sans-serif;margin:24px;background:#f8fafc;color:#0f172a}"
        ".container{max-width:1200px;margin:0 auto;background:#fff;padding:24px;border-radius:16px;"
        "box-shadow:0 8px 24px rgba(15,23,42,.08)}</style></head>"
        f"<body><div class='container'>{body}</div></body></html>"
    )


def _install_md2html_support() -> None:
    if "src.tools.md2html" in sys.modules:
        return

    src_module = sys.modules.setdefault("src", types.ModuleType("src"))
    tools_module = sys.modules.setdefault("src.tools", types.ModuleType("src.tools"))

    if MD2HTML_PATH.exists():
        spec = importlib.util.spec_from_file_location("src.tools.md2html", MD2HTML_PATH)
        if spec is not None and spec.loader is not None:
            md2html_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(md2html_module)
            sys.modules["src.tools.md2html"] = md2html_module
            setattr(src_module, "tools", tools_module)
            setattr(tools_module, "md2html", md2html_module)
            return

    md2html_module = types.ModuleType("src.tools.md2html")
    md2html_module.markdown2html = _simple_markdown_to_html
    sys.modules["src.tools.md2html"] = md2html_module
    setattr(src_module, "tools", tools_module)
    setattr(tools_module, "md2html", md2html_module)


_install_md2html_support()

_spec = importlib.util.spec_from_file_location("mcp_demo_render_utils", RENDER_UTILS_PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"Unable to load render utils from {RENDER_UTILS_PATH}")
_render_utils = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_render_utils)


SVG_WIDTH = 1200
SVG_HEIGHT = 720
CARD_X = 32
CARD_Y = 32
CARD_WIDTH = 1136
CARD_HEIGHT = 656
PALETTE = [
    "#113f67",
    "#4d8fac",
    "#f4a259",
    "#c8553d",
    "#6b8f71",
    "#7a6c5d",
]
HEADLESS_BROWSER_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
]


def chart_spec_to_xml(spec: dict[str, Any]) -> str:
    chart_tag = str(spec.get("chart_tag") or "empty")
    chart_data = spec.get("chart_data") or {}
    explain = str(spec.get("explain") or "")
    reference = spec.get("reference") or []
    return (
        f"<{chart_tag}>\n"
        f"<chartData>{json.dumps(chart_data, ensure_ascii=False)}</chartData>\n"
        f"<explain>{html.escape(explain)}</explain>\n"
        f"<reference>{json.dumps(reference, ensure_ascii=False)}</reference>\n"
        f"</{chart_tag}>"
    )


def _render_empty_svg(title: str, explain: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="720" viewBox="0 0 1200 720">
  <rect width="1200" height="720" fill="#f6f8fb"/>
  <rect x="40" y="40" width="1120" height="640" rx="24" fill="#ffffff" stroke="#d9e2f2"/>
  <text x="80" y="120" font-size="40" font-weight="700" fill="#0f172a">{html.escape(title or "Chart unavailable")}</text>
  <text x="80" y="190" font-size="26" fill="#475569">No complete chart-ready data was found.</text>
  <foreignObject x="80" y="240" width="1040" height="340">
    <div xmlns="http://www.w3.org/1999/xhtml" style="font-size:24px;line-height:1.6;color:#334155;font-family:Arial, sans-serif;">
      {html.escape(explain or "The plugin returned empty because the available references could not support a stable chart.")}
    </div>
  </foreignObject>
</svg>"""


def _safe_float(value: Any) -> float | None:
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


def _label_style_for_fill(color: str) -> dict[str, str]:
    if _is_dark_color(color):
        return {
            "fill": "#ffffff",
            "stroke": "rgba(15,23,42,0.32)",
        }
    return {
        "fill": "#0f172a",
        "stroke": "rgba(255,255,255,0.72)",
    }


def _wrap_text(value: Any, max_line_chars: int = 12, max_lines: int = 3) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    if " (" in text:
        text = text.replace(" (", "\n(")
    lines: list[str] = []
    for raw_line in text.split("\n"):
        current = raw_line
        while len(current) > max_line_chars:
            lines.append(current[:max_line_chars])
            current = current[max_line_chars:]
        if current:
            lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        if not lines[-1].endswith("…"):
            lines[-1] = (lines[-1][: max(1, max_line_chars - 1)] + "…").strip()
    return lines


def _render_multiline_text(
    x: float,
    y: float,
    lines: list[str],
    *,
    font_size: int = 18,
    fill: str = "#0f172a",
    anchor: str = "middle",
    weight: str = "500",
    line_height: int | None = None,
    stroke: str | None = None,
    stroke_width: int = 2,
) -> str:
    if not lines:
        return ""
    line_height = line_height or int(font_size * 1.35)
    total_height = (len(lines) - 1) * line_height
    attrs = [
        f'x="{x:.1f}"',
        f'y="{y:.1f}"',
        f'font-size="{font_size}"',
        f'font-weight="{weight}"',
        f'fill="{fill}"',
        f'text-anchor="{anchor}"',
        'font-family="Arial, sans-serif"',
        'paint-order="stroke"',
    ]
    if stroke:
        attrs.append(f'stroke="{stroke}"')
        attrs.append(f'stroke-width="{stroke_width}"')
    tspans: list[str] = []
    start_y = y - total_height / 2
    for idx, line in enumerate(lines):
        dy = 0 if idx == 0 else line_height
        tspan_attrs = [f'x="{x:.1f}"']
        if idx == 0:
            tspan_attrs.append(f'y="{start_y:.1f}"')
        else:
            tspan_attrs.append(f'dy="{dy}"')
        tspans.append(f'<tspan {" ".join(tspan_attrs)}>{html.escape(line)}</tspan>')
    return f'<text {" ".join(attrs)}>{"".join(tspans)}</text>'


def _svg_frame(title: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_WIDTH}" height="{SVG_HEIGHT}" viewBox="0 0 {SVG_WIDTH} {SVG_HEIGHT}">',
        f'<rect width="{SVG_WIDTH}" height="{SVG_HEIGHT}" fill="#f6f8fb"/>',
        f'<rect x="{CARD_X}" y="{CARD_Y}" width="{CARD_WIDTH}" height="{CARD_HEIGHT}" rx="24" fill="#ffffff" stroke="#d9e2f2"/>',
        f'<text x="120" y="72" font-size="34" font-weight="700" fill="#0f172a">{html.escape(title)}</text>',
    ]


def _finish_svg(parts: list[str]) -> str:
    parts.append("</svg>")
    return "".join(parts)


def _find_headless_browser() -> Path | None:
    for candidate in HEADLESS_BROWSER_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def _echarts_script_tag() -> str:
    if ECHARTS_VENDOR_PATH.exists():
        try:
            script_body = ECHARTS_VENDOR_PATH.read_text(encoding="utf-8")
            return f"<script>{script_body}</script>"
        except Exception:
            pass
    return "<script src='https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js'></script>"


def _build_echarts_snapshot_html(option: dict[str, Any]) -> str:
    option_json = json.dumps(option, ensure_ascii=False)
    return (
        "<!doctype html><html><head><meta charset='utf-8'/>"
        f"{_echarts_script_tag()}"
        "<style>"
        "html,body{margin:0;padding:0;width:1200px;height:720px;background:#f6f8fb;overflow:hidden;}"
        ".card{width:1136px;height:656px;margin:32px;border:1px solid #d9e2f2;border-radius:24px;background:#ffffff;"
        "box-sizing:border-box;overflow:hidden;}"
        "#chart{width:1136px;height:656px;}"
        "</style></head><body>"
        "<div class='card'><div id='chart'></div></div>"
        "<script>"
        "const chart = echarts.init(document.getElementById('chart'));"
        f"const option = {option_json};"
        "chart.setOption(option);"
        "window.__chart_ready__ = true;"
        "</script>"
        "</body></html>"
    )


def _build_svg_snapshot_html(svg_markup: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'/>"
        "<style>"
        "html,body{margin:0;padding:0;width:1200px;height:720px;background:#f6f8fb;overflow:hidden;}"
        ".frame{width:1200px;height:720px;overflow:hidden;}"
        "svg{display:block;width:1200px;height:720px;}"
        "</style></head><body>"
        f"<div class='frame'>{svg_markup}</div>"
        "</body></html>"
    )


def _clear_chart_artifacts(target_dir: Path) -> None:
    for name in ["chart_01.png", "chart_01.svg", "_echarts_render.html", "_svg_render.html"]:
        try:
            (target_dir / name).unlink(missing_ok=True)
        except Exception:
            pass


def _screenshot_html_to_png(target_dir: Path, html_file_name: str, html_content: str) -> Path:
    browser = _find_headless_browser()
    if browser is None:
        raise RuntimeError("PNG rendering requires a local headless Edge or Chrome executable, but none was found.")
    target_dir.mkdir(parents=True, exist_ok=True)
    html_path = target_dir / html_file_name
    png_path = target_dir / "chart_01.png"
    html_path.write_text(html_content, encoding="utf-8")
    command = [
        str(browser),
        "--headless",
        "--disable-gpu",
        "--hide-scrollbars",
        "--allow-file-access-from-files",
        "--run-all-compositor-stages-before-draw",
        "--force-device-scale-factor=2",
        "--window-size=1200,720",
        f"--virtual-time-budget={RENDER_VIRTUAL_TIME_BUDGET_MS}",
        f"--screenshot={str(png_path)}",
        html_path.resolve().as_uri(),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=RENDER_TIMEOUT_S,
            check=False,
        )
        if completed.returncode == 0 and png_path.exists():
            return png_path
        error_text = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(
            "Headless browser PNG rendering failed."
            + (f" Browser output: {error_text[:500]}" if error_text else "")
        )
    finally:
        try:
            html_path.unlink(missing_ok=True)
        except Exception:
            pass


def _render_echarts_png(request_id: str, option: dict[str, Any]) -> Path:
    target_dir = CHART_ARTIFACTS_ROOT / request_id
    return _screenshot_html_to_png(
        target_dir,
        "_echarts_render.html",
        _build_echarts_snapshot_html(option),
    )


def _render_svg_markup_png(request_id: str, svg_markup: str) -> Path:
    target_dir = CHART_ARTIFACTS_ROOT / request_id
    return _screenshot_html_to_png(
        target_dir,
        "_svg_render.html",
        _build_svg_snapshot_html(svg_markup),
    )


def _polar_to_cartesian(cx: float, cy: float, radius: float, angle: float) -> tuple[float, float]:
    return cx + radius * math.cos(angle), cy + radius * math.sin(angle)


def _arc_path(
    cx: float,
    cy: float,
    outer_radius: float,
    inner_radius: float,
    start_angle: float,
    end_angle: float,
) -> str:
    if end_angle - start_angle >= math.tau:
        end_angle = start_angle + math.tau - 1e-4
    start_outer = _polar_to_cartesian(cx, cy, outer_radius, start_angle)
    end_outer = _polar_to_cartesian(cx, cy, outer_radius, end_angle)
    large_arc = 1 if (end_angle - start_angle) > math.pi else 0
    if inner_radius <= 0:
        return (
            f"M {start_outer[0]:.2f} {start_outer[1]:.2f} "
            f"A {outer_radius:.2f} {outer_radius:.2f} 0 {large_arc} 1 {end_outer[0]:.2f} {end_outer[1]:.2f} "
            f"L {cx:.2f} {cy:.2f} Z"
        )
    start_inner = _polar_to_cartesian(cx, cy, inner_radius, start_angle)
    end_inner = _polar_to_cartesian(cx, cy, inner_radius, end_angle)
    return (
        f"M {start_outer[0]:.2f} {start_outer[1]:.2f} "
        f"A {outer_radius:.2f} {outer_radius:.2f} 0 {large_arc} 1 {end_outer[0]:.2f} {end_outer[1]:.2f} "
        f"L {end_inner[0]:.2f} {end_inner[1]:.2f} "
        f"A {inner_radius:.2f} {inner_radius:.2f} 0 {large_arc} 0 {start_inner[0]:.2f} {start_inner[1]:.2f} Z"
    )


def _wrap_axis_label_text(value: str, max_line_chars: int = 10) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    if " (" in text:
        text = text.replace(" (", "\n(")
    lines: list[str] = []
    for raw_line in text.split("\n"):
        current = raw_line
        while len(current) > max_line_chars:
            lines.append(current[:max_line_chars])
            current = current[max_line_chars:]
        if current:
            lines.append(current)
    return lines


def _render_bar_line_svg(title: str, chart_data: dict[str, Any]) -> str:
    labels = [str(x) for x in (chart_data.get("xAxisData") or [])]
    series = chart_data.get("seriesData") or []
    if not labels or not series:
        return _render_empty_svg(title, "bar-line chart_data is incomplete.")

    width = 1200
    height = 720
    left = 120
    right = 80
    top = 130
    bottom = 180
    plot_w = width - left - right
    plot_h = height - top - bottom

    all_values: list[float] = []
    for item in series:
        for value in item.get("data", []):
            try:
                all_values.append(float(value))
            except Exception:
                continue
    max_value = max(all_values) if all_values else 1.0
    max_value = max(max_value, 1.0)

    colors = ["#113f67", "#f4a259", "#4d8fac", "#c8553d"]
    category_step = plot_w / max(len(labels), 1)
    bar_series = [item for item in series if item.get("type") != "line"]
    line_series = [item for item in series if item.get("type") == "line"]
    bar_width = min(46, category_step / max(len(bar_series), 1) * 0.58)

    svg_parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="1200" height="720" fill="#f6f8fb"/>',
        '<rect x="32" y="32" width="1136" height="656" rx="24" fill="#ffffff" stroke="#d9e2f2"/>',
        f'<text x="{left}" y="72" font-size="34" font-weight="700" fill="#0f172a">{html.escape(title)}</text>',
    ]

    for i in range(6):
        y = top + plot_h * i / 5
        value = max_value * (5 - i) / 5
        svg_parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" stroke="#e2e8f0"/>')
        svg_parts.append(f'<text x="{left - 18}" y="{y + 8:.1f}" text-anchor="end" font-size="18" fill="#64748b">{int(value)}</text>')

    svg_parts.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#334155" stroke-width="2"/>')
    svg_parts.append(f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#334155" stroke-width="2"/>')

    for idx, label in enumerate(labels):
        cx = left + category_step * idx + category_step / 2
        wrapped_lines = _wrap_axis_label_text(label)
        base_y = top + plot_h + 34
        for line_idx, line in enumerate(wrapped_lines[:3]):
            svg_parts.append(
                f'<text x="{cx:.1f}" y="{base_y + line_idx * 24:.1f}" text-anchor="middle" font-size="18" fill="#334155">{html.escape(line)}</text>'
            )

    for s_idx, item in enumerate(bar_series):
        color = colors[s_idx % len(colors)]
        for idx, raw_value in enumerate(item.get("data", [])):
            try:
                value = float(raw_value)
            except Exception:
                continue
            cx = left + category_step * idx + category_step / 2
            cluster_offset = (s_idx - (len(bar_series) - 1) / 2) * (bar_width + 8)
            x = cx + cluster_offset - bar_width / 2
            bar_h = plot_h * value / max_value
            y = top + plot_h - bar_h
            svg_parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{bar_h:.1f}" rx="8" fill="{color}"/>'
            )

    for s_idx, item in enumerate(line_series, start=len(bar_series)):
        color = colors[s_idx % len(colors)]
        points: list[str] = []
        for idx, raw_value in enumerate(item.get("data", [])):
            try:
                value = float(raw_value)
            except Exception:
                continue
            cx = left + category_step * idx + category_step / 2
            y = top + plot_h - (plot_h * value / max_value)
            points.append(f"{cx:.1f},{y:.1f}")
            svg_parts.append(f'<circle cx="{cx:.1f}" cy="{y:.1f}" r="6" fill="{color}"/>')
        if points:
            svg_parts.append(
                f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="4" stroke-linejoin="round" stroke-linecap="round"/>'
            )

    legend_x = left
    legend_y = 100
    for idx, item in enumerate(series):
        color = colors[idx % len(colors)]
        lx = legend_x + idx * 220
        svg_parts.append(f'<rect x="{lx}" y="{legend_y}" width="28" height="16" rx="4" fill="{color}"/>')
        svg_parts.append(
            f'<text x="{lx + 40}" y="{legend_y + 14}" font-size="20" fill="#334155">{html.escape(str(item.get("name") or ""))}</text>'
        )

    svg_parts.append("</svg>")
    return "".join(svg_parts)


def _render_pie_svg(title: str, chart_data: dict[str, Any]) -> str:
    raw_items = chart_data.get("data") or []
    items: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        value = _safe_float(item.get("value"))
        if value is None or value <= 0:
            continue
        items.append({"name": str(item.get("name") or ""), "value": value})
    if not items:
        return _render_empty_svg(title, "pie chart_data is incomplete.")

    total = sum(item["value"] for item in items)
    cx, cy = 360.0, 390.0
    outer_radius = 180.0
    inner_radius = 96.0
    parts = _svg_frame(title)
    parts.append(_render_multiline_text(cx, cy - 14, ["总量", _format_number(total)], font_size=24, weight="700"))

    start_angle = -math.pi / 2
    legend_x = 670.0
    legend_y = 165.0
    legend_gap = 68.0
    for idx, item in enumerate(items):
        color = PALETTE[idx % len(PALETTE)]
        span = math.tau * item["value"] / total
        end_angle = start_angle + span
        parts.append(
            f'<path d="{_arc_path(cx, cy, outer_radius, inner_radius, start_angle, end_angle)}" fill="{color}" stroke="#ffffff" stroke-width="4"/>'
        )
        if span >= 0.32:
            label_angle = (start_angle + end_angle) / 2
            label_radius = (outer_radius + inner_radius) / 2
            lx, ly = _polar_to_cartesian(cx, cy, label_radius, label_angle)
            lines = _wrap_text(item["name"], max_line_chars=8, max_lines=2)
            pct = item["value"] / total * 100
            lines.append(f"{pct:.1f}%")
            style = _label_style_for_fill(color)
            parts.append(
                _render_multiline_text(
                    lx,
                    ly,
                    lines,
                    font_size=15,
                    fill=style["fill"],
                    stroke=style["stroke"],
                    weight="700",
                )
            )

        legend_item_y = legend_y + idx * legend_gap
        pct = item["value"] / total * 100
        parts.append(
            f'<rect x="{legend_x:.1f}" y="{legend_item_y - 16:.1f}" width="28" height="28" rx="6" fill="{color}"/>'
        )
        parts.append(
            _render_multiline_text(
                legend_x + 48,
                legend_item_y,
                _wrap_text(item["name"], max_line_chars=16, max_lines=2),
                font_size=20,
                fill="#334155",
                anchor="start",
                weight="600",
                line_height=24,
            )
        )
        parts.append(
            f'<text x="{legend_x + 360:.1f}" y="{legend_item_y + 7:.1f}" font-size="20" font-weight="600" fill="#475569" text-anchor="end">{_format_number(item["value"])} / {pct:.1f}%</text>'
        )
        start_angle = end_angle
    return _finish_svg(parts)


def _render_radar_svg(title: str, chart_data: dict[str, Any]) -> str:
    indicators = [item for item in (chart_data.get("list") or []) if isinstance(item, dict)]
    series_map = chart_data.get("data") or {}
    if len(indicators) < 3 or not isinstance(series_map, dict) or not series_map:
        return _render_empty_svg(title, "radar chart_data is incomplete.")

    cx, cy = 430.0, 410.0
    radius = 210.0
    angles = [(-math.pi / 2) + math.tau * idx / len(indicators) for idx in range(len(indicators))]
    parts = _svg_frame(title)

    for level in range(5, 0, -1):
        ratio = level / 5
        points = []
        for angle in angles:
            px, py = _polar_to_cartesian(cx, cy, radius * ratio, angle)
            points.append(f"{px:.1f},{py:.1f}")
        fill = "#eff4ff" if level % 2 else "#f8fbff"
        parts.append(f'<polygon points="{" ".join(points)}" fill="{fill}" stroke="#dbe5f5" stroke-width="1.5"/>')

    for angle, indicator in zip(angles, indicators):
        ax, ay = _polar_to_cartesian(cx, cy, radius, angle)
        parts.append(f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{ax:.1f}" y2="{ay:.1f}" stroke="#cbd5e1" stroke-width="1.5"/>')
        label_x, label_y = _polar_to_cartesian(cx, cy, radius + 36, angle)
        anchor = "middle"
        if label_x < cx - 20:
            anchor = "end"
        elif label_x > cx + 20:
            anchor = "start"
        parts.append(
            _render_multiline_text(
                label_x,
                label_y,
                _wrap_text(indicator.get("name"), max_line_chars=8, max_lines=2),
                font_size=18,
                fill="#334155",
                anchor=anchor,
                weight="600",
                line_height=22,
            )
        )

    legend_x = 760.0
    legend_y = 165.0
    for idx, (series_name, values) in enumerate(series_map.items()):
        color = PALETTE[idx % len(PALETTE)]
        normalized_points: list[str] = []
        for angle, indicator, raw_value in zip(angles, indicators, values):
            max_value = _safe_float(indicator.get("max")) or 1.0
            value = _safe_float(raw_value) or 0.0
            ratio = max(0.0, min(value / max_value, 1.0))
            px, py = _polar_to_cartesian(cx, cy, radius * ratio, angle)
            normalized_points.append(f"{px:.1f},{py:.1f}")
            parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5" fill="{color}" stroke="#ffffff" stroke-width="2"/>')
        parts.append(f'<polygon points="{" ".join(normalized_points)}" fill="{color}" fill-opacity="0.16" stroke="{color}" stroke-width="3"/>')
        ly = legend_y + idx * 42
        parts.append(f'<rect x="{legend_x:.1f}" y="{ly - 12:.1f}" width="24" height="24" rx="6" fill="{color}"/>')
        parts.append(f'<text x="{legend_x + 38:.1f}" y="{ly + 7:.1f}" font-size="20" font-weight="600" fill="#334155">{html.escape(str(series_name))}</text>')
    return _finish_svg(parts)


def _render_funnel_svg(title: str, chart_data: dict[str, Any]) -> str:
    raw_items = chart_data.get("data") or []
    items: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        value = _safe_float(item.get("value"))
        if value is None or value <= 0:
            continue
        items.append({"name": str(item.get("name") or ""), "value": value})
    if not items:
        return _render_empty_svg(title, "funnel chart_data is incomplete.")

    parts = _svg_frame(title)
    top_y = 150.0
    bottom_y = 650.0
    gap = 8.0
    segment_height = (bottom_y - top_y - gap * (len(items) - 1)) / len(items)
    center_x = 600.0
    max_width = 840.0
    min_width = 140.0
    max_value = max(item["value"] for item in items)

    for idx, item in enumerate(items):
        color = PALETTE[idx % len(PALETTE)]
        top_ratio = item["value"] / max_value
        top_width = max(min_width, max_width * top_ratio)
        if idx < len(items) - 1:
            next_ratio = items[idx + 1]["value"] / max_value
            bottom_width = max(min_width, max_width * next_ratio)
        else:
            bottom_width = max(84.0, top_width * 0.42)
        y0 = top_y + idx * (segment_height + gap)
        y1 = y0 + segment_height
        points = [
            (center_x - top_width / 2, y0),
            (center_x + top_width / 2, y0),
            (center_x + bottom_width / 2, y1),
            (center_x - bottom_width / 2, y1),
        ]
        points_text = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        parts.append(f'<polygon points="{points_text}" fill="{color}" stroke="#ffffff" stroke-width="3"/>')
        style = _label_style_for_fill(color)
        label_lines = _wrap_text(item["name"], max_line_chars=10, max_lines=2)
        label_lines.append(_format_number(item["value"]))
        parts.append(
            _render_multiline_text(
                center_x,
                (y0 + y1) / 2,
                label_lines,
                font_size=18,
                fill=style["fill"],
                stroke=style["stroke"],
                weight="700",
                line_height=22,
            )
        )
    return _finish_svg(parts)


def _treemap_color(depth: int, idx: int) -> str:
    return PALETTE[(depth + idx) % len(PALETTE)]


def _render_treemap_nodes(
    parts: list[str],
    nodes: list[dict[str, Any]],
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    depth: int = 0,
    vertical: bool | None = None,
) -> None:
    if not nodes or width <= 6 or height <= 6:
        return
    vertical = width >= height if vertical is None else vertical
    total = sum(max(_safe_float(node.get("value")) or 0.0, 0.0) for node in nodes)
    if total <= 0:
        return

    cursor = x if vertical else y
    for idx, node in enumerate(nodes):
        value = max(_safe_float(node.get("value")) or 0.0, 0.0)
        if value <= 0:
            continue
        if vertical:
            span = width * value / total if idx < len(nodes) - 1 else (x + width - cursor)
            rect_x, rect_y, rect_w, rect_h = cursor, y, span, height
            cursor += span
        else:
            span = height * value / total if idx < len(nodes) - 1 else (y + height - cursor)
            rect_x, rect_y, rect_w, rect_h = x, cursor, width, span
            cursor += span

        color = _treemap_color(depth, idx)
        parts.append(
            f'<rect x="{rect_x:.1f}" y="{rect_y:.1f}" width="{max(rect_w - 2, 1):.1f}" height="{max(rect_h - 2, 1):.1f}" fill="{color}" stroke="#ffffff" stroke-width="2"/>'
        )
        style = _label_style_for_fill(color)
        label_lines = _wrap_text(node.get("name"), max_line_chars=10 if rect_w > 160 else 7, max_lines=3)
        label_lines.append(_format_number(value))
        parts.append(
            _render_multiline_text(
                rect_x + rect_w / 2,
                rect_y + rect_h / 2,
                label_lines,
                font_size=18 if rect_w > 140 and rect_h > 80 else 15,
                fill=style["fill"],
                stroke=style["stroke"],
                weight="700",
                line_height=21,
            )
        )
        children = [child for child in (node.get("children") or []) if isinstance(child, dict)]
        if children and rect_w > 180 and rect_h > 120:
            _render_treemap_nodes(
                parts,
                children,
                rect_x + 6,
                rect_y + 28,
                rect_w - 12,
                rect_h - 34,
                depth=depth + 1,
                vertical=not vertical,
            )


def _render_treemap_svg(title: str, chart_data: dict[str, Any]) -> str:
    nodes = [item for item in (chart_data.get("data") or []) if isinstance(item, dict)]
    if not nodes:
        return _render_empty_svg(title, "treemap chart_data is incomplete.")
    parts = _svg_frame(title)
    _render_treemap_nodes(parts, nodes, 70.0, 120.0, 940.0, 550.0)
    return _finish_svg(parts)


def _tree_depth(nodes: list[dict[str, Any]]) -> int:
    if not nodes:
        return 0
    return 1 + max(_tree_depth([child for child in (node.get("children") or []) if isinstance(child, dict)]) for node in nodes)


def _render_sunburst_level(
    parts: list[str],
    nodes: list[dict[str, Any]],
    cx: float,
    cy: float,
    start_angle: float,
    end_angle: float,
    inner_radius: float,
    ring_width: float,
    *,
    depth: int = 0,
) -> None:
    total = sum(max(_safe_float(node.get("value")) or 0.0, 0.0) for node in nodes)
    if total <= 0:
        return
    angle_cursor = start_angle
    for idx, node in enumerate(nodes):
        value = max(_safe_float(node.get("value")) or 0.0, 0.0)
        if value <= 0:
            continue
        span = (end_angle - start_angle) * value / total
        node_end = angle_cursor + span
        color = _treemap_color(depth, idx)
        path = _arc_path(cx, cy, inner_radius + ring_width - 3, inner_radius + 3, angle_cursor, node_end)
        parts.append(f'<path d="{path}" fill="{color}" stroke="#ffffff" stroke-width="2"/>')
        if span >= 0.26:
            mid_angle = (angle_cursor + node_end) / 2
            text_radius = inner_radius + ring_width / 2
            tx, ty = _polar_to_cartesian(cx, cy, text_radius, mid_angle)
            style = _label_style_for_fill(color)
            lines = _wrap_text(node.get("name"), max_line_chars=8, max_lines=2)
            lines.append(_format_number(value))
            parts.append(
                _render_multiline_text(
                    tx,
                    ty,
                    lines,
                    font_size=14,
                    fill=style["fill"],
                    stroke=style["stroke"],
                    weight="700",
                    line_height=16,
                )
            )
        children = [child for child in (node.get("children") or []) if isinstance(child, dict)]
        if children:
            _render_sunburst_level(
                parts,
                children,
                cx,
                cy,
                angle_cursor,
                node_end,
                inner_radius + ring_width,
                ring_width,
                depth=depth + 1,
            )
        angle_cursor = node_end


def _render_sunburst_svg(title: str, chart_data: dict[str, Any]) -> str:
    nodes = [item for item in (chart_data.get("data") or []) if isinstance(item, dict)]
    if not nodes:
        return _render_empty_svg(title, "sunburst chart_data is incomplete.")
    parts = _svg_frame(title)
    cx, cy = 410.0, 405.0
    max_depth = max(_tree_depth(nodes), 1)
    inner_radius = 58.0
    outer_radius = 250.0
    ring_width = (outer_radius - inner_radius) / max_depth
    parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{inner_radius - 6:.1f}" fill="#eff4ff" stroke="#dbe5f5"/>')
    _render_sunburst_level(parts, nodes, cx, cy, -math.pi / 2, (math.pi * 3) / 2, inner_radius, ring_width)
    legend_x = 760.0
    legend_y = 170.0
    for idx, node in enumerate(nodes[:5]):
        color = _treemap_color(0, idx)
        ly = legend_y + idx * 46
        parts.append(f'<rect x="{legend_x:.1f}" y="{ly - 14:.1f}" width="24" height="24" rx="6" fill="{color}"/>')
        parts.append(f'<text x="{legend_x + 36:.1f}" y="{ly + 5:.1f}" font-size="19" font-weight="600" fill="#334155">{html.escape(str(node.get("name") or ""))}</text>')
    return _finish_svg(parts)


def _render_sankey_svg(title: str, chart_data: dict[str, Any]) -> str:
    nodes_raw = [item for item in (chart_data.get("data") or []) if isinstance(item, dict) and item.get("name")]
    links_raw = [item for item in (chart_data.get("links") or []) if isinstance(item, dict)]
    if not nodes_raw or not links_raw:
        return _render_empty_svg(title, "sankey chart_data is incomplete.")

    nodes: dict[str, dict[str, Any]] = {str(item["name"]): {"name": str(item["name"])} for item in nodes_raw}
    outgoing: dict[str, float] = {name: 0.0 for name in nodes}
    incoming: dict[str, float] = {name: 0.0 for name in nodes}
    levels: dict[str, int] = {name: 0 for name in nodes}
    normalized_links: list[dict[str, Any]] = []
    for item in links_raw:
        source = str(item.get("source") or "")
        target = str(item.get("target") or "")
        value = _safe_float(item.get("value"))
        if not source or not target or value is None or value <= 0:
            continue
        if source not in nodes:
            nodes[source] = {"name": source}
            outgoing[source] = 0.0
            incoming[source] = 0.0
            levels[source] = 0
        if target not in nodes:
            nodes[target] = {"name": target}
            outgoing[target] = 0.0
            incoming[target] = 0.0
            levels[target] = 0
        outgoing[source] += value
        incoming[target] += value
        normalized_links.append({"source": source, "target": target, "value": value})
    if not normalized_links:
        return _render_empty_svg(title, "sankey links are empty.")

    for _ in range(len(nodes)):
        updated = False
        for link in normalized_links:
            next_level = levels[link["source"]] + 1
            if levels.get(link["target"], 0) < next_level:
                levels[link["target"]] = next_level
                updated = True
        if not updated:
            break

    grouped: dict[int, list[str]] = {}
    for name, level in levels.items():
        grouped.setdefault(level, []).append(name)
    max_level = max(grouped) if grouped else 0
    plot_left, plot_right = 120.0, 1040.0
    plot_top, plot_bottom = 150.0, 630.0
    plot_height = plot_bottom - plot_top
    node_width = 22.0
    gap = 24.0

    value_map = {name: max(outgoing.get(name, 0.0), incoming.get(name, 0.0), 1.0) for name in nodes}
    scale_candidates = []
    for level_names in grouped.values():
        total_value = sum(value_map[name] for name in level_names)
        scale_candidates.append((plot_height - gap * (len(level_names) - 1)) / total_value)
    scale = max(min(scale_candidates), 5.0) if scale_candidates else 10.0

    positions: dict[str, dict[str, float]] = {}
    level_span = (plot_right - plot_left - node_width) / max(max_level, 1) if max_level else 0.0
    for level, level_names in grouped.items():
        total_height = sum(value_map[name] * scale for name in level_names) + gap * (len(level_names) - 1)
        cursor_y = plot_top + (plot_height - total_height) / 2
        x = plot_left + level * level_span
        for idx, name in enumerate(level_names):
            height = max(28.0, value_map[name] * scale)
            positions[name] = {
                "x": x,
                "y": cursor_y,
                "width": node_width,
                "height": height,
                "color": PALETTE[(level + idx) % len(PALETTE)],
            }
            cursor_y += height + gap

    out_offsets = {name: 0.0 for name in nodes}
    in_offsets = {name: 0.0 for name in nodes}
    parts = _svg_frame(title)
    for link in normalized_links:
        source_pos = positions[link["source"]]
        target_pos = positions[link["target"]]
        thickness = max(10.0, link["value"] * scale)
        sy0 = source_pos["y"] + out_offsets[link["source"]]
        sy1 = sy0 + thickness
        ty0 = target_pos["y"] + in_offsets[link["target"]]
        ty1 = ty0 + thickness
        out_offsets[link["source"]] += thickness
        in_offsets[link["target"]] += thickness
        x0 = source_pos["x"] + source_pos["width"]
        x1 = target_pos["x"]
        c0 = x0 + (x1 - x0) * 0.38
        c1 = x0 + (x1 - x0) * 0.62
        path = (
            f"M {x0:.1f} {sy0:.1f} "
            f"C {c0:.1f} {sy0:.1f} {c1:.1f} {ty0:.1f} {x1:.1f} {ty0:.1f} "
            f"L {x1:.1f} {ty1:.1f} "
            f"C {c1:.1f} {ty1:.1f} {c0:.1f} {sy1:.1f} {x0:.1f} {sy1:.1f} Z"
        )
        parts.append(f'<path d="{path}" fill="{source_pos["color"]}" fill-opacity="0.30" stroke="none"/>')

    for name, pos in positions.items():
        color = pos["color"]
        parts.append(
            f'<rect x="{pos["x"]:.1f}" y="{pos["y"]:.1f}" width="{pos["width"]:.1f}" height="{pos["height"]:.1f}" rx="8" fill="{color}"/>'
        )
        anchor = "start"
        text_x = pos["x"] + pos["width"] + 10
        if levels[name] == max_level:
            anchor = "end"
            text_x = pos["x"] - 10
        parts.append(
            _render_multiline_text(
                text_x,
                pos["y"] + pos["height"] / 2,
                _wrap_text(name, max_line_chars=10, max_lines=2),
                font_size=16,
                fill="#334155",
                anchor=anchor,
                weight="600",
                line_height=20,
            )
        )
    return _finish_svg(parts)


def _render_generic_svg(title: str, chart_tag: str, explain: str, chart_data: dict[str, Any]) -> str:
    preview = html.escape(json.dumps(chart_data, ensure_ascii=False)[:800])
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="720" viewBox="0 0 1200 720">
  <rect width="1200" height="720" fill="#f6f8fb"/>
  <rect x="40" y="40" width="1120" height="640" rx="24" fill="#ffffff" stroke="#d9e2f2"/>
  <text x="80" y="110" font-size="38" font-weight="700" fill="#0f172a">{html.escape(title)}</text>
  <text x="80" y="170" font-size="26" fill="#475569">Chart tag: {html.escape(chart_tag)}</text>
  <foreignObject x="80" y="220" width="1040" height="150">
    <div xmlns="http://www.w3.org/1999/xhtml" style="font-size:22px;line-height:1.6;color:#334155;font-family:Arial, sans-serif;">
      {html.escape(explain)}
    </div>
  </foreignObject>
  <foreignObject x="80" y="410" width="1040" height="220">
    <div xmlns="http://www.w3.org/1999/xhtml" style="font-size:18px;line-height:1.5;color:#0f172a;font-family:Consolas, monospace;white-space:pre-wrap;">
      {preview}
    </div>
  </foreignObject>
</svg>"""


def _build_chart_svg(title: str, spec: dict[str, Any]) -> str:
    chart_tag = str(spec.get("chart_tag") or "empty")
    chart_data = spec.get("chart_data") or {}
    explain = str(spec.get("explain") or "")
    if chart_tag == "empty":
        return _render_empty_svg(title, explain)
    if chart_tag == "bar-line":
        return _render_bar_line_svg(title, chart_data)
    if chart_tag == "pie":
        return _render_pie_svg(title, chart_data)
    if chart_tag == "radar":
        return _render_radar_svg(title, chart_data)
    if chart_tag == "funnel":
        return _render_funnel_svg(title, chart_data)
    if chart_tag == "treemap":
        return _render_treemap_svg(title, chart_data)
    if chart_tag == "sunburst":
        return _render_sunburst_svg(title, chart_data)
    if chart_tag == "sankey":
        return _render_sankey_svg(title, chart_data)
    return _render_generic_svg(title, chart_tag, explain, chart_data)


def render_chart_artifacts(spec: dict[str, Any], request_id: str, title: str) -> dict[str, Any]:
    target_dir = CHART_ARTIFACTS_ROOT / request_id
    target_dir.mkdir(parents=True, exist_ok=True)
    _clear_chart_artifacts(target_dir)
    raw_xml = chart_spec_to_xml(spec)
    parsed = _render_utils.parse_output(raw_xml)
    option = _render_utils.build_echarts_option(parsed)
    payload = _render_utils.write_result_bundle(
        OUTPUTS_ROOT,
        "mcp_demo_chart",
        request_id,
        raw_xml,
        extra={"subtitle": title},
    )
    if option:
        chart_path = _render_echarts_png(request_id=request_id, option=option)
    else:
        chart_path = _render_svg_markup_png(request_id=request_id, svg_markup=_build_chart_svg(title, spec))
    txt_path = OUTPUTS_ROOT / f"mcp_demo_chart__{request_id}.txt"
    json_path = OUTPUTS_ROOT / f"mcp_demo_chart__{request_id}.json"
    html_path = OUTPUTS_ROOT / f"mcp_demo_chart__{request_id}.html"
    return {
        "success": True,
        "raw_xml": raw_xml,
        "payload": payload,
        "relative_path": relative_to_demo(chart_path),
        "png_path": relative_to_demo(chart_path),
        "image_path": relative_to_demo(chart_path),
        "txt_path": relative_to_demo(txt_path),
        "json_path": relative_to_demo(json_path),
        "html_path": relative_to_demo(html_path),
        "markdown": f"![{title}]({relative_to_demo(chart_path)})",
    }
