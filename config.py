from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


MCP_DEMO_ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = MCP_DEMO_ROOT.parent

ARTIFACTS_ROOT = MCP_DEMO_ROOT / "artifacts"
CHART_ARTIFACTS_ROOT = ARTIFACTS_ROOT / "charts"
OUTPUTS_ROOT = MCP_DEMO_ROOT / "outputs"
SCHEMAS_ROOT = MCP_DEMO_ROOT / "schemas"
ASSETS_ROOT = MCP_DEMO_ROOT / "assets"
VENDOR_ROOT = MCP_DEMO_ROOT / "vendor"
MD2HTML_PATH = VENDOR_ROOT / "md2html.py"

BASELINE_PROMPT_PATH = ASSETS_ROOT / "baseline_chart_prompt.txt"
RENDER_UTILS_PATH = VENDOR_ROOT / "render_utils.py"

CSV_ROOT = WORKSPACE_ROOT / "深度研究大模型日志调用_csv"
LOG_HELPER_ROOT = WORKSPACE_ROOT
SEARCH_AUDIT_ROOT = WORKSPACE_ROOT / "chart_search_recall_audit"

for path in [ARTIFACTS_ROOT, CHART_ARTIFACTS_ROOT, OUTPUTS_ROOT, SCHEMAS_ROOT, ASSETS_ROOT, VENDOR_ROOT]:
    path.mkdir(parents=True, exist_ok=True)


def relative_to_demo(path: Path) -> str:
    try:
        return path.resolve().relative_to(MCP_DEMO_ROOT.resolve()).as_posix()
    except Exception:
        return path.as_posix()


@dataclass(slots=True)
class DemoConfig:
    agg_host: str = os.getenv("MCP_DEMO_AGG_HOST", "http://127.0.0.1:18080/search")
    agg_host_header: str = os.getenv(
        "MCP_DEMO_AGG_HOST_HEADER",
        "dx-cbm-ocp-agg-search-inner.xf-yun.com",
    )
    agg_pipeline_name: str = os.getenv("MCP_DEMO_AGG_PIPELINE", "pl_map_agg_search")
    agg_timeout_ms: int = int(os.getenv("MCP_DEMO_AGG_TIMEOUT_MS", "15000"))
    agg_top_k: int = int(os.getenv("MCP_DEMO_AGG_TOP_K", "10"))
    chart_max_queries: int = int(os.getenv("MCP_DEMO_MAX_QUERIES", "8"))
    chart_max_docs_for_extraction: int = int(os.getenv("MCP_DEMO_MAX_DOCS", "10"))
    chart_existing_refs_quota: int = int(os.getenv("MCP_DEMO_EXISTING_REFS_QUOTA", "4"))
    chart_live_docs_quota: int = int(os.getenv("MCP_DEMO_LIVE_DOCS_QUOTA", "10"))

    llm_base_url: str = os.getenv(
        "MCP_DEMO_LLM_BASE_URL",
        "https://maas-api.cn-huabei-1.xf-yun.com/v1",
    )
    llm_api_key: str = os.getenv("MCP_DEMO_LLM_API_KEY", "")
    llm_model: str = os.getenv("MCP_DEMO_LLM_MODEL", "xopdeepseekv32")
    llm_timeout_s: int = int(os.getenv("MCP_DEMO_LLM_TIMEOUT_S", "90"))
    require_https_for_model: bool = os.getenv("MCP_DEMO_REQUIRE_HTTPS", "1") != "0"
    force_function_call: bool = os.getenv("MCP_DEMO_FORCE_FUNCTION_CALL", "1") != "0"

    default_file_name: str = "会计专科岗位_discover search.csv"
    default_row_id: int = 150
