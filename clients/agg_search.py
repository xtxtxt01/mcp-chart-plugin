from __future__ import annotations

import json
import hmac
import hashlib
import base64
import time
from email.utils import formatdate
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse, urlencode

import requests

from ..config import DemoConfig


@dataclass(slots=True)
class AggSearchConfig:
    backend: str = "agg"
    app_id: str = "187837596"
    business: str = "knowledge_base"
    extra_info: str = '{"domain":"generalv4","env":"dx-v4-0"}'
    host: str = "http://127.0.0.1:18080/search"
    host_header: str = ""
    pipeline_name: str = "pl_map_agg_search"
    timeout_ms: int = 15000
    high_light: bool = True
    top_k: int = 10
    full_text: bool = True
    disable_crawler: bool = True
    sites: tuple[str, ...] = ()
    ifly_endpoint: str = "https://cbm-search-api.cn-huabei-1.xf-yun.com/biz/search"
    ifly_api_key: str = ""
    ifly_api_secret: str = ""
    ifly_user_id: str = "user001"


def _compact(value: Any) -> str:
    return str(value or "").strip()


class AggSearchClient:
    def __init__(self, config: DemoConfig | None = None):
        self.config = config or DemoConfig()
        self._last_sid_ms = 0

    def _build_cfg(self) -> AggSearchConfig:
        return AggSearchConfig(
            backend=str(self.config.search_backend or "agg").strip().lower(),
            host=self.config.agg_host,
            host_header=self.config.agg_host_header,
            timeout_ms=self.config.agg_timeout_ms,
            pipeline_name=self.config.agg_pipeline_name,
            top_k=self.config.agg_top_k,
            ifly_endpoint=self.config.ifly_endpoint,
            ifly_api_key=self.config.ifly_api_key,
            ifly_api_secret=self.config.ifly_api_secret,
            ifly_user_id=self.config.ifly_user_id,
            app_id=self.config.ifly_app_id or "187837596",
        )

    def _search_once(self, query: str, sid: str) -> dict[str, Any]:
        cfg = self._build_cfg()
        if cfg.backend == "ifly_public":
            return self._search_ifly(query, sid=sid, cfg=cfg)
        append_data = {
            "sid": sid,
            "caller": cfg.app_id,
        }
        body = {
            "pipeline_name": cfg.pipeline_name,
            "appId": cfg.app_id,
            "name": query,
            "append": json.dumps(append_data, ensure_ascii=False),
            "uId": cfg.app_id,
            "extraInfo": cfg.extra_info,
            "limit": cfg.top_k,
            "sid": sid,
            "open_rerank": True,
            "disable_highlight": not cfg.high_light,
            "disable_crawler": cfg.disable_crawler,
            "full_text": cfg.full_text,
            "business": cfg.business,
            "sites": list(cfg.sites),
        }
        headers = {
            "Content-Type": "application/json",
        }
        if cfg.host_header:
            headers["Host"] = cfg.host_header

        try:
            response = requests.post(
                cfg.host.rstrip("/"),
                json=body,
                headers=headers,
                timeout=max(cfg.timeout_ms / 1000.0, 1.0),
            )
            status_code = response.status_code
            response.raise_for_status()
            payload = response.json()
            success = bool(payload.get("success")) and str(payload.get("err_code")) == "0"
            documents = (((payload.get("data") or {}).get("documents")) or []) if success else []
            error = ""
            if not success:
                error = f"agg_search error: {payload.get('err_code')} msg:{payload.get('err_message')}"
            return {
                "success": success,
                "endpoint": cfg.host.rstrip("/"),
                "url": cfg.host.rstrip("/"),
                "status_code": status_code,
                "payload": payload,
                "documents": documents,
                "error": error,
            }
        except Exception as exc:
            status_code = None
            response_obj = getattr(exc, "response", None)
            if response_obj is not None:
                status_code = getattr(response_obj, "status_code", None)
            return {
                "success": False,
                "endpoint": cfg.host.rstrip("/"),
                "url": cfg.host.rstrip("/"),
                "status_code": status_code,
                "payload": None,
                "documents": [],
                "error": _compact(exc),
            }

    def _search_ifly(self, query: str, sid: str, cfg: AggSearchConfig) -> dict[str, Any]:
        try:
            auth_url = self._build_ifly_auth_url(
                request_url=cfg.ifly_endpoint,
                method="POST",
                api_key=cfg.ifly_api_key,
                api_secret=cfg.ifly_api_secret,
            )
            body = {
                "appId": cfg.app_id,
                "limit": cfg.top_k,
                "name": query,
                "pipeline_name": cfg.pipeline_name,
                "timestamp": int(time.time() * 1000),
                "uId": cfg.ifly_user_id,
                "sid": sid,
                "open_rerank": True,
                "full_text": cfg.full_text,
                "disable_crawler": cfg.disable_crawler,
                "disable_highlight": not cfg.high_light,
            }
            response = requests.post(
                auth_url,
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                timeout=max(cfg.timeout_ms / 1000.0, 1.0),
            )
            status_code = response.status_code
            response.raise_for_status()
            payload = response.json()
            documents = (((payload.get("data") or {}).get("documents")) or [])
            return {
                "success": True,
                "endpoint": cfg.ifly_endpoint,
                "url": cfg.ifly_endpoint,
                "status_code": status_code,
                "payload": payload,
                "documents": documents,
                "error": "",
            }
        except Exception as exc:
            status_code = None
            response_obj = getattr(exc, "response", None)
            if response_obj is not None:
                status_code = getattr(response_obj, "status_code", None)
            return {
                "success": False,
                "endpoint": cfg.ifly_endpoint,
                "url": cfg.ifly_endpoint,
                "status_code": status_code,
                "payload": None,
                "documents": [],
                "error": _compact(exc),
            }

    @staticmethod
    def _build_ifly_auth_url(request_url: str, method: str, api_key: str, api_secret: str) -> str:
        parsed = urlparse(request_url)
        date = formatdate(timeval=None, localtime=False, usegmt=True)
        signature_origin = "\n".join(
            [
                f"host: {parsed.hostname or ''}",
                f"date: {date}",
                f"{method.upper()} {parsed.path or '/'} HTTP/1.1",
            ]
        )
        digest = hmac.new(
            api_secret.encode("utf-8"),
            signature_origin.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        signature_sha = base64.b64encode(digest).decode("utf-8")
        authorization_origin = (
            f'api_key="{api_key}", algorithm="hmac-sha256", '
            f'headers="host date request-line", signature="{signature_sha}"'
        )
        authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("utf-8")
        query = urlencode(
            {
                "host": parsed.hostname or "",
                "date": date,
                "authorization": authorization,
            }
        )
        return f"{request_url}?{query}"

    def _next_timestamp_sid(self) -> str:
        current_ms = time.time_ns() // 1_000_000
        while current_ms <= self._last_sid_ms:
            time.sleep(0.001)
            current_ms = time.time_ns() // 1_000_000
        self._last_sid_ms = current_ms
        return str(current_ms)

    def search(self, query: str, sid: str | None = None) -> dict[str, Any]:
        actual_sid = sid or self._next_timestamp_sid()
        return self._search_once(query, sid=actual_sid)

    def search_many(self, queries: list[str], request_id: str) -> list[dict[str, Any]]:
        del request_id
        results: list[dict[str, Any]] = []
        for idx, query in enumerate(queries, start=1):
            result = self.search(query)
            result["query_index"] = idx
            result["query"] = query
            results.append(result)
        return results
