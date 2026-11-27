from datetime import datetime

from app.services.alerts import check_vital_alert
from app.services.language_guard import filter_observations, is_diagnostic
from app.services.state_assembler import dedupe_observations
from app.services.vitals_trend import _trend, extract_readings


def test_alert_thresholds():
    assert check_vital_alert("bp_systolic", 145)[0] == "high_bp"
    assert check_vital_alert("bp_systolic", 185)[0] == "critical_bp"
    assert check_vital_alert("bp_systolic", 130) is None
    assert check_vital_alert("bp_diastolic", 95)[0] == "high_bp"
    assert check_vital_alert("spo2", 90)[0] == "low_spo2"
    assert check_vital_alert("heart_rate", 110)[0] == "tachycardia"
    assert check_vital_alert("blood_glucose", 210)[0] == "high_glucose"
    assert check_vital_alert("blood_glucose", 60)[0] == "low_glucose"


def test_bp_extraction_recovers_dropped_diastolic():
    entry = {
        "type": "vital",
        "name": "blood pressure",
        "raw_text": "bp 160 over 100 this morning",
        "structured": {"name": "blood pressure", "value": 160, "attributes": {}},
    }
    readings = {vt: v for vt, v, _ in extract_readings(entry)}
    assert readings["bp_systolic"] == 160
    assert readings["bp_diastolic"] == 100


def test_trend_classification():
    assert _trend(0.10) == "rising"
    assert _trend(-0.10) == "falling"
    assert _trend(0.0) == "stable"
    assert _trend(None) == "stable"


def test_language_guard_flags_diagnostic():
    assert is_diagnostic("You have hypertension")
    assert is_diagnostic("This is caused by stress")
    assert is_diagnostic("You should take ibuprofen")
    assert is_diagnostic("diagnosed with migraine")
    assert not is_diagnostic("Headache episodes increased to 3 in two months")
    assert not is_diagnostic("Blood pressure has been rising over six months")


def test_filter_observations_drops_diagnostic():
    kept = filter_observations(["You have diabetes", "Blood pressure has been rising"])
    assert kept == ["Blood pressure has been rising"]


class _Obs:
    def __init__(self, text: str):
        self.text = text


def test_dedupe_observations_collapses_near_duplicates():
    obs = [
        _Obs("Headache episodes have increased to 3 with an increasing trend"),
        _Obs("Headache episodes increased to 3, trend increasing"),
        _Obs("Blood pressure has been rising over the past six months"),
    ]
    kept = dedupe_observations(obs, limit=5)
    assert len(kept) == 2


def test_pdf_date_format_is_portable():
    from app.services.pdf_report import _fmt

    assert _fmt(datetime(2026, 3, 5)) == "Mar 5, 2026"
    assert _fmt(datetime(2026, 11, 27)) == "Nov 27, 2026"


def test_llm_settings_defaults_and_v1_groq_key_alias(monkeypatch):
    from app.core.config import Settings

    for var in ("FALLBACK_API_KEY", "GROQ_API_KEY", "LLM_TASK_TIERS"):
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=None)
    assert s.FALLBACK_MODEL == "openai/gpt-oss-120b"
    assert s.MED_AI_FLAGS_ENABLED is False
    assert s.LLM_TASK_TIERS["router"] == "fast" and s.LLM_TASK_TIERS["story"] == "smart"

    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")  # a v1 .env keeps working as the fallback
    assert Settings(_env_file=None).FALLBACK_API_KEY == "gsk-test"
    monkeypatch.setenv("LLM_TASK_TIERS", '{"story": "fast"}')
    assert Settings(_env_file=None).LLM_TASK_TIERS == {"story": "fast"}


def test_story_fallback_never_prints_none():
    from app.schemas.health_state import PatientHealthState, ProblemView
    from app.services.story import _fallback_story

    state = PatientHealthState(
        patient_id=1,
        active_problems=[
            ProblemView(name="vitamin D deficiency", frequency=None, trend="stable", status="managed"),
            ProblemView(name="migraine", frequency="12 episodes", trend="increasing", status="active"),
            ProblemView(name="fatigue", frequency=None, trend=None, status="active"),
        ],
    )
    story = _fallback_story(state)
    assert "None" not in story
    assert "vitamin D deficiency (stable)" in story
    assert "migraine (12 episodes, increasing)" in story
    assert "fatigue." in story
