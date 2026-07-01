"""Offline unit tests for report intelligence (Part 2): lab trend reuse, Chroma chunk
building, and the non-diagnostic ai_summary fallback. GROQ is disabled in tests, so the
summary path exercises the deterministic fallback."""

from datetime import date, datetime, timezone

from sqlalchemy import select

from app.models.clinical import VitalReading, VitalSummary
from app.models.patient import Patient
from app.models.records import Report
from app.models.user import User
from app.services.language_guard import is_diagnostic
from app.services.report_extraction import generate_report_summary
from app.services.report_indexing import build_report_chunks
from app.services.vitals_trend import (
    lab_vital_type,
    record_lab_readings_and_recompute,
)

_counter = {"n": 0}


def _make_patient(db) -> int:
    _counter["n"] += 1
    u = User(email=f"rpt{_counter['n']}@x.com", password_hash="x", role="patient")
    db.add(u)
    db.flush()
    p = Patient(user_id=u.id, name="Report Test")
    db.add(p)
    db.flush()
    return p.id


def test_lab_vital_type_slug():
    assert lab_vital_type("LDL Cholesterol") == "lab_ldl_cholesterol"
    assert lab_vital_type("Total Cholesterol") == "lab_total_cholesterol"
    assert lab_vital_type("") == "lab_unknown"


def test_recurring_lab_produces_rising_trend(db):
    """4 lipid panels with rising LDL -> the SAME rolling-average module marks it rising."""
    pid = _make_patient(db)
    for i, (d, ldl) in enumerate(
        [(date(2026, 2, 1), 128), (date(2026, 3, 1), 148),
         (date(2026, 4, 1), 162), (date(2026, 5, 1), 176)]
    ):
        record_lab_readings_and_recompute(
            db,
            pid,
            report_id=i + 1,
            values=[{"test_name": "LDL Cholesterol", "value": str(ldl), "unit": "mg/dL",
                     "reference_range": "<100", "flag": "high"}],
            recorded_at=datetime(d.year, d.month, d.day, tzinfo=timezone.utc),
        )
    summary = db.scalar(
        select(VitalSummary).where(
            VitalSummary.patient_id == pid,
            VitalSummary.vital_type == "lab_ldl_cholesterol",
        )
    )
    assert summary is not None
    assert summary.latest == 176.0
    assert summary.trend == "rising"


def test_lab_readings_idempotent_per_report(db):
    """Re-parsing the same report replaces its readings rather than double-counting."""
    pid = _make_patient(db)
    vals = [{"test_name": "TSH", "value": "3.1", "unit": "mIU/L"}]
    ts = datetime(2026, 3, 1, tzinfo=timezone.utc)
    record_lab_readings_and_recompute(db, pid, report_id=7, values=vals, recorded_at=ts)
    record_lab_readings_and_recompute(db, pid, report_id=7, values=vals, recorded_at=ts)
    rows = db.scalars(
        select(VitalReading).where(
            VitalReading.patient_id == pid, VitalReading.vital_type == "lab_tsh"
        )
    ).all()
    assert len(rows) == 1


def test_non_numeric_lab_skipped(db):
    """Non-numeric results (e.g. 'Negative') can't trend and are not stored as readings."""
    pid = _make_patient(db)
    affected = record_lab_readings_and_recompute(
        db,
        pid,
        report_id=1,
        values=[{"test_name": "Culture", "value": None, "unit": None}],
        recorded_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
    )
    assert affected == []


def _report(**kw) -> Report:
    r = Report(patient_id=1, filename="f.pdf", path="/tmp/f.pdf")
    r.id = kw.get("id", 1)
    r.report_type = kw.get("report_type", "Lipid Panel")
    r.test_date = kw.get("test_date", date(2026, 5, 14))
    r.extracted_values = kw.get("extracted_values", [])
    r.ai_summary = kw.get("ai_summary")
    return r


def test_build_report_chunks_summary_and_values():
    report = _report(
        extracted_values=[
            {"test_name": "LDL Cholesterol", "value": "158", "unit": "mg/dL",
             "reference_range": "<100", "flag": "high"},
            {"test_name": "HDL Cholesterol", "value": "41", "unit": "mg/dL",
             "reference_range": ">40", "flag": "normal"},
        ],
        ai_summary="LDL is elevated.",
    )
    chunks = build_report_chunks(report)
    ids = [c[0] for c in chunks]
    assert "report_1_summary" in ids
    assert "report_1_v0" in ids and "report_1_v1" in ids
    # Every chunk carries the filterable tags.
    for _cid, text, meta in chunks:
        assert meta["report_id"] == 1
        assert meta["report_type"] == "Lipid Panel"
        assert meta["date"] == "2026-05-14"
        assert text
    ldl_chunk = next(c for c in chunks if c[2].get("test_name") == "LDL Cholesterol")
    assert "158" in ldl_chunk[1] and "flagged high" in ldl_chunk[1]


def test_build_report_chunks_non_lab_still_indexes_summary():
    """A discharge summary (no values) still yields one retrievable summary chunk."""
    report = _report(report_type="Discharge Summary", extracted_values=[],
                      ai_summary="Observed overnight, discharged stable.")
    chunks = build_report_chunks(report)
    assert len(chunks) == 1
    assert chunks[0][2]["chunk"] == "summary"
    assert "Discharge Summary" in chunks[0][1]


def test_ai_summary_fallback_is_nondiagnostic():
    """With GROQ off, the deterministic fallback fires and stays non-diagnostic."""
    values = [{"test_name": "LDL Cholesterol", "value": "176", "unit": "mg/dL",
               "reference_range": "<100", "flag": "high"}]
    trends = [{"test_name": "LDL Cholesterol", "trend": "rising", "since": "2026-02-10"}]
    summary = generate_report_summary("Lipid Panel", values, trends)
    assert summary
    assert not is_diagnostic(summary)
    assert "cholesterol" in summary.lower()


def test_ai_summary_none_when_empty():
    assert generate_report_summary("Other", [], []) is None
