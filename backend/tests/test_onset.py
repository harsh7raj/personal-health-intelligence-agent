"""Onset / backdating parser: the user's words -> when it happened (IST in, UTC out)."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.services.onset import resolve_onset

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 3, 18, 10, 0, tzinfo=IST)  # a Wednesday, 10:00 in India


def ist(month: int, day: int, hour: int = 12, minute: int = 0, year: int = 2026) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=IST)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("had a migraine yesterday", ist(3, 17)),
        ("terrible headache last night", ist(3, 17, 22)),
        ("dizzy since Monday", ist(3, 16)),
        ("it started last wednesday", ist(3, 11)),
        ("shaky this morning after skipping breakfast", ist(3, 18, 8)),
        ("nausea 3 days ago", ist(3, 15)),
        ("nausea three days ago", ist(3, 15)),
        ("fever since 2 days", ist(3, 16)),
        ("cough for the past week", ist(3, 11)),
        ("rash 2 days back", ist(3, 16)),
        ("palpitations 2 hours ago", ist(3, 18, 8)),
        ("felt faint the day before yesterday", ist(3, 16)),
        ("swollen ankles on 12 March", ist(3, 12)),
        ("swollen ankles March 12th", ist(3, 12)),
        ("back pain from dec 25", ist(12, 25, year=2025)),
    ],
)
def test_relative_and_explicit_phrases(text, expected):
    assert resolve_onset(text, now=NOW) == expected


def test_no_time_phrase_means_now():
    assert resolve_onset("headache right now, moderate", now=NOW) is None


def test_result_is_utc():
    assert resolve_onset("yesterday", now=NOW).tzinfo == timezone.utc


def test_never_in_the_future():
    assert resolve_onset("tired this evening", now=NOW) == NOW  # said at 10:00
    assert resolve_onset("since wednesday", now=NOW) == NOW  # today, midday not reached yet


def test_far_past_is_history_not_an_episode_date():
    assert resolve_onset("diabetic since 2019", now=NOW) is None
    assert resolve_onset("knee pain 400 days ago", now=NOW) is None


def test_llm_phrase_wins_over_raw_text():
    assert resolve_onset("felt awful last night", phrase="yesterday morning", now=NOW) == ist(3, 17, 8)


def test_earliest_phrase_in_the_text_wins():
    assert resolve_onset("headache yesterday, and 3 days ago some nausea", now=NOW) == ist(3, 17)


def test_yesterday_is_the_indian_calendar_day():
    # 20:00 UTC on 18 Mar is already 01:30 on 19 Mar in India, so "yesterday" is the 18th.
    late = datetime(2026, 3, 18, 20, 0, tzinfo=timezone.utc)
    assert resolve_onset("yesterday", now=late) == ist(3, 18)
