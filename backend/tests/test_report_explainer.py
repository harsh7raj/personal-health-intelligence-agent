"""Report explainer (D34): code-built rows and pack, cited explanation, critical first,
report-pinned follow-ups, doctor questions, and the API around them. LLM always stubbed."""

import json
from datetime import date, datetime, time, timezone

import pytest

import app.services.assistant as assistant
import app.services.report_explainer as rexp
from app.models.records import Report
from app.services import lab_values
from app.services.vitals_trend import record_lab_readings_and_recompute


def _auth(client, email):
    client.post("/api/auth/register", json={"email": email, "password": "pw123456"})
    r = client.post("/api/auth/login", data={"username": email, "password": "pw123456"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    return h, client.post("/api/patients", json={"name": "Rex"}, headers=h).json()["id"]


def _report(db, pid, day: date, values: list[dict], rtype="Diabetes Panel") -> Report:
    vals = lab_values.enrich(values)
    rep = Report(patient_id=pid, filename=f"r{day}.pdf", path="x", status="parsed", report_type=rtype,
                 test_date=day, extracted_values=vals, extracted_text="HbA1c ...")
    db.add(rep)
    db.flush()
    record_lab_readings_and_recompute(db, pid, rep.id, vals, datetime.combine(day, time.min, tzinfo=timezone.utc))
    db.commit()
    return rep


def _hba1c(v, glucose="128"):
    return [{"test_name": "HbA1c (Glycated haemoglobin)", "value": v, "unit": "%", "reference_range": "4.0 - 5.6",
             "flag": "unknown"},
            {"test_name": "Fasting plasma glucose", "value": glucose, "unit": "mg/dL", "reference_range": "70 - 100",
             "flag": "unknown"}]


@pytest.fixture
def two_reports(client, db):
    h, pid = _auth(client, "rex@x.com")
    first = _report(db, pid, date(2026, 7, 1), _hba1c("7.6", "140"))
    second = _report(db, pid, date(2026, 10, 14), _hba1c("6.9", "128"))
    return h, pid, first, second


def test_rows_compare_against_the_range_and_the_previous_report(db, two_reports):
    _h, pid, first, second = two_reports
    rows = rexp.value_rows(db, pid, second)
    hba1c = rows[0]
    assert hba1c["test_key"] == "hba1c" and hba1c["flag"] == "high"
    assert hba1c["outside_by"] == {"direction": "above", "amount": 1.3, "percent": 23.2}
    assert hba1c["previous"]["value"] == 7.6 and hba1c["previous"]["date"] == "2026-07-01"
    assert hba1c["previous"]["id"].startswith("V")
    assert hba1c["change"] == {"amount": -0.7, "percent": -9.2, "direction": "down"}
    assert hba1c["glossary_id"].startswith("G")
    # The first report has nothing earlier to compare with.
    assert rexp.value_rows(db, pid, first)[0]["previous"] is None


def test_explanation_cites_the_pack_and_bad_replies_fall_back(db, two_reports, monkeypatch):
    _h, pid, _first, second = two_reports
    pack, items = rexp.build_report_pack(db, pid, second)
    v = pack["report"]["values"][0]
    good = (f"Your HbA1c [{pack['report']['id']}] is {v['outside_by']['amount']} above the printed range, "
            f"down from [{v['previous']['id']}]. HbA1c measures average sugar [{v['glossary_id']}].")
    monkeypatch.setattr(rexp, "is_available", lambda: True)
    monkeypatch.setattr(rexp, "llm_text", lambda *a, **k: good)
    out = rexp.explain(db, pid, second)
    assert out["generated_by"] == "llm" and out["reply"] == good
    assert {e["kind"] for e in out["evidence"]} == {"report", "lab", "glossary"}

    for bad in ("Your HbA1c is fine [R999999].", "You have diabetes, see [%s]." % pack["report"]["id"]):
        monkeypatch.setattr(rexp, "llm_text", lambda *a, _b=bad, **k: _b)
        out = rexp.explain(db, pid, second)
        assert out["generated_by"] == "fallback"
        assert "1.3 above the printed range" in out["reply"] and "went down by 0.7" in out["reply"]


def test_a_critical_value_leads_in_codes_own_words(client, db, monkeypatch):
    _h, pid = _auth(client, "crit@x.com")
    rep = _report(db, pid, date(2026, 11, 20), [
        {"test_name": "Potassium", "value": "6.8", "unit": "mmol/L", "reference_range": "3.5 - 5.1", "flag": "high"}],
        rtype="Kidney Function")
    monkeypatch.setattr(rexp, "is_available", lambda: True)
    monkeypatch.setattr(rexp, "llm_text", lambda *a, **k: f"Potassium is above the range [R{rep.id}].")
    out = rexp.explain(db, pid, rep)
    assert out["reply"].startswith("Potassium is 6.8 mmol/L, beyond the level")
    assert "contact your doctor today" in out["reply"] and out["critical"]


def test_follow_ups_get_the_report_and_the_glossary(db, two_reports):
    _h, pid, _first, second = two_reports
    pack, items = assistant.build_pack(db, pid, message="is this bad?", kind="question", new_entry=None,
                                       context_bundle=None, focus={"type": "report", "id": second.id})
    fr = pack["focused_report"]
    assert fr["report"]["id"] == f"R{second.id}" and fr["glossary"][0]["name"] == "HbA1c"
    assert fr["report"]["id"] in items and fr["glossary"][0]["id"] in items
    pack, items = assistant.build_pack(db, pid, message="What is TSH?", kind="question", new_entry=None,
                                       context_bundle=None)
    assert [g["name"] for g in pack["glossary"]] == ["TSH"] and pack["glossary"][0]["id"] in items
    assert "focused_report" not in pack
    assert "never give a good/bad verdict" in assistant.SYSTEM


def test_api_detail_explain_questions_and_thread(client, two_reports, monkeypatch):
    h, pid, _first, second = two_reports
    base = f"/api/patients/{pid}/reports/{second.id}"
    detail = client.get(base, headers=h).json()
    assert detail["values"][0]["previous"]["value"] == 7.6 and detail["critical"] == []
    assert client.get(f"/api/patients/{pid}/reports", headers=h).json()[0]["critical_count"] == 0

    calls = []
    monkeypatch.setattr(rexp, "is_available", lambda: True)
    monkeypatch.setattr(rexp, "llm_text", lambda *a, **k: calls.append(1) or f"Your report [R{second.id}].")
    first = client.post(f"{base}/explain", headers=h).json()
    again = client.post(f"{base}/explain", headers=h).json()
    assert first["id"] == again["id"] and len(calls) == 1  # reopening doesn't call the model again
    assert first["meta"]["kind"] == "report_explainer" and first["evidence"][0]["id"] == f"R{second.id}"
    client.post(f"{base}/explain?regenerate=true", headers=h)
    assert len(calls) == 2

    monkeypatch.setattr(rexp, "llm_json", lambda *a, **k: {"questions": [
        "Should my HbA1c be rechecked?", "You have diabetes, right?"]})
    q = client.post(f"{base}/questions", headers=h).json()
    assert q == {"questions": ["Should my HbA1c be rechecked?"], "generated_by": "llm"}  # guard drops one

    # A follow-up pinned to the report lands in that report's thread only.
    monkeypatch.setattr(assistant, "is_available", lambda: False)
    client.post(f"/api/patients/{pid}/chat", json={"message": "is this bad?", "focus": {"type": "report",
                                                                                         "id": second.id}}, headers=h)
    client.post(f"/api/patients/{pid}/chat", json={"message": "how is my bp?"}, headers=h)
    thread = client.get(f"/api/patients/{pid}/chat?report_id={second.id}", headers=h).json()
    assert [m["content"] for m in thread if m["role"] == "user"] == ["is this bad?"]
    assert all(m["meta"]["report_id"] == second.id for m in thread)
    assert len(client.get(f"/api/patients/{pid}/chat", headers=h).json()) == len(thread) + 2


def test_unparsed_report_cannot_be_explained(client, db):
    h, pid = _auth(client, "unparsed@x.com")
    rep = Report(patient_id=pid, filename="a.pdf", path="x", status="parsing")
    db.add(rep)
    db.commit()
    assert client.post(f"/api/patients/{pid}/reports/{rep.id}/explain", headers=h).status_code == 409
    assert json.loads(json.dumps(rexp.glossary_item("tsh")))["url"].startswith("https://medlineplus.gov/")
