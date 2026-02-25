import hashlib
import os
from html import escape

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

from client.api import APIClient, APIError
from components.design_system import apply_theme

load_dotenv()
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
TTS_VOICE = os.getenv("OPENAI_TTS_VOICE", "alloy")

apply_theme(
    "Chat Assistant",
    "Ask about projects, employees, utilization, invoices, and forecast risks.",
    badge="AI",
)

st.markdown(
    """
<style>
.ca-chat-wrap { margin-top: 0.35rem; }
.ca-msg-row { display: flex; margin: 0.35rem 0; }
.ca-msg-row.user { justify-content: flex-end; }
.ca-msg-row.assistant { justify-content: flex-start; }
.ca-bubble {
  max-width: min(760px, 78%);
  padding: 0.62rem 0.8rem;
  border-radius: 16px;
  font-size: 0.94rem;
  line-height: 1.35;
  border: 1px solid #dbe3ef;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
  white-space: pre-wrap;
}
.ca-bubble.user {
  background: linear-gradient(180deg, #137fec 0%, #0b63be 100%);
  border-color: #0b63be;
  color: #ffffff;
  border-bottom-right-radius: 6px;
}
.ca-bubble.assistant {
  background: #ffffff;
  color: #0f172a;
  border-bottom-left-radius: 6px;
}
div[data-testid="stAudioInput"] {
  display: flex;
  justify-content: center;
}
div[data-testid="stAudioInput"] button {
  border-radius: 999px !important;
  min-height: 2.35rem !important;
  min-width: 2.35rem !important;
  padding: 0.05rem !important;
  border: 1px solid #cbd5e1 !important;
  background: #ffffff !important;
  box-shadow: 0 1px 4px rgba(15, 23, 42, 0.08) !important;
  color: #0f172a !important;
}
div[data-testid="stAudioInputInstructions"] {
  display: none !important;
}
div[data-testid="stAudioInput"] button[aria-label*="Stop"],
div[data-testid="stAudioInput"] button[aria-label*="stop"] {
  background: #dc2626 !important;
  border-color: #b91c1c !important;
  color: #ffffff !important;
  box-shadow: 0 0 0 0 rgba(220, 38, 38, 0.45);
  animation: ca-pulse 1.2s ease-in-out infinite;
}
@keyframes ca-pulse {
  0% { box-shadow: 0 0 0 0 rgba(220, 38, 38, 0.45); }
  70% { box-shadow: 0 0 0 10px rgba(220, 38, 38, 0.0); }
  100% { box-shadow: 0 0 0 0 rgba(220, 38, 38, 0.0); }
}
div[data-testid="stButton"] button[kind="secondary"] {
  border-radius: 999px !important;
  min-height: 2.35rem !important;
  min-width: 2.35rem !important;
  padding: 0 !important;
  border: 1px solid #cbd5e1 !important;
  background: #ffffff !important;
  color: #0f172a !important;
}
div[data-testid="stButton"] button[kind="secondary"]:hover {
  border-color: #94a3b8 !important;
  background: #f8fafc !important;
}
</style>
""",
    unsafe_allow_html=True,
)


def _render_message(role: str, text: str) -> None:
    safe_role = "user" if role == "user" else "assistant"
    safe_text = escape(str(text or "")).replace("\n", "<br>")
    st.markdown(
        f"<div class='ca-msg-row {safe_role}'><div class='ca-bubble {safe_role}'>{safe_text}</div></div>",
        unsafe_allow_html=True,
    )


def _audio_format(mime_type: str) -> str:
    raw = str(mime_type or "audio/mp3").strip().lower()
    if not raw.startswith("audio/"):
        return "audio/mp3"
    return raw.split(";", 1)[0]


def _stop_voice_playback() -> None:
    components.html(
        """
<script>
function stopAllAudio(doc) {
  try {
    const audios = doc.querySelectorAll("audio");
    audios.forEach((a) => {
      try { a.pause(); a.currentTime = 0; } catch (e) {}
    });
  } catch (e) {}
}
stopAllAudio(document);
try { stopAllAudio(parent.document); } catch (e) {}
try { stopAllAudio(window.top.document); } catch (e) {}
</script>
""",
        height=0,
    )


user_id = st.session_state.get("user_id")
if not user_id:
    st.warning("Select a user in the sidebar (Home page).")
    st.stop()
user_role = str(st.session_state.get("user_role", "") or "").upper()
if user_role not in {"PM", "FINANCE", "ADMIN"}:
    st.warning("Chat Assistant is available only for PM, Finance, or Admin users.")
    st.stop()

api = APIClient(st.session_state.get("backend_url", BACKEND_URL), user_id=user_id)

if "assistant_history" not in st.session_state:
    st.session_state["assistant_history"] = st.session_state.get("copilot_history", [])
if "assistant_draft" not in st.session_state:
    st.session_state["assistant_draft"] = ""
if "assistant_draft_next" not in st.session_state:
    st.session_state["assistant_draft_next"] = None
if "assistant_last_voice_hash" not in st.session_state:
    st.session_state["assistant_last_voice_hash"] = ""
if "assistant_input_mode" not in st.session_state:
    st.session_state["assistant_input_mode"] = "text"
if "assistant_submit_requested" not in st.session_state:
    st.session_state["assistant_submit_requested"] = False
if "assistant_tts_voice" not in st.session_state:
    st.session_state["assistant_tts_voice"] = TTS_VOICE
if "assistant_last_trace" not in st.session_state:
    st.session_state["assistant_last_trace"] = []
if "assistant_tts_audio_bytes" not in st.session_state:
    st.session_state["assistant_tts_audio_bytes"] = b""
if "assistant_tts_content_type" not in st.session_state:
    st.session_state["assistant_tts_content_type"] = "audio/mp3"
if "assistant_tts_autoplay" not in st.session_state:
    st.session_state["assistant_tts_autoplay"] = False

pending_draft = st.session_state.pop("assistant_draft_next", None)
if pending_draft is not None:
    st.session_state["assistant_draft"] = str(pending_draft)


def _send_prompt(prompt_text: str, input_mode: str = "text") -> None:
    text = str(prompt_text or "").strip()
    if not text:
        return
    st.session_state["assistant_history"].append({"role": "user", "content": text})
    trace: list[dict] = []
    try:
        with st.spinner("Generating"):
            response = api.copilot_chat(
                message=text,
                history=st.session_state["assistant_history"][:-1],
                month=None,
            )
        reply = str(response.get("reply", "")).strip() or "No response."
        raw_trace = response.get("trace", [])
        trace = list(raw_trace) if isinstance(raw_trace, list) else []
    except APIError as exc:
        reply = f"Error: {exc}"
    st.session_state["assistant_history"].append({"role": "assistant", "content": reply, "trace": trace})
    st.session_state["assistant_last_trace"] = trace
    st.session_state["assistant_draft_next"] = ""
    if input_mode == "voice" and not reply.startswith("Error:"):
        st.session_state["assistant_pending_tts"] = reply


def _mark_text_mode() -> None:
    st.session_state["assistant_input_mode"] = "text"
    st.session_state["assistant_submit_requested"] = True


voice_options = {"Nova": "nova", "Onyx": "onyx", "Alloy": "alloy"}
current_voice = str(st.session_state.get("assistant_tts_voice", TTS_VOICE) or TTS_VOICE).lower()
selected_voice_label = st.selectbox(
    "Voice",
    options=list(voice_options.keys()),
    index=next(
        (i for i, v in enumerate(voice_options.values()) if v == current_voice),
        list(voice_options.values()).index("alloy"),
    ),
)
st.session_state["assistant_tts_voice"] = voice_options[selected_voice_label]

chat_col, pause_col = st.columns([12, 1], vertical_alignment="center")
with pause_col:
    pause_voice_clicked = st.button("||", key="assistant_pause_voice_btn", type="secondary", help="Pause voice")
if pause_voice_clicked:
    st.session_state.pop("assistant_pending_tts", None)
    st.session_state["assistant_tts_audio_bytes"] = b""
    st.session_state["assistant_tts_autoplay"] = False
    _stop_voice_playback()

st.markdown("<div class='ca-chat-wrap'>", unsafe_allow_html=True)
for msg in st.session_state["assistant_history"]:
    _render_message(msg.get("role", "assistant"), msg.get("content", ""))
st.markdown("</div>", unsafe_allow_html=True)

last_trace = st.session_state.get("assistant_last_trace", [])
if last_trace:
    with st.expander("Last tool trace", expanded=False):
        st.json(last_trace)

with st.container():
    input_col, mic_col, send_col = st.columns([11, 1, 1], vertical_alignment="center")
    with input_col:
        st.text_input(
            "Message",
            key="assistant_draft",
            label_visibility="collapsed",
            placeholder="Message Chat Assistant",
            on_change=_mark_text_mode,
        )
    with mic_col:
        audio_file = st.audio_input("Mic", key="assistant_mic_inline", label_visibility="collapsed")
    with send_col:
        send_clicked = st.button(">", key="assistant_send_btn", type="secondary", help="Send")

if audio_file is not None:
    wav_bytes = audio_file.getvalue()
    if wav_bytes:
        audio_hash = hashlib.sha1(wav_bytes).hexdigest()
        if audio_hash != str(st.session_state.get("assistant_last_voice_hash") or ""):
            try:
                transcript_payload = api.ai_voice_transcribe(wav_bytes=wav_bytes)
                transcript = str(transcript_payload.get("transcript", "")).strip()
                st.session_state["assistant_last_voice_hash"] = audio_hash
                if transcript:
                    st.session_state["assistant_draft_next"] = transcript
                    st.session_state["assistant_input_mode"] = "voice"
                    st.session_state["assistant_submit_requested"] = True
                    st.rerun()
                else:
                    st.warning("No transcript content detected.")
            except APIError as exc:
                st.error(f"Voice transcription failed: {exc}")

if send_clicked:
    st.session_state["assistant_submit_requested"] = True

if st.session_state.pop("assistant_submit_requested", False):
    mode = "voice" if str(st.session_state.get("assistant_input_mode", "text")) == "voice" else "text"
    _send_prompt(st.session_state.get("assistant_draft", ""), input_mode=mode)
    st.session_state["assistant_input_mode"] = "text"
    st.rerun()

pending_tts = st.session_state.pop("assistant_pending_tts", None)
if pending_tts:
    try:
        audio_bytes, content_type = api.ai_voice_synthesize(
            pending_tts,
            voice=st.session_state.get("assistant_tts_voice", TTS_VOICE),
            response_format="mp3",
        )
        st.session_state["assistant_tts_audio_bytes"] = bytes(audio_bytes or b"")
        st.session_state["assistant_tts_content_type"] = _audio_format(content_type)
        st.session_state["assistant_tts_autoplay"] = True
    except APIError as exc:
        st.caption(f"Voice playback failed: {exc}")

tts_audio = bytes(st.session_state.get("assistant_tts_audio_bytes") or b"")
if tts_audio:
    st.audio(
        tts_audio,
        format=str(st.session_state.get("assistant_tts_content_type") or "audio/mp3"),
        autoplay=bool(st.session_state.get("assistant_tts_autoplay", False)),
    )
    st.session_state["assistant_tts_autoplay"] = False
