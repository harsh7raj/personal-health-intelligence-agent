"""Context tags at intake: fixed vocabulary, keyword rules, and what gets stored."""

import pytest

from app.services.context_tags import CONTEXT_TAGS, keyword_tags, merge_tags


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("feeling shaky and sweaty, skipped lunch, meetings all day", {"skipped_meal"}),
        ("didn't eat breakfast before my walk", {"skipped_meal"}),
        ("lunch was late today, felt dizzy", {"delayed_meal"}),
        ("slept badly and woke up with a headache", {"poor_sleep"}),
        ("couldn't sleep, deadline tomorrow", {"poor_sleep", "stress"}),
        ("forgot to take my morning dose", {"missed_dose"}),
        ("had a few drinks at a wedding last night", {"alcohol"}),
        ("chest felt tight climbing stairs", {"exercise"}),
        ("went for a run then felt faint", {"exercise"}),
        ("jet lag after the flight from Delhi", {"travel"}),
    ],
)
def test_keyword_rules_find_stated_circumstances(text, expected):
    assert keyword_tags(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "running nose and sore throat",  # Indian English for a runny nose, not exercise
        "blood pressure 150 over 95",  # "pressure" is not stress
        "should drink more water",  # not alcohol
        "ran out of my BP tablets yesterday",  # not exercise; not a missed dose either
        "fasting sugar 98",  # a test type, not a skipped meal
        "headache, moderate",
    ],
)
def test_no_false_positives_on_common_phrasing(text):
    assert keyword_tags(text) == set()


def test_llm_tags_are_vocabulary_checked_and_merged():
    tags = merge_tags(["stress", "dehydration", 7, "skipped_meal"], "slept badly")
    assert tags == ["poor_sleep", "skipped_meal", "stress"]  # off-vocabulary dropped
    assert merge_tags(None, "skipped lunch") == ["skipped_meal"]
    assert set(merge_tags(list(CONTEXT_TAGS), "")) == set(CONTEXT_TAGS)


def test_intake_stores_context_tags(client):
    client.post("/api/auth/register", json={"email": "tags@x.com", "password": "pw123456"})
    tok = client.post("/api/auth/login", data={"username": "tags@x.com", "password": "pw123456"})
    h = {"Authorization": f"Bearer {tok.json()['access_token']}"}
    pid = client.post("/api/patients", json={"name": "Tags"}, headers=h).json()["id"]

    r = client.post(
        f"/api/patients/{pid}/intake",
        json={"raw_text": "headache after I skipped lunch and slept badly"},
        headers=h,
    )
    assert r.json()["new_entry"]["structured"]["context_tags"] == ["poor_sleep", "skipped_meal"]
    stored = client.get(f"/api/patients/{pid}/entries", headers=h).json()[0]
    assert stored["structured"]["context_tags"] == ["poor_sleep", "skipped_meal"]
