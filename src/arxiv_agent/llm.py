from __future__ import annotations

import json
import re
from typing import Any

# 统一封装 OpenAI-compatible 接口调用及模型 JSON 响应解析。

import requests


class LLMClient:
    """Small OpenAI-compatible Chat Completions client.

    Works with providers exposing /v1/chat/completions. Check the provider's
    endpoint and model name in its documentation before configuring .env.
    """

    def __init__(self, env: dict[str, Any]):
        self.base_url = env["llm_base_url"].rstrip("/")
        self.api_key = env["llm_api_key"]
        self.model = env["llm_model"]
        self.timeout = int(env.get("llm_timeout", 180))
        if not self.api_key or not self.model:
            raise RuntimeError("LLM_API_KEY and LLM_MODEL must be configured in .env")
        self.session = requests.Session()

    def chat(self, system_prompt: str, user_prompt: str, max_tokens: int = 5000) -> str:
        url = self.base_url + "/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        response = self.session.post(
            url,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected LLM response format: {data}") from exc

    @staticmethod
    def parse_json(text: str) -> dict[str, Any]:
        cleaned = text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            value = json.loads(cleaned)
        except json.JSONDecodeError as original_error:
            start, end = cleaned.find("{"), cleaned.rfind("}")
            if start < 0 or end <= start:
                raise ValueError(f"LLM did not return JSON: {text[:500]}") from original_error
            try:
                value = json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError as exc:
                raise ValueError(f"LLM returned invalid JSON: {text[:500]}") from exc
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object from LLM")
        return value
