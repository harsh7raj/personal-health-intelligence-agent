"""Every LLM call in the app goes through this module (memory.md D15).

llm_json(task, system, user) picks the model for `task` from config (task -> tier ->
model), calls the LiteLLM proxy, falls back to Groq on any error, and logs tokens and
estimated cost for every call. Callers check is_available() first and keep their own
deterministic fallback for when no LLM can be reached at all.
"""

import hashlib
import json
import logging
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx  # ships with openai
from openai import OpenAI

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

PRIMARY = "litellm"
FALLBACK = "groq"
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_DEFAULT_TIERS: dict[str, str] = Settings.model_fields["LLM_TASK_TIERS"].default
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class LLMUnavailable(RuntimeError):
    """No configured provider produced a usable JSON answer."""


def _primary_ready(s: Settings) -> bool:
    return bool(s.LLM_BASE_URL and s.LLM_API_KEY)


def is_available() -> bool:
    """True if a provider (LiteLLM or the Groq fallback) is configured, or a response cache
    is active (a demo replay can then run offline from stored answers)."""
    s = get_settings()
    return _primary_ready(s) or bool(s.FALLBACK_API_KEY) or _cache_dir is not None


# ---- Response cache (demo replays; memory.md D32) ----
_cache_dir: Path | None = None
_cache_used: set[Path] = set()


@contextmanager
def response_cache(directory: Path, *, prune: bool = False) -> Iterator[Path]:
    """Within this block an identical request (task + prompts) returns the stored answer
    instead of calling a model, and new answers are stored. Makes demo re-seeding offline,
    free and identical. Not for the live app.

    prune=True: if the block finishes without an error, delete stored answers it did not use
    (left behind when a prompt changed)."""
    global _cache_dir
    previous, _cache_dir = _cache_dir, Path(directory)
    _cache_dir.mkdir(parents=True, exist_ok=True)
    _cache_used.clear()
    try:
        yield _cache_dir
        if prune:
            for stale in set(_cache_dir.glob("*.json")) - _cache_used:
                stale.unlink()
    finally:
        _cache_dir = previous


def _cache_path(
    task: str, system: str, user: str, as_json: bool, max_tokens: int | None,
    images: list[str] | None = None,
) -> Path:
    parts: list = [task, system, user, as_json, max_tokens]
    if images:  # only vision calls add this, so earlier cache keys stay valid
        parts.append([hashlib.sha256(i.encode()).hexdigest() for i in images])
    key = hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode("utf-8")).hexdigest()
    return _cache_dir / f"{task}-{key[:20]}.json"  # type: ignore[operator]


def model_for(task: str) -> str:
    """The configured model for a task. A partial LLM_TASK_TIERS override keeps the defaults."""
    s = get_settings()
    tier = {**_DEFAULT_TIERS, **s.LLM_TASK_TIERS}.get(task)
    models = {"fast": s.MODEL_FAST, "smart": s.MODEL_SMART, "vision": s.MODEL_VISION}
    if tier not in models:
        raise ValueError(f"Unknown LLM task {task!r}; add it to LLM_TASK_TIERS in app/core/config.py")
    return models[tier]


@lru_cache
def _client(provider: str) -> OpenAI:
    s = get_settings()
    if provider == PRIMARY:
        base_url, api_key, retries = s.LLM_BASE_URL, s.LLM_API_KEY, s.LLM_PRIMARY_MAX_RETRIES
    else:
        base_url, api_key, retries = s.FALLBACK_BASE_URL, s.FALLBACK_API_KEY, s.LLM_MAX_RETRIES
    return OpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=httpx.Timeout(s.LLM_TIMEOUT, connect=s.LLM_CONNECT_TIMEOUT),
        max_retries=retries,
    )


def parse_json_object(content: str | None) -> dict[str, Any]:
    """Parse a model reply into a JSON object, tolerating code fences or stray prose."""
    text = _FENCE.sub("", (content or "").strip())
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Stray prose around it, or a second object after it: take the first complete object.
        start = text.find("{")
        if start == -1:
            raise ValueError("reply contained no JSON object") from None
        try:
            data, _ = json.JSONDecoder().raw_decode(text, start)
        except json.JSONDecodeError:
            raise ValueError("reply contained no valid JSON object") from None
    if not isinstance(data, dict):
        raise ValueError("reply JSON is not an object")
    return data


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    price = get_settings().LLM_PRICES.get(model)
    if not price:
        return None
    return round((prompt_tokens * price[0] + completion_tokens * price[1]) / 1_000_000, 6)


def _record_usage(rec: dict[str, Any]) -> None:
    logger.info(
        "llm task=%s provider=%s model=%s ok=%s tokens=%s+%s cost_usd=%s ms=%s",
        rec["task"], rec["provider"], rec["model"], rec["ok"],
        rec["prompt_tokens"], rec["completion_tokens"], rec["cost_usd"], rec["latency_ms"],
    )
    path = get_settings().LLM_USAGE_LOG
    if not path:
        return
    p = Path(path)
    if not p.is_absolute():
        p = _BACKEND_DIR / p
    # Real wall-clock time on purpose (spend tracking), not the app clock.
    line = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **rec}
    try:
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line) + "\n")
    except OSError:
        logger.warning("could not write LLM usage log %s", p, exc_info=True)


def _complete(
    provider: str, model: str, system: str, user: str, *, task: str, temperature: float,
    as_json: bool, max_tokens: int | None = None, images: list[str] | None = None,
) -> Any:
    rec: dict[str, Any] = {
        "task": task, "provider": provider, "model": model, "ok": False,
        "prompt_tokens": None, "completion_tokens": None, "cost_usd": None, "latency_ms": None,
    }
    started = time.perf_counter()
    try:
        extra: dict[str, Any] = {"response_format": {"type": "json_object"}} if as_json else {}
        if max_tokens:
            extra["max_tokens"] = max_tokens
        raw = _client(provider).chat.completions.with_raw_response.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": _content(user, images)}],
            temperature=temperature,
            **extra,
        )
        resp = raw.parse()
        if resp.usage is not None:
            rec["prompt_tokens"] = resp.usage.prompt_tokens
            rec["completion_tokens"] = resp.usage.completion_tokens
        try:  # LiteLLM reports its own cost per call; trust it over our price table.
            rec["cost_usd"] = float(raw.headers.get("x-litellm-response-cost") or "")
        except ValueError:
            if resp.usage is not None:
                rec["cost_usd"] = _estimate_cost(
                    model, resp.usage.prompt_tokens or 0, resp.usage.completion_tokens or 0
                )
        choice = resp.choices[0]
        content = choice.message.content or ""
        if getattr(choice, "finish_reason", None) == "length" and not as_json:
            # Hit max_tokens (reasoning tokens count too): never show half a sentence.
            raise ValueError("reply cut off at max_tokens")
        if as_json:
            result: Any = parse_json_object(content)
        else:
            result = content.strip()
            if not result:
                raise ValueError("empty reply")
        rec["ok"] = True
        return result
    finally:
        rec["latency_ms"] = round((time.perf_counter() - started) * 1000)
        _record_usage(rec)


def _content(user: str, images: list[str] | None) -> Any:
    """The user message: plain text, or text plus images (data: URLs) for vision calls."""
    if not images:
        return user
    return [{"type": "text", "text": user}, *({"type": "image_url", "image_url": {"url": u}} for u in images)]


def complete_json(
    provider: str, model: str, system: str, user: str, *, task: str, temperature: float = 0.0
) -> dict[str, Any]:
    """One JSON-mode chat call to one provider and model, with usage logging.
    Prefer llm_json(); this is the building block (and what the smoke test calls)."""
    return _complete(provider, model, system, user, task=task, temperature=temperature, as_json=True)


def _route(
    task: str, system: str, user: str, temperature: float, as_json: bool,
    max_tokens: int | None = None, images: list[str] | None = None,
) -> Any:
    if _cache_dir is not None:
        path = _cache_path(task, system, user, as_json, max_tokens, images)
        _cache_used.add(path)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))["result"]
        result = _route_live(task, system, user, temperature, as_json, max_tokens, images)
        path.write_text(json.dumps({"task": task, "result": result}, ensure_ascii=False, indent=1),
                        encoding="utf-8", newline="\n")  # same bytes on every OS
        return result
    return _route_live(task, system, user, temperature, as_json, max_tokens, images)


def _route_live(
    task: str, system: str, user: str, temperature: float, as_json: bool, max_tokens: int | None,
    images: list[str] | None = None,
) -> Any:
    s = get_settings()
    model = model_for(task)  # validates the task name even when only the fallback is set
    last_error: Exception | None = None
    if _primary_ready(s):
        try:
            return _complete(PRIMARY, model, system, user, task=task, temperature=temperature,
                             as_json=as_json, max_tokens=max_tokens, images=images)
        except Exception as exc:  # noqa: BLE001 - any proxy failure falls back
            last_error = exc
            logger.warning("LiteLLM call for %s failed (%s); trying the Groq fallback", task, exc)
    if s.FALLBACK_API_KEY:
        fallback = s.FALLBACK_VISION_MODEL if images else s.FALLBACK_MODEL
        try:
            return _complete(FALLBACK, fallback, system, user, task=task, temperature=temperature,
                             as_json=as_json, max_tokens=max_tokens, images=images)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("Groq fallback for %s failed (%s)", task, exc)
    raise LLMUnavailable(f"no LLM provider could answer task {task!r}") from last_error


def llm_json(task: str, system: str, user: str, *, temperature: float = 0.0) -> dict[str, Any]:
    """JSON-mode completion for `task`: LiteLLM first, the Groq fallback on any error.
    Raises LLMUnavailable if nothing is configured or every provider fails."""
    return _route(task, system, user, temperature, as_json=True)


def llm_text(
    task: str, system: str, user: str, *, temperature: float = 0.0, max_tokens: int | None = None
) -> str:
    """Plain-text completion (same routing, fallback and logging) for prose replies, where a
    JSON wrapper only adds a way to fail (models sometimes answer in prose anyway)."""
    return _route(task, system, user, temperature, as_json=False, max_tokens=max_tokens)


def llm_vision_json(
    task: str, system: str, user: str, images: list[str], *, temperature: float = 0.0
) -> dict[str, Any]:
    """JSON-mode completion that also sends images (data: URLs): report photos and scans.
    Same routing; the Groq fallback uses FALLBACK_VISION_MODEL."""
    return _route(task, system, user, temperature, as_json=True, images=images)


def transcribe(path: str | Path) -> str:
    """Speech to text for visit recaps: Whisper (STT_MODEL) on Groq. Raises LLMUnavailable if
    no Groq key is set. Inside response_cache() the transcript is cached by the audio's hash."""
    s = get_settings()
    data = Path(path).read_bytes()
    cache = None
    if _cache_dir is not None:
        cache = _cache_dir / f"stt-{hashlib.sha256(data).hexdigest()[:20]}.json"
        _cache_used.add(cache)
        if cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))["result"]
    if not s.FALLBACK_API_KEY:
        raise LLMUnavailable("speech-to-text needs FALLBACK_API_KEY (Groq)")
    rec: dict[str, Any] = {"task": "transcribe", "provider": FALLBACK, "model": s.STT_MODEL, "ok": False,
                           "prompt_tokens": None, "completion_tokens": None, "cost_usd": None, "latency_ms": None}
    started = time.perf_counter()
    try:
        res = _client(FALLBACK).audio.transcriptions.create(
            model=s.STT_MODEL, file=(Path(path).name, data), response_format="text", language="en",
        )
        text = (res if isinstance(res, str) else getattr(res, "text", "") or "").strip()
        rec["ok"] = True
    finally:
        rec["latency_ms"] = round((time.perf_counter() - started) * 1000)
        _record_usage(rec)
    if cache is not None:
        cache.write_text(json.dumps({"task": "transcribe", "result": text}, ensure_ascii=False, indent=1),
                         encoding="utf-8", newline="\n")
    return text


def list_models(provider: str = PRIMARY) -> list[str]:
    """Model ids a provider exposes (GET {base_url}/v1/models)."""
    return sorted(m.id for m in _client(provider).models.list())


def describe() -> str:
    """One line for the startup log; never includes secrets."""
    s = get_settings()
    primary = (
        f"LiteLLM fast={s.MODEL_FAST} smart={s.MODEL_SMART}"
        if _primary_ready(s)
        else "LiteLLM not configured"
    )
    fallback = f"Groq fallback {s.FALLBACK_MODEL}" if s.FALLBACK_API_KEY else "no Groq fallback"
    suffix = "" if is_available() else " (offline fallbacks only)"
    return f"LLM: {primary}; {fallback}{suffix}"
