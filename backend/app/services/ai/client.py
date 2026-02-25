# backend/app/services/ai/client.py
from __future__ import annotations
import json
from typing import Any, Optional, Type, TypeVar
from pydantic import BaseModel
from app.core.config import get_openai_api_key, get_openai_model

T = TypeVar("T", bound=BaseModel)

def ai_enabled() -> bool:
    return bool(get_openai_api_key())

def _extract_json(text: str) -> Optional[dict[str, Any]]:
    if not text:
        return None
    text = text.strip()
    # Try direct
    try:
        return json.loads(text)
    except Exception:
        pass
    # Try bracket extraction
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end+1])
        except Exception:
            return None
    return None


def _extract_response_text(resp: Any) -> str:
    text = getattr(resp, "output_text", None)
    if isinstance(text, str) and text.strip():
        return text
    try:
        chunks: list[str] = []
        for item in getattr(resp, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                value = getattr(content, "text", "")
                if value:
                    chunks.append(str(value))
        return "\n".join(chunks).strip()
    except Exception:
        return ""


def call_structured(schema: Type[T], system: str, user: str) -> tuple[Optional[T], str]:
    """
    Returns (parsed_schema_or_None, raw_text)
    """
    if not ai_enabled():
        return None, ""

    from openai import OpenAI  # lazy import
    client = OpenAI(api_key=get_openai_api_key())

    raw = ""
    try:
        resp = client.chat.completions.create(
            model=get_openai_model(),
            temperature=0,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        raw = resp.choices[0].message.content or ""
    except Exception as exc:
        # Fallback for newer SDKs/models exposed primarily through Responses API.
        if hasattr(client, "responses"):
            resp = client.responses.create(
                model=get_openai_model(),
                input=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0,
            )
            raw = _extract_response_text(resp)
        else:
            return None, f"chat_failed: {exc}"

    data = _extract_json(raw)
    if not data:
        return None, raw
    try:
        return schema(**data), raw
    except Exception:
        return None, raw
