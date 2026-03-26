from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests

from ..config import DemoConfig, LLMProfile


@dataclass(slots=True)
class ToolCallResult:
    ok: bool
    arguments: dict[str, Any] | None
    content: str = ""
    error: str = ""
    raw_response: dict[str, Any] | None = None


class SecureLLMClient:
    def __init__(
        self,
        config: DemoConfig | None = None,
        *,
        profile: LLMProfile | None = None,
    ):
        self.config = config or DemoConfig()
        self.profile = profile or self.config.llm_profile()

    def available(self) -> tuple[bool, str]:
        if not self.profile.base_url:
            return False, "LLM base URL is empty."
        parsed = urlparse(self.profile.base_url)
        if not parsed.scheme:
            return False, "LLM base URL has no scheme."
        if self.profile.require_https_for_model and parsed.scheme.lower() != "https":
            return False, "LLM base URL must use HTTPS."
        if not self.profile.api_key:
            return False, "LLM api key is empty."
        if not self.profile.model:
            return False, "LLM model is empty."
        return True, ""

    def call_with_tools(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict[str, Any]],
        tool_name: str,
        temperature: float = 0.0,
    ) -> ToolCallResult:
        ok, message = self.available()
        if not ok:
            return ToolCallResult(ok=False, arguments=None, error=message)

        if not self.profile.force_function_call:
            return self._call_structured_via_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                tools=tools,
                tool_name=tool_name,
                temperature=temperature,
            )

        payload: dict[str, Any] = {
            "model": self.profile.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "tools": tools,
            "tool_choice": {
                "type": "function",
                "function": {"name": tool_name},
            },
        }
        headers = {
            "Authorization": f"Bearer {self.profile.api_key}",
            "Content-Type": "application/json",
        }
        url = self.profile.base_url.rstrip("/") + "/chat/completions"

        primary_error = ""
        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.profile.timeout_s,
            )
            response.raise_for_status()
            data = response.json()
            message_obj = (data.get("choices") or [{}])[0].get("message", {})
            tool_calls = message_obj.get("tool_calls") or []
            content = str(message_obj.get("content") or "")
            if tool_calls:
                arguments_raw = tool_calls[0].get("function", {}).get("arguments", "{}")
                return ToolCallResult(
                    ok=True,
                    arguments=self._load_json_lenient(arguments_raw),
                    content=content,
                    raw_response=data,
                )
            if content:
                try:
                    return ToolCallResult(
                        ok=True,
                        arguments=self._load_json_lenient(content),
                        content=content,
                        raw_response=data,
                    )
                except Exception:
                    pass
            primary_error = "Model returned no tool call arguments."
        except Exception as exc:
            primary_error = str(exc)

        fallback = self._call_structured_via_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            tools=tools,
            tool_name=tool_name,
            temperature=temperature,
        )
        if fallback.ok:
            return fallback
        if primary_error and fallback.error:
            return ToolCallResult(
                ok=False,
                arguments=None,
                error=f"{primary_error} | text_fallback: {fallback.error}",
            )
        return ToolCallResult(ok=False, arguments=None, error=primary_error or fallback.error)

    def call_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
    ) -> ToolCallResult:
        ok, message = self.available()
        if not ok:
            return ToolCallResult(ok=False, arguments=None, error=message)

        payload: dict[str, Any] = {
            "model": self.profile.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.profile.api_key}",
            "Content-Type": "application/json",
        }
        url = self.profile.base_url.rstrip("/") + "/chat/completions"

        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.profile.timeout_s,
            )
            response.raise_for_status()
            data = response.json()
            message_obj = (data.get("choices") or [{}])[0].get("message", {})
            content = str(message_obj.get("content") or "").strip()
            if not content:
                return ToolCallResult(
                    ok=False,
                    arguments=None,
                    content="",
                    error="Model returned empty content.",
                    raw_response=data,
                )
            return ToolCallResult(
                ok=True,
                arguments=None,
                content=content,
                raw_response=data,
            )
        except Exception as exc:
            return ToolCallResult(ok=False, arguments=None, error=str(exc))

    def _call_structured_via_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict[str, Any]],
        tool_name: str,
        temperature: float = 0.0,
    ) -> ToolCallResult:
        schema = self._tool_parameters(tools, tool_name)
        if not schema:
            return ToolCallResult(ok=False, arguments=None, error=f"Tool schema not found for {tool_name}.")

        structured_system_prompt = (
            system_prompt
            + "\n\n"
            + "The serving endpoint may not support native function calling. "
            + "Return ONLY one JSON object that matches the provided schema exactly. "
            + "Do not use markdown fences, do not explain, and do not emit any extra text."
        )
        structured_user_prompt = (
            user_prompt
            + "\n\n"
            + "Target function name:\n"
            + tool_name
            + "\n\n"
            + "Return JSON that matches this parameters schema exactly:\n"
            + json.dumps(schema, ensure_ascii=False, indent=2)
        )
        response = self.call_text(
            system_prompt=structured_system_prompt,
            user_prompt=structured_user_prompt,
            temperature=temperature,
        )
        if not response.ok:
            return response
        try:
            parsed = self._load_json_lenient(response.content)
            if not isinstance(parsed, dict):
                return ToolCallResult(
                    ok=False,
                    arguments=None,
                    content=response.content,
                    error="Structured text fallback did not return a JSON object.",
                    raw_response=response.raw_response,
                )
            return ToolCallResult(
                ok=True,
                arguments=parsed,
                content=response.content,
                raw_response=response.raw_response,
            )
        except Exception as exc:
            return ToolCallResult(
                ok=False,
                arguments=None,
                content=response.content,
                error=f"Structured text fallback JSON parse failed: {exc}",
                raw_response=response.raw_response,
            )

    @staticmethod
    def _tool_parameters(tools: list[dict[str, Any]], tool_name: str) -> dict[str, Any] | None:
        for tool in tools:
            function = tool.get("function") or {}
            if function.get("name") == tool_name:
                params = function.get("parameters")
                if isinstance(params, dict):
                    return params
        return None

    @staticmethod
    def _load_json_lenient(raw: str) -> dict[str, Any]:
        text = str(raw or "").strip()
        if not text:
            return {}
        if text.startswith("```"):
            text = text.strip("`")
            text = text.replace("json\n", "", 1).strip()
        try:
            return json.loads(text)
        except Exception:
            start = min(
                [idx for idx in [text.find("{"), text.find("[")] if idx != -1],
                default=-1,
            )
            end = max(text.rfind("}"), text.rfind("]"))
            if start != -1 and end != -1 and end > start:
                candidate = text[start : end + 1]
                loaded = json.loads(candidate)
                if isinstance(loaded, dict):
                    return loaded
            raise
