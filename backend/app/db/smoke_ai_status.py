from __future__ import annotations

from app.core.config import (
    get_env_search_paths,
    get_openai_api_key,
    get_openai_embed_model,
    get_openai_model,
    get_openai_transcribe_model,
)


def run() -> None:
    key = get_openai_api_key()
    print("AI config:")
    print(f"- key configured: {bool(key)}")
    print(f"- key hint: {'...' + key[-4:] if len(key) >= 4 else ''}")
    print(f"- chat model: {get_openai_model()}")
    print(f"- transcribe model: {get_openai_transcribe_model()}")
    print(f"- embed model: {get_openai_embed_model()}")
    print("- env paths checked:")
    for p in get_env_search_paths():
        from pathlib import Path

        print(f"  - {p} (exists={Path(p).exists()})")

    if not key:
        print("OpenAI probe skipped: key missing.")
        return

    try:
        from openai import OpenAI

        client = OpenAI(api_key=key)
        resp = client.chat.completions.create(
            model=get_openai_model(),
            messages=[{"role": "user", "content": "Reply exactly OK"}],
            temperature=0,
        )
        text = (resp.choices[0].message.content or "").strip()
        print(f"OpenAI probe: ok, reply='{text}'")
    except Exception as exc:
        print(f"OpenAI probe failed: {exc}")


if __name__ == "__main__":
    run()
