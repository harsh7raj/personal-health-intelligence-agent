"""POST /chat with a stubbed LLM: cited replies, rejected citations/diagnoses, question mode,
red flags (always escalate, no LLM), clarification, history, and the Harsh scenario."""

import json
from datetime import date, datetime, timedelta, timezone

import pytest

import app.services.assistant as assistant
from app.models.clinical import Medication, MedicationEvent
from app.models.records import Entry

CAPTURED: dict = {}


def _auth(client, email: str) -> tuple[dict, int]:
    client.post("/api/auth/register", json={"email": email, "password": "pw123456"})
    r = client.post("/api/auth/login", data={"username": email, "password": "pw123456"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    return h, client.post("/api/patients", json={"name": "Chat"}, headers=h).json()["id"]


def _llm(reply_for):
    """Stub LLM: records the evidence pack, replies with reply_for(pack)."""
    def fake(task, system, user, **_kw):
        CAPTURED["task"], CAPTURED["pack"] = task, json.loads(user)["evidence"]
        return reply_for(CAPTURED["pack"])
    return fake


@pytest.fixture
def llm_on(monkeypatch):
    CAPTURED.clear()
    monkeypatch.setattr(assistant, "is_available", lambda: True)
    return lambda reply_for: monkeypatch.setattr(assistant, "llm_text", _llm(reply_for))


def _say(client, h, pid, text):
    return client.post(f"/api/patients/{pid}/chat", json={"message": text}, headers=h).json()


def test_log_gets_a_cited_reply_and_history_is_kept(client, llm_on):
    llm_on(lambda pack: f"Logged your migraine [{pack['logged_now']['id']}].")
    h, pid = _auth(client, "chat1@x.com")
    r = _say(client, h, pid, "bad migraine today")
    assert r["generated_by"] == "llm" and CAPTURED["task"] == "assistant"
    assert r["logged_entry"]["name"] == "migraine"
    assert [e["id"] for e in r["evidence"]] == [f"E{r['logged_entry']['entry_id']}"]
    history = client.get(f"/api/patients/{pid}/chat", headers=h).json()
    assert [m["role"] for m in history] == ["user", "assistant"]
    assert history[1]["evidence"][0]["kind"] == "entry"


@pytest.mark.parametrize("bad", ["Noted [E999999].", "You have migraines [{logged}]."])
def test_bad_citations_or_diagnoses_fall_back_to_the_facts(client, llm_on, bad):
    llm_on(lambda pack: bad.format(logged=pack["logged_now"]["id"]))
    h, pid = _auth(client, f"chat2{len(bad)}@x.com")
    r = _say(client, h, pid, "bad migraine today")
    assert r["generated_by"] == "fallback"
    assert r["reply"].startswith("Logged: migraine")
    assert "You have" not in r["reply"]


def test_questions_are_answered_from_history_and_not_saved(client, llm_on):
    def reply(pack):
        eps = pack.get("recurrence", [{}])[0].get("prior_episodes", [])
        return "Your migraines: " + ", ".join(f"{e['date']} [{e['id']}]" for e in eps) + "."
    llm_on(reply)
    h, pid = _auth(client, "chat3@x.com")
    _say(client, h, pid, "migraine again")
    _say(client, h, pid, "another migraine")
    r = _say(client, h, pid, "When did my migraines start?")
    assert r["logged_entry"] is None
    assert len(client.get(f"/api/patients/{pid}/entries", headers=h).json()) == 2
    assert CAPTURED["pack"]["message_kind"] == "question"
    assert len(r["evidence"]) == 2 and all(e["kind"] == "entry" for e in r["evidence"])


@pytest.mark.parametrize(
    ("text", "kind"),
    [("chest felt tight climbing stairs again, a bit breathless", "medical"),
     ("I don't want to live anymore", "mental_health")],
)
def test_red_flags_always_escalate_without_the_llm(client, monkeypatch, text, kind):
    monkeypatch.setattr(assistant, "is_available", lambda: True)
    monkeypatch.setattr(assistant, "llm_text", lambda *a, **k: pytest.fail("LLM must not run"))
    h, pid = _auth(client, f"chat4{kind}@x.com")
    r = _say(client, h, pid, text)
    assert r["escalation"]["kind"] == kind and r["generated_by"] == "rules"
    assert ("14416" if kind == "mental_health" else "112") in r["reply"]


def test_clarifying_question_then_answer(client, monkeypatch):
    def parse(text):
        if "Additional info" in text:
            return {"type": "symptom", "name": "rash", "attributes": {}, "complete": True}
        return {"type": "symptom", "name": "rash", "complete": False,
                "clarifying_question": "Where is the rash?"}
    monkeypatch.setattr("app.graph.nodes.intake.parse_entry", parse)
    h, pid = _auth(client, "chat5@x.com")
    r = _say(client, h, pid, "rash")
    assert r["needs_clarification"] and r["reply"] == "Where is the rash?"
    r = _say(client, h, pid, "on my left arm")
    assert not r["needs_clarification"] and r["logged_entry"]["name"] == "rash"


def test_harsh_climax_pack_has_dates_pattern_and_dose_change(client, db, llm_on, monkeypatch):
    llm_on(lambda pack: "Noted [{}].".format(pack["logged_now"]["id"]))
    monkeypatch.setattr(
        "app.graph.nodes.intake.parse_entry",
        lambda text: {"type": "symptom", "name": "shaky", "attributes": {}, "complete": True},
    )
    h, pid = _auth(client, "harsh-chat@x.com")
    med = Medication(patient_id=pid, name="Glimepiride", dose="2 mg", dose_times=["08:00"])
    db.add(med)
    db.flush()
    db.add(MedicationEvent(patient_id=pid, medication_id=med.id, medication_name="Glimepiride",
                           event_type="dose_change", event_date=date.today() - timedelta(days=150),
                           old_dose="1 mg", new_dose="2 mg"))
    for days in (120, 90, 45):
        db.add(Entry(patient_id=pid, type="symptom", raw_text="shaky, skipped lunch",
                     structured={"name": "shakiness", "context_tags": ["skipped_meal"]},
                     occurred_at=datetime.now(timezone.utc) - timedelta(days=days)))
    db.commit()

    _say(client, h, pid, "feeling shaky and sweaty, skipped lunch, meetings all day")
    rec = CAPTURED["pack"]["recurrence"][0]
    assert rec["symptom"] == "shakiness" and len(rec["prior_episodes"]) == 3
    top = rec["shared_factors"][0]
    assert (top["factor"], top["count"]) == ("tag:skipped_meal", 4)  # 3 earlier + today
    assert rec["all_after_medication_change"][0]["new_dose"] == "2 mg"


def test_every_reading_shown_in_the_pack_is_citable(client, db, llm_on):
    def reply(pack):
        s = pack["readings"]["bp_systolic"]["summary"]
        return f"First {s['first']['value']} [{s['first']['id']}], highest {s['highest']['value']} [{s['highest']['id']}]."
    llm_on(reply)
    h, pid = _auth(client, "chat-bp@x.com")
    for i, v in enumerate([118, 150, 131] + [125] * 13):  # older than the last 12 kept in "recent"
        client.post(f"/api/patients/{pid}/vitals", headers=h, json={
            "vital_type": "bp_systolic", "value": v,
            "recorded_at": (datetime.now(timezone.utc) - timedelta(days=60 - i)).isoformat()})
    r = _say(client, h, pid, "How has my blood pressure been?")
    assert r["generated_by"] == "llm" and len(r["evidence"]) == 2


def test_chat_observations_run_after_the_reply(client, llm_on, monkeypatch):
    llm_on(lambda pack: f"Logged [{pack['logged_now']['id']}].")
    import app.services.observations as obs
    monkeypatch.setattr(obs, "is_available", lambda: True)
    monkeypatch.setattr(obs, "llm_json", lambda *a, **k: {"observations": ["Migraine logged twice this week."]})
    h, pid = _auth(client, "chat-obs@x.com")
    r = _say(client, h, pid, "bad migraine today")
    assert r["generated_by"] == "llm"
    texts = [o["text"] for o in client.get(f"/api/patients/{pid}/observations", headers=h).json()]
    assert texts == ["Migraine logged twice this week."]  # written by the background task


def test_follow_ups_can_cite_evidence_from_earlier_turns(client, llm_on):
    first: dict = {}

    def reply(pack):
        if "logged_now" in pack and not first:
            first["id"] = pack["logged_now"]["id"]
            return f"Logged [{first['id']}]."
        return f"Before that, the one on [{first['id']}]."  # an id from the earlier turn
    llm_on(reply)
    h, pid = _auth(client, "chat-follow@x.com")
    _say(client, h, pid, "bad migraine today")
    r = _say(client, h, pid, "and before that?")
    assert r["generated_by"] == "llm" and r["evidence"][0]["id"] == first["id"]
