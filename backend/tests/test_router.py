"""Router: log / question / both. Questions are not saved (holding reply until Phase 2)."""

import pytest

import app.graph.nodes.router as router
from app.graph.nodes.router import QUESTION_HOLDING_REPLY, classify_message, heuristic_kind


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("What did my last thyroid report say?", "question"),
        ("How has my sugar been this month", "question"),
        ("when did the headaches start", "question"),
        ("Should I worry about these readings", "question"),
        ("explain my lipid report", "question"),
        ("headache since morning, about 6/10", "log"),
        ("I have a bad migraine headache", "log"),
        ("Have been feeling dizzy since Monday", "log"),
        ("When I woke up my head was pounding", "log"),
        ("blood pressure 150 over 95", "log"),
        ("skipped lunch and feeling shaky. Is that because of my dose?", "both"),
        ("Is it bad that my BP is 150/95?", "both"),  # a question carrying a reading
    ],
)
def test_heuristic(text, kind):
    assert heuristic_kind(text)[0] == kind


def test_heuristic_extracts_the_asked_part():
    kind, asked = heuristic_kind("Migraine again today. When did these start?")
    assert (kind, asked) == ("both", "When did these start?")


def test_llm_answer_is_used_when_valid_and_ignored_when_not(monkeypatch):
    monkeypatch.setattr(router, "is_available", lambda: True)
    monkeypatch.setattr(
        router, "llm_json", lambda task, system, user, **_kw: {"kind": "both", "question": "ok?"}
    )
    mixed = "Migraine again. Is that normal?"
    assert classify_message(mixed) == ("both", "ok?")
    monkeypatch.setattr(router, "llm_json", lambda *a, **k: {"kind": "chitchat"})
    assert classify_message(mixed) == ("both", "Is that normal?")  # invalid -> heuristic


def test_clear_cut_messages_skip_the_llm(monkeypatch):
    monkeypatch.setattr(router, "is_available", lambda: True)
    monkeypatch.setattr(router, "llm_json", lambda *a, **k: pytest.fail("router LLM not needed"))
    assert classify_message("headache since morning")[0] == "log"
    assert classify_message("What did my report say?")[0] == "question"


def _auth(client, email: str) -> tuple[dict, int]:
    client.post("/api/auth/register", json={"email": email, "password": "pw123456"})
    r = client.post("/api/auth/login", data={"username": email, "password": "pw123456"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    return h, client.post("/api/patients", json={"name": "Router"}, headers=h).json()["id"]


def test_questions_are_not_saved(client):
    h, pid = _auth(client, "router1@x.com")
    r = client.post(
        f"/api/patients/{pid}/intake", json={"raw_text": "What did my last thyroid report say?"}, headers=h
    ).json()
    assert r["status"] == "question"
    assert r["reply"] == QUESTION_HOLDING_REPLY
    assert client.get(f"/api/patients/{pid}/entries", headers=h).json() == []


def test_log_plus_question_is_logged_and_the_question_passed_on(client):
    h, pid = _auth(client, "router2@x.com")
    r = client.post(
        f"/api/patients/{pid}/intake",
        json={"raw_text": "I have a migraine again. When did my headaches start?"},
        headers=h,
    ).json()
    assert r["status"] == "processed"
    assert r["user_question"] == "When did my headaches start?"
    assert len(client.get(f"/api/patients/{pid}/entries", headers=h).json()) == 1


def test_clarification_answers_skip_the_router(client):
    h, pid = _auth(client, "router3@x.com")
    r = client.post(
        f"/api/patients/{pid}/intake/answer",
        json={"raw_text": "vague", "answer": "what do you mean?"},
        headers=h,
    ).json()
    assert r["status"] == "clarification_needed"  # still treated as a log, not a question
