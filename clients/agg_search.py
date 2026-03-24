from __future__ import annotations

import sys
import time
from typing import Any

from ..config import DemoConfig, LOG_HELPER_ROOT, SEARCH_AUDIT_ROOT


for path in [LOG_HELPER_ROOT, SEARCH_AUDIT_ROOT]:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from chart_search_recall_helper import AggSearchConfig, search_query  # noqa: E402


class AggSearchClient:
    def __init__(self, config: DemoConfig | None = None):
        self.config = config or DemoConfig()

    def _build_cfg(self) -> AggSearchConfig:
        return AggSearchConfig(
            host=self.config.agg_host,
            host_header=self.config.agg_host_header,
            timeout_ms=self.config.agg_timeout_ms,
            pipeline_name=self.config.agg_pipeline_name,
            top_k=self.config.agg_top_k,
        )

    def search(self, query: str, sid: str | None = None) -> dict[str, Any]:
        actual_sid = sid or str(time.time_ns())
        return search_query(self._build_cfg(), query, sid=actual_sid)

    def search_many(self, queries: list[str], request_id: str) -> list[dict[str, Any]]:
        del request_id
        results: list[dict[str, Any]] = []
        for idx, query in enumerate(queries, start=1):
            result = self.search(query, sid=str(time.time_ns()))
            result["query_index"] = idx
            result["query"] = query
            results.append(result)
        return results
