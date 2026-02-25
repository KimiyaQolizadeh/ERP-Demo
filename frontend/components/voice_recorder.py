from __future__ import annotations

import io
import wave

import streamlit as st


def _wav_sample_rate(wav_bytes: bytes) -> int | None:
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            return int(wf.getframerate())
    except Exception:
        return None


def record_audio_ui(label: str = "Record voice note", key: str = "voice") -> tuple[bytes | None, int | None]:
    """
    Uses native Streamlit microphone capture when available.
    Returns (wav_bytes, sample_rate) or (None, None).
    """
    st.markdown(
        f"""
<div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:0.8rem 0.9rem;margin-bottom:0.5rem;">
  <div style="font-weight:800;color:#0f172a;">{label}</div>
  <div style="font-size:0.82rem;color:#64748b;margin-top:0.15rem;">Use your browser microphone to capture voice.</div>
</div>
""",
        unsafe_allow_html=True,
    )

    if hasattr(st, "audio_input"):
        audio_file = st.audio_input("Tap to record", key=f"{key}_audio_input")
        if audio_file is None:
            return None, None
        wav_bytes = audio_file.getvalue()
        if not wav_bytes:
            return None, None
        return wav_bytes, _wav_sample_rate(wav_bytes)

    st.warning("This Streamlit version does not support microphone capture.")
    return None, None
