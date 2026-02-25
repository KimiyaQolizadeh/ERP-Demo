import os
from pathlib import Path

from dotenv import load_dotenv

_CONFIG_PATH = Path(__file__).resolve()
_BACKEND_ROOT = _CONFIG_PATH.parents[2]
_PROJECT_ROOT = _CONFIG_PATH.parents[3]
_ENV_CANDIDATES = (
    Path.cwd() / ".env",
    _PROJECT_ROOT / ".env",
    _BACKEND_ROOT / ".env",
)

# Load both common locations so `python -m uvicorn ...` works from repo root or backend dir.
_seen: set[str] = set()
for _env_file in _ENV_CANDIDATES:
    _norm = str(_env_file.resolve())
    if _norm in _seen:
        continue
    _seen.add(_norm)
    if _env_file.exists():
        load_dotenv(_env_file, override=False)


def _env_str(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or "").strip()


def get_openai_api_key() -> str:
    return _env_str("OPENAI_API_KEY", "")


def get_openai_model() -> str:
    return _env_str("OPENAI_MODEL", "gpt-5.2")


def get_openai_transcribe_model() -> str:
    configured = _env_str("OPENAI_TRANSCRIBE_MODEL", "")
    if configured:
        return configured
    llm_configured = _env_str("LLM_TRANSCRIBE_MODEL", "")
    if llm_configured:
        return llm_configured
    return "gpt-4o-mini-transcribe"


def get_openai_embed_model() -> str:
    return _env_str("OPENAI_EMBED_MODEL", "text-embedding-3-small")


def get_env_search_paths() -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for path in _ENV_CANDIDATES:
        norm = str(path.resolve())
        if norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    return out

POSTGRES_DSN = os.getenv("POSTGRES_DSN", "postgresql+psycopg://erp:erp@localhost:5432/erp")
BACKEND_HOST = os.getenv("BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))

OPENAI_API_KEY = get_openai_api_key()
OPENAI_MODEL = get_openai_model()
OPENAI_TRANSCRIBE_MODEL = get_openai_transcribe_model()
OPENAI_EMBED_MODEL = get_openai_embed_model()
BILLABLE_AUTO_ACCEPT = float(os.getenv("BILLABLE_AUTO_ACCEPT", "0.80"))
BILLABLE_REVIEW_MIN = float(os.getenv("BILLABLE_REVIEW_MIN", "0.50"))
BILLABLE_REVIEW_MAX = float(os.getenv("BILLABLE_REVIEW_MAX", "0.80"))
