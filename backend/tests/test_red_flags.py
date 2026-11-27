"""Red-flag rules: every listed situation escalates; ordinary logs don't."""

import pytest

from app.services.red_flags import check


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("chest felt tight climbing stairs again, a bit breathless", "chest pain or tightness on exertion"),
        ("pain in my chest when I walk fast", "chest pain or tightness on exertion"),
        ("I fainted in the kitchen this morning", "fainting"),
        ("passed out for a few seconds", "fainting"),
        ("my left side feels weak and numb", "one-sided weakness, face droop or slurred speech"),
        ("his face is drooping on one side", "one-sided weakness, face droop or slurred speech"),
        ("my speech is slurred", "one-sided weakness, face droop or slurred speech"),
        ("I can't breathe properly even sitting down", "severe breathlessness"),
        ("sugar 48 and feeling odd", "blood glucose below 54 mg/dL"),
        ("shaky and sweaty and a bit confused", "low-sugar symptoms with confusion"),
        ("bp 182/96 this morning", "blood pressure at or above 180/120"),
        ("BP 150 over 122", "blood pressure at or above 180/120"),
        ("spo2 89 on the oximeter", "oxygen saturation below 92%"),
    ],
)
def test_red_flags_escalate(text, reason):
    esc = check(text)
    assert esc is not None and esc["kind"] == "medical" and esc["call"] == "112"
    assert reason in esc["reasons"]


def test_readings_from_the_parser_count_too():
    assert check("logging my reading", [("blood_glucose", 50.0)])["reasons"] == [
        "blood glucose below 54 mg/dL"
    ]


@pytest.mark.parametrize("text", ["I want to die", "thinking about ending my life", "I keep wanting to hurt myself"])
def test_self_harm_goes_to_the_mental_health_line(text):
    esc = check(text)
    assert esc["kind"] == "mental_health" and esc["call"] == "14416"


@pytest.mark.parametrize(
    "text",
    [
        "climbing stairs was easy today, chest feels fine",
        "bp 150/95",
        "sugar 98 fasting",
        "sweaty after the gym, felt great",
        "headache since morning, about 6/10",
        "shaky and sweaty, skipped lunch, meetings all day",  # no confusion: not a red flag
    ],
)
def test_ordinary_logs_do_not_escalate(text):
    assert check(text) is None
