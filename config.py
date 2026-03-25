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

BASELINE_PROMPT_PATH = ASSETS_ROOT / "baseline_chart_prompt.txt"
QUERY_PLANNING_SYSTEM_PROMPT_PATH = ASSETS_ROOT / "query_planning_system_prompt.txt"
QUERY_PLANNING_USER_PROMPT_PATH = ASSETS_ROOT / "query_planning_user_prompt.txt"
QUERY_PLANNING_GAP_SECTION_PROMPT_PATH = ASSETS_ROOT / "query_planning_gap_section.txt"
FACT_EXTRACTION_SYSTEM_PROMPT_PATH = ASSETS_ROOT / "fact_extraction_system_prompt.txt"
FACT_EXTRACTION_USER_PROMPT_PATH = ASSETS_ROOT / "fact_extraction_user_prompt.txt"
FACT_EXTRACTION_DOCUMENT_BLOCK_PROMPT_PATH = ASSETS_ROOT / "fact_extraction_document_block.txt"
CHART_DECISION_USER_PROMPT_PATH = ASSETS_ROOT / "chart_decision_user_prompt.txt"
RENDER_UTILS_PATH = VENDOR_ROOT / "render_utils.py"

LOG_HELPER_ROOT = WORKSPACE_ROOT
SEARCH_AUDIT_ROOT = WORKSPACE_ROOT / "chart_search_recall_audit"

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
    require_https_for_model: bool = _env_bool("MCP_DEMO_REQUIRE_HTTPS", True)
    force_function_call: bool = _env_bool("MCP_DEMO_FORCE_FUNCTION_CALL", True)

    planning_llm_base_url: str = os.getenv("MCP_DEMO_LLM_PLANNING_BASE_URL", "")
    planning_llm_api_key: str = os.getenv("MCP_DEMO_LLM_PLANNING_API_KEY", "")
    planning_llm_model: str = os.getenv("MCP_DEMO_LLM_PLANNING_MODEL", "")
    planning_llm_timeout_s: int = int(os.getenv("MCP_DEMO_LLM_PLANNING_TIMEOUT_S", os.getenv("MCP_DEMO_LLM_TIMEOUT_S", "90")))
    planning_llm_require_https_for_model: bool = _env_bool(
        "MCP_DEMO_LLM_PLANNING_REQUIRE_HTTPS",
        _env_bool("MCP_DEMO_REQUIRE_HTTPS", True),
    )
    planning_llm_force_function_call: bool = _env_bool(
        "MCP_DEMO_LLM_PLANNING_FORCE_FUNCTION_CALL",
        _env_bool("MCP_DEMO_FORCE_FUNCTION_CALL", True),
    )

    extraction_llm_base_url: str = os.getenv("MCP_DEMO_LLM_EXTRACTION_BASE_URL", "")
    extraction_llm_api_key: str = os.getenv("MCP_DEMO_LLM_EXTRACTION_API_KEY", "")
    extraction_llm_model: str = os.getenv("MCP_DEMO_LLM_EXTRACTION_MODEL", "")
    extraction_llm_timeout_s: int = int(os.getenv("MCP_DEMO_LLM_EXTRACTION_TIMEOUT_S", os.getenv("MCP_DEMO_LLM_TIMEOUT_S", "90")))
    extraction_llm_require_https_for_model: bool = _env_bool(
        "MCP_DEMO_LLM_EXTRACTION_REQUIRE_HTTPS",
        _env_bool("MCP_DEMO_REQUIRE_HTTPS", True),
    )
    extraction_llm_force_function_call: bool = _env_bool(
        "MCP_DEMO_LLM_EXTRACTION_FORCE_FUNCTION_CALL",
        _env_bool("MCP_DEMO_FORCE_FUNCTION_CALL", True),
    )

    chart_generation_llm_base_url: str = os.getenv("MCP_DEMO_LLM_CHART_BASE_URL", "")
    chart_generation_llm_api_key: str = os.getenv("MCP_DEMO_LLM_CHART_API_KEY", "")
    chart_generation_llm_model: str = os.getenv("MCP_DEMO_LLM_CHART_MODEL", "")
    chart_generation_llm_timeout_s: int = int(os.getenv("MCP_DEMO_LLM_CHART_TIMEOUT_S", os.getenv("MCP_DEMO_LLM_TIMEOUT_S", "90")))
    chart_generation_llm_require_https_for_model: bool = _env_bool(
        "MCP_DEMO_LLM_CHART_REQUIRE_HTTPS",
        _env_bool("MCP_DEMO_REQUIRE_HTTPS", True),
    )
    chart_generation_llm_force_function_call: bool = _env_bool(
        "MCP_DEMO_LLM_CHART_FORCE_FUNCTION_CALL",
        _env_bool("MCP_DEMO_FORCE_FUNCTION_CALL", True),
    )

    def llm_profile(self, stage: str | None = None) -> LLMProfile:
        stage_key = (stage or "default").strip().lower()
        if stage_key in {"planning", "extraction", "chart_generation", "chart"}:
            prefix = "chart_generation" if stage_key in {"chart_generation", "chart"} else stage_key
            return LLMProfile(
                base_url=str(getattr(self, f"{prefix}_llm_base_url") or self.llm_base_url),
                api_key=str(getattr(self, f"{prefix}_llm_api_key") or self.llm_api_key),
                model=str(getattr(self, f"{prefix}_llm_model") or self.llm_model),
                timeout_s=int(getattr(self, f"{prefix}_llm_timeout_s")),
                require_https_for_model=bool(getattr(self, f"{prefix}_llm_require_https_for_model")),
                force_function_call=bool(getattr(self, f"{prefix}_llm_force_function_call")),
            )
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
        stage_map = {
            "default": "default",
            "planning": "planning",
            "extraction": "extraction",
            "chart_generation": "chart_generation",
            "chart": "chart_generation",
        }
        for input_stage, internal_stage in stage_map.items():
            value = llm_config.get(input_stage)
            if isinstance(value, dict):
                self._apply_llm_stage(internal_stage, value)

    def _apply_llm_stage(self, stage: str, values: dict[str, Any]) -> None:
        prefix = "llm" if stage == "default" else f"{stage}_llm"
        key_map = {
            "base_url": f"{prefix}_base_url",
            "api_key": f"{prefix}_api_key",
            "model": f"{prefix}_model",
            "timeout_s": f"{prefix}_timeout_s",
            "require_https": f"{prefix}_require_https_for_model",
            "require_https_for_model": f"{prefix}_require_https_for_model",
            "force_function_call": f"{prefix}_force_function_call",
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
