from __future__ import annotations

import os
from typing import Any

from openai import OpenAI

from app.core.config import get_openai_api_key

ALLOWED_VOICES = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}
ALLOWED_FORMATS = {"mp3", "opus", "aac", "flac", "wav", "pcm"}
ALLOWED_TTS_MODELS = {"gpt-4o-mini-tts", "tts-1", "tts-1-hd"}


def _env_first(*names: str, default: str = "") -> str:
    for name in names:
        value = str(os.getenv(name, "") or "").strip()
        if value:
            return value
    return default


def _tts_models(preferred_model: str | None = None) -> list[str]:
    out: list[str] = []
    preferred = str(preferred_model or "").strip()
    if preferred and preferred in ALLOWED_TTS_MODELS:
        out.append(preferred)
    primary = _env_first("OPENAI_TTS_MODEL", "LLM_TTS_MODEL", default="gpt-4o-mini-tts")
    if primary and primary in ALLOWED_TTS_MODELS and primary not in out:
        out.append(primary)
    for model in ["tts-1", "tts-1-hd"]:
        if model not in out:
            out.append(model)
    return out


def synthesize_text_to_speech(
    text: str,
    *,
    voice: str = "alloy",
    response_format: str = "mp3",
    model: str | None = None,
) -> tuple[bytes, str, str]:
    api_key = _env_first("LLM_API_KEY", "OPENAI_API_KEY", default=get_openai_api_key())
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not configured")

    clean_text = str(text or "").strip()
    if not clean_text:
        raise RuntimeError("Text is empty")
    if len(clean_text) > 4000:
        clean_text = clean_text[:4000]

    safe_voice = str(voice or "alloy").strip().lower()
    if safe_voice not in ALLOWED_VOICES:
        safe_voice = "alloy"

    safe_format = str(response_format or "mp3").strip().lower()
    if safe_format not in ALLOWED_FORMATS:
        safe_format = "mp3"

    base_url = _env_first("LLM_BASE_URL", "OPENAI_BASE_URL", default="")
    kwargs: dict[str, Any] = {"api_key": api_key, "timeout": 30.0, "max_retries": 2}
    if base_url:
        kwargs["base_url"] = base_url
    client = OpenAI(**kwargs)

    last_error: Exception | None = None
    for model_name in _tts_models(model):
        try:
            resp = client.audio.speech.create(
                model=model_name,
                voice=safe_voice,  # type: ignore[arg-type]
                input=clean_text,
                response_format=safe_format,  # type: ignore[arg-type]
            )
            return bytes(resp.content), model_name, safe_format
        except Exception as exc:
            last_error = exc
            continue

    raise RuntimeError(f"TTS failed for all models: {last_error}")
