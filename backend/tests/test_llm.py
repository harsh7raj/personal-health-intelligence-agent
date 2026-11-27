"""app/core/llm.py: task routing, LiteLLM -> Groq fallback, JSON parsing and usage
logging. Everything runs against fake clients; no network."""

import json
from types import SimpleNamespace

import pytest

import app.core.llm as llm
from app.core.config import get_settings


class _Raw:
    """Mimics openai's with_raw_response result: .headers plus .parse()."""

    def __init__(self, content: str, usage=(10, 5), headers=None):
        self._content, self._usage, self.headers = content, usage, headers or {}

    def parse(self):
        usage = (
            SimpleNamespace(prompt_tokens=self._usage[0], completion_tokens=self._usage[1])
            if self._usage
            else None
        )
        message = SimpleNamespace(content=self._content)
        return SimpleNamespace(usage=usage, choices=[SimpleNamespace(message=message)])


class _FakeClient:
    def __init__(self, reply: _Raw | None = None, error: Exception | None = None):
        self.calls: list[dict] = []

        def create(**kw):
            self.calls.append(kw)
            if error is not None:
                raise error
            return reply

        self.chat = SimpleNamespace(
            completions=SimpleNamespace(with_raw_response=SimpleNamespace(create=create))
        )


@pytest.fixture
def cfg(monkeypatch, tmp_path):
    s = get_settings()
    values = {
        "LLM_BASE_URL": "http://proxy.test",
        "LLM_API_KEY": "proxy-key",
        "FALLBACK_API_KEY": "groq-key",
        "MODEL_FAST": "fast-model",
        "MODEL_SMART": "smart-model",
        "LLM_USAGE_LOG": str(tmp_path / "usage.jsonl"),
    }
    for key, value in values.items():
        monkeypatch.setattr(s, key, value)
    return s


def _use(monkeypatch, primary: _FakeClient, fallback: _FakeClient) -> None:
    clients = {llm.PRIMARY: primary, llm.FALLBACK: fallback}
    monkeypatch.setattr(llm, "_client", lambda provider: clients[provider])


def test_each_task_uses_its_configured_tier(cfg, monkeypatch):
    primary = _FakeClient(_Raw('{"a": 1}'))
    _use(monkeypatch, primary, _FakeClient(error=AssertionError("fallback not expected")))

    assert llm.llm_json("intake", "sys", "user") == {"a": 1}
    assert llm.llm_json("story", "sys", "user") == {"a": 1}
    assert [c["model"] for c in primary.calls] == ["fast-model", "smart-model"]
    assert primary.calls[0]["response_format"] == {"type": "json_object"}


def test_unknown_task_is_rejected(cfg):
    with pytest.raises(ValueError):
        llm.llm_json("not-a-task", "sys", "user")


def test_partial_tier_override_keeps_the_defaults(cfg, monkeypatch):
    monkeypatch.setattr(cfg, "LLM_TASK_TIERS", {"story": "fast"})
    assert llm.model_for("story") == "fast-model"
    assert llm.model_for("observations") == "smart-model"


def test_any_proxy_error_falls_back_to_groq(cfg, monkeypatch):
    fallback = _FakeClient(_Raw('{"via": "groq"}'))
    _use(monkeypatch, _FakeClient(error=RuntimeError("proxy down")), fallback)

    assert llm.llm_json("story", "sys", "user") == {"via": "groq"}
    assert fallback.calls[0]["model"] == cfg.FALLBACK_MODEL


def test_unparseable_proxy_reply_also_falls_back(cfg, monkeypatch):
    _use(monkeypatch, _FakeClient(_Raw("sorry, no JSON today")), _FakeClient(_Raw('{"ok": 1}')))
    assert llm.llm_json("intake", "sys", "user") == {"ok": 1}


def test_unconfigured_proxy_goes_straight_to_groq(cfg, monkeypatch):
    monkeypatch.setattr(cfg, "LLM_API_KEY", "")
    primary = _FakeClient(error=AssertionError("proxy must not be called"))
    _use(monkeypatch, primary, _FakeClient(_Raw('{"ok": 1}')))

    assert llm.llm_json("intake", "sys", "user") == {"ok": 1}
    assert primary.calls == []


def test_raises_when_every_provider_fails_or_none_is_set(cfg, monkeypatch):
    _use(monkeypatch, _FakeClient(error=RuntimeError("a")), _FakeClient(error=RuntimeError("b")))
    with pytest.raises(llm.LLMUnavailable):
        llm.llm_json("intake", "sys", "user")

    monkeypatch.setattr(cfg, "LLM_API_KEY", "")
    monkeypatch.setattr(cfg, "FALLBACK_API_KEY", "")
    assert llm.is_available() is False
    with pytest.raises(llm.LLMUnavailable):
        llm.llm_json("intake", "sys", "user")


def test_json_in_code_fences_or_prose_is_parsed():
    assert llm.parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert llm.parse_json_object('Sure! {"a": 2} Hope that helps.') == {"a": 2}
    with pytest.raises(ValueError):
        llm.parse_json_object("[1, 2]")
    with pytest.raises(ValueError):
        llm.parse_json_object("no json here")


def test_usage_log_has_tokens_and_cost_but_never_prompt_text(cfg, monkeypatch):
    monkeypatch.setattr(cfg, "LLM_PRICES", {"smart-model": [2.0, 10.0]})
    _use(monkeypatch, _FakeClient(_Raw('{"a": 1}', usage=(1000, 200))), _FakeClient())

    llm.llm_json("story", "sys", "PRIVATE health text")

    text = (open(cfg.LLM_USAGE_LOG, encoding="utf-8").read())
    assert "PRIVATE" not in text
    rec = json.loads(text.splitlines()[-1])
    assert rec["task"] == "story" and rec["provider"] == llm.PRIMARY and rec["ok"] is True
    assert (rec["prompt_tokens"], rec["completion_tokens"]) == (1000, 200)
    assert rec["cost_usd"] == pytest.approx(0.004)  # (1000*2 + 200*10) / 1e6


def test_litellm_cost_header_wins_over_the_price_table(cfg, monkeypatch):
    reply = _Raw('{"a": 1}', headers={"x-litellm-response-cost": "0.0123"})
    _use(monkeypatch, _FakeClient(reply), _FakeClient())

    llm.llm_json("intake", "sys", "user")
    rec = json.loads(open(cfg.LLM_USAGE_LOG, encoding="utf-8").read().splitlines()[-1])
    assert rec["cost_usd"] == pytest.approx(0.0123)


def test_real_clients_are_blocked_in_tests(cfg):
    with pytest.raises(RuntimeError, match="must not call a real LLM"):
        llm._client(llm.PRIMARY)


def test_intake_uses_the_llm_and_degrades_when_it_fails(monkeypatch):
    import app.graph.nodes.intake as intake

    monkeypatch.setattr(intake, "is_available", lambda: True)
    monkeypatch.setattr(
        intake, "llm_json", lambda task, system, user, **_kw: {"type": "symptom", "name": "headache"}
    )
    fact = intake.parse_entry("bad headache")
    assert fact["name"] == "headache" and fact["complete"] is True

    def boom(*_a, **_kw):
        raise llm.LLMUnavailable("down")

    monkeypatch.setattr(intake, "llm_json", boom)
    assert intake.parse_entry("bad headache")["type"] == "note"  # deterministic fallback


def test_llm_text_returns_prose_and_falls_back_on_empty(cfg, monkeypatch):
    primary = _FakeClient(_Raw("Your readings rose [V1]."))
    _use(monkeypatch, primary, _FakeClient(error=AssertionError("fallback not expected")))
    assert llm.llm_text("assistant", "sys", "user") == "Your readings rose [V1]."
    assert "response_format" not in primary.calls[0]  # plain text, no JSON mode

    _use(monkeypatch, _FakeClient(_Raw("   ")), _FakeClient(_Raw("From Groq.")))
    assert llm.llm_text("assistant", "sys", "user") == "From Groq."


def test_response_cache_replays_without_calling_a_model(cfg, monkeypatch, tmp_path):
    primary = _FakeClient(_Raw('{"a": 1}'))
    _use(monkeypatch, primary, _FakeClient(error=AssertionError("no fallback")))
    with llm.response_cache(tmp_path / "cache"):
        assert llm.llm_json("intake", "sys", "user") == {"a": 1}  # miss: calls and stores
        assert llm.llm_json("intake", "sys", "user") == {"a": 1}  # hit: no second call
        assert llm.llm_text("assistant", "sys", "other") == '{"a": 1}'
    assert len(primary.calls) == 2
    assert len(list((tmp_path / "cache").glob("*.json"))) == 2

    # Offline (no keys) the cache still answers, and is_available() says so.
    monkeypatch.setattr(cfg, "LLM_API_KEY", "")
    monkeypatch.setattr(cfg, "FALLBACK_API_KEY", "")
    with llm.response_cache(tmp_path / "cache"):
        assert llm.is_available() is True
        assert llm.llm_json("intake", "sys", "user") == {"a": 1}
    assert llm.is_available() is False
