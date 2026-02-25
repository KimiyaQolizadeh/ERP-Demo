from __future__ import annotations
import io
import logging
import os

from openai import OpenAI

from app.core.config import get_openai_api_key, get_openai_transcribe_model

logger = logging.getLogger("app.ai.transcribe")


def _env_first(*names: str, default: str = "") -> str:
    for name in names:
        value = str(os.getenv(name, "") or "").strip()
        if value:
            return value
    return default


def _model_candidates() -> list[str]:
    primary = get_openai_transcribe_model()
    candidates = [primary]
    for model in ("gpt-4o-mini-transcribe", "gpt-4o-transcribe", "whisper-1"):
        if model not in candidates:
            candidates.append(model)
    return candidates


def transcribe_wav_bytes(wav_bytes: bytes) -> str:
    api_key = _env_first("LLM_API_KEY", "OPENAI_API_KEY", default=get_openai_api_key())
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not configured")

    base_url = _env_first("LLM_BASE_URL", "OPENAI_BASE_URL", default="")
    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    client = OpenAI(**kwargs)
    # OpenAI expects a file-like object
    f = io.BytesIO(wav_bytes)
    f.name = "audio.wav"
    prompt = _env_first(
        "OPENAI_TRANSCRIBE_PROMPT",
        "LLM_TRANSCRIBE_PROMPT",
        default="Project management, timesheets, invoices, budgets, utilization, forecasts.",
    )

    last_error: Exception | None = None
    for model in _model_candidates():
        try:
            f.seek(0)
            resp = client.audio.transcriptions.create(model=model, file=f, prompt=prompt)
            text = resp.text or ""
            if text.strip():
                return text
        except Exception as exc:
            last_error = exc
            logger.warning("Transcription failed with model '%s': %s", model, exc)
            continue
    raise RuntimeError(f"Transcription failed for all models: {last_error}")
