from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MCP_DEMO_ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = MCP_DEMO_ROOT.parent

ARTIFACTS_ROOT = MCP_DEMO_ROOT / "artifacts"
CHART_ARTIFACTS_ROOT = ARTIFACTS_ROOT / "charts"
OUTPUTS_ROOT = MCP_DEMO_ROOT / "outputs"
SCHEMAS_ROOT = MCP_DEMO_ROOT / "schemas"
ASSETS_ROOT = MCP_DEMO_ROOT / "assets"
VENDOR_ROOT = MCP_DEMO_ROOT / "vendor"
MD2HTML_PATH = VENDOR_ROOT / "md2html.py"
ECHARTS_VENDOR_PATH = VENDOR_ROOT / "echarts.min.js"

BASELINE_PROMPT_PATH = ASSETS_ROOT / "baseline_chart_prompt.txt"
QUERY_PLANNING_PROMPT_PATH = ASSETS_ROOT / "query_planning_prompt.txt"
RENDER_UTILS_PATH = VENDOR_ROOT / "render_utils.py"
RENDER_TIMEOUT_S = int(os.getenv("MCP_DEMO_RENDER_TIMEOUT_S", "45"))
RENDER_VIRTUAL_TIME_BUDGET_MS = int(os.getenv("MCP_DEMO_RENDER_VIRTUAL_TIME_BUDGET_MS", "12000"))

for path in [ARTIFACTS_ROOT, CHART_ARTIFACTS_ROOT, OUTPUTS_ROOT, SCHEMAS_ROOT, ASSETS_ROOT, VENDOR_ROOT]:
    path.mkdir(parents=True, exist_ok=True)


def relative_to_demo(path: Path) -> str:
    try:
        return path.resolve().relative_to(MCP_DEMO_ROOT.resolve()).as_posix()
    except Exception:
        return path.as_posix()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() not in {"0", "false", "no", "off", ""}


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off", ""}


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


@dataclass(slots=True)
class LLMProfile:
    base_url: str
    api_key: str
    model: str
    timeout_s: int
    require_https_for_model: bool
    force_function_call: bool


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
    chart_live_docs_quota: int = int(os.getenv("MCP_DEMO_LIVE_DOCS_QUOTA", "3"))

    llm_base_url: str = os.getenv(
        "MCP_DEMO_LLM_BASE_URL",
        "https://maas-api.cn-huabei-1.xf-yun.com/v1",
    )
    llm_api_key: str = os.getenv("MCP_DEMO_LLM_API_KEY", "")
    llm_model: str = os.getenv("MCP_DEMO_LLM_MODEL", "xopdeepseekv32")
    llm_timeout_s: int = int(os.getenv("MCP_DEMO_LLM_TIMEOUT_S", "90"))
    require_https_for_model: bool = _env_bool("MCP_DEMO_REQUIRE_HTTPS", True)
    force_function_call: bool = _env_bool("MCP_DEMO_FORCE_FUNCTION_CALL", True)

    def llm_profile(self) -> LLMProfile:
        return LLMProfile(
            base_url=self.llm_base_url,
            api_key=self.llm_api_key,
            model=self.llm_model,
            timeout_s=self.llm_timeout_s,
            require_https_for_model=self.require_https_for_model,
            force_function_call=self.force_function_call,
        )

    def apply_overrides(self, config_dict: dict[str, Any] | None) -> None:
        for key, value in (config_dict or {}).items():
            if key == "llm" and isinstance(value, dict):
                self._apply_llm_overrides(value)
                continue
            if hasattr(self, key):
                setattr(self, key, value)

    def _apply_llm_overrides(self, llm_config: dict[str, Any]) -> None:
        values = llm_config
        if isinstance(llm_config.get("default"), dict):
            values = llm_config["default"]
        elif any(isinstance(llm_config.get(key), dict) for key in ("planning", "chart_generation", "chart")):
            for key in ("planning", "chart_generation", "chart"):
                if isinstance(llm_config.get(key), dict):
                    values = llm_config[key]
                    break

        key_map = {
            "base_url": "llm_base_url",
            "api_key": "llm_api_key",
            "model": "llm_model",
            "timeout_s": "llm_timeout_s",
            "require_https": "require_https_for_model",
            "require_https_for_model": "require_https_for_model",
            "force_function_call": "force_function_call",
        }
        for input_key, attr_name in key_map.items():
            if input_key not in values or not hasattr(self, attr_name):
                continue
            raw_value = values[input_key]
            if attr_name.endswith("_timeout_s"):
                setattr(self, attr_name, _coerce_int(raw_value, getattr(self, attr_name)))
            elif attr_name.endswith("_require_https_for_model") or attr_name.endswith("_force_function_call"):
                setattr(self, attr_name, _coerce_bool(raw_value))
            else:
                setattr(self, attr_name, str(raw_value or "").strip())
