"""Check the LLM setup with a few tiny real calls (well under $0.01 in total).

    uv run python -m scripts.llm_smoke_test                # JSON-mode call to MODEL_SMART and MODEL_FAST
    uv run python -m scripts.llm_smoke_test --list-models  # what the proxy exposes (GET /v1/models)
    uv run python -m scripts.llm_smoke_test --fallback     # also one call straight to the Groq fallback

Every call goes through app/core/llm.py, so this also checks the JSON parsing and the
usage log line (tokens + cost). Exits non-zero if any call fails.
"""

import argparse
import logging
import sys

from app.core import llm
from app.core.config import get_settings

_SYSTEM = 'Reply with only this JSON object: {"ok": true, "words": "<three words>"}'
_USER = "Greet a new user in three words."


def _check(provider: str, label: str, model: str) -> bool:
    try:
        data = llm.complete_json(provider, model, _SYSTEM, _USER, task="smoke_test")
    except Exception as exc:  # noqa: BLE001 - report every failure kind
        print(f"FAIL  {label:<8} {provider}/{model}: {type(exc).__name__}: {exc}")
        return False
    ok = data.get("ok") is True
    print(f"{'OK  ' if ok else 'ODD '}  {label:<8} {provider}/{model}: {data}")
    return ok


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)
    logging.basicConfig(level=logging.WARNING, format="  %(message)s")
    logging.getLogger("app.core.llm").setLevel(logging.INFO)  # show tokens and cost per call

    parser = argparse.ArgumentParser(description="Check the LiteLLM proxy and Groq fallback.")
    parser.add_argument("--list-models", action="store_true", help="list the proxy's model ids")
    parser.add_argument("--fallback", action="store_true", help="also call the Groq fallback")
    args = parser.parse_args()

    s = get_settings()
    results: list[bool] = []
    if not (s.LLM_BASE_URL and s.LLM_API_KEY):
        print("LLM_BASE_URL / LLM_API_KEY are not set in backend/.env; skipping the proxy checks.")
    else:
        if args.list_models:
            try:
                print("Proxy models:", ", ".join(llm.list_models(llm.PRIMARY)) or "(none)")
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL  listing models: {type(exc).__name__}: {exc}")
                results.append(False)
        results.append(_check(llm.PRIMARY, "smart", s.MODEL_SMART))
        results.append(_check(llm.PRIMARY, "fast", s.MODEL_FAST))
    if args.fallback:
        if not s.FALLBACK_API_KEY:
            print("FALLBACK_API_KEY is not set in backend/.env; skipping the Groq check.")
        else:
            results.append(_check(llm.FALLBACK, "fallback", s.FALLBACK_MODEL))
    if not results:
        print("Nothing to check yet: add the keys to backend/.env.")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
