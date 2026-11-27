"""Demo generator: deterministic timeline that plants Harsh's pattern, and readable lab PDFs."""

from datetime import date, timedelta

from app.core import clock
from app.services.report_extraction import extract_text_from_file
from scripts.demo.generate import build_timeline, load_script, make_lab_pdf

TODAY = date(2026, 11, 27)


def test_timeline_is_deterministic_and_sorted():
    script = load_script("harsh")
    a, b = build_timeline(script, TODAY), build_timeline(script, TODAY)
    assert [(e.at, e.kind, e.data) for e in a] == [(e.at, e.kind, e.data) for e in b]
    assert [e.at for e in a] == sorted(e.at for e in a)
    first_day = TODAY - timedelta(days=script["history_days"])
    assert all(clock.to_local(e.at).date() >= first_day for e in a)


def test_every_episode_day_has_the_morning_dose_and_the_dose_change_comes_first():
    script = load_script("harsh")
    timeline = build_timeline(script, TODAY)
    doses = {(e.data["date"], e.data["medicine"], e.data["time"]) for e in timeline if e.kind == "dose"}
    change = next(e for e in timeline if e.kind == "med_change")
    for ep in script["episodes"]:
        day = (TODAY - timedelta(days=ep["days_ago"])).isoformat()
        assert (day, "Glimepiride", "08:00") in doses
        assert clock.to_local(change.at).date().isoformat() < day  # all episodes after the increase
    lows = [e.data["value"] for e in timeline if e.kind == "reading" and e.data["value"] < 70]
    assert sorted(lows) == [62, 66]


def test_lab_pdf_is_a_readable_text_pdf(tmp_path):
    script = load_script("harsh")
    pdf = make_lab_pdf(tmp_path / "r.pdf", script, script["reports"][0], TODAY)
    text = extract_text_from_file(pdf)
    assert "HbA1c" in text and "8.4" in text and "Harsh Iyer" in text
