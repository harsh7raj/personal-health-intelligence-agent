"""Medication records: prescriber per medicine, and the change history."""


def _auth(client, email: str) -> tuple[dict, int]:
    client.post("/api/auth/register", json={"email": email, "password": "pw123456"})
    r = client.post("/api/auth/login", data={"username": email, "password": "pw123456"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    pid = client.post("/api/patients", json={"name": "Meds"}, headers=h).json()["id"]
    return h, pid


def test_prescriber_is_saved_and_editable(client):
    h, pid = _auth(client, "rx@x.com")
    med = client.post(
        f"/api/patients/{pid}/medications",
        json={"name": "Glimepiride", "dose": "1 mg", "prescriber": "Dr. Rao",
              "prescriber_specialty": "Endocrinology"},
        headers=h,
    ).json()
    assert (med["prescriber"], med["prescriber_specialty"]) == ("Dr. Rao", "Endocrinology")

    r = client.put(
        f"/api/patients/{pid}/medications/{med['id']}", json={"prescriber": "Dr. Iyer"}, headers=h
    )
    assert r.json()["prescriber"] == "Dr. Iyer"
    assert r.json()["prescriber_specialty"] == "Endocrinology"  # untouched fields stay


def test_history_records_start_dose_change_stop_and_restart(client):
    h, pid = _auth(client, "history@x.com")
    base = f"/api/patients/{pid}/medications"
    med = client.post(
        base,
        json={"name": "Glimepiride", "dose": "1 mg", "started_on": "2026-01-10",
              "prescriber": "Dr. Rao"},
        headers=h,
    ).json()
    # Raised months ago, entered now: changed_on dates the event correctly.
    r = client.put(f"{base}/{med['id']}", json={"dose": "2 mg", "changed_on": "2026-06-20"}, headers=h)
    assert r.json()["dose"] == "2 mg"  # the medicine row holds the current state only
    client.put(f"{base}/{med['id']}", json={"active": False, "changed_on": "2026-11-01"}, headers=h)
    client.put(f"{base}/{med['id']}", json={"active": True, "changed_on": "2026-11-15"}, headers=h)
    client.put(f"{base}/{med['id']}", json={"frequency": "once daily"}, headers=h)  # no event

    events = client.get(f"{base}/events", headers=h).json()
    assert [(e["event_type"], e["event_date"], e["old_dose"], e["new_dose"]) for e in events] == [
        ("start", "2026-11-15", None, "2 mg"),
        ("stop", "2026-11-01", "2 mg", None),
        ("dose_change", "2026-06-20", "1 mg", "2 mg"),
        ("start", "2026-01-10", None, "1 mg"),
    ]
    assert {e["prescriber"] for e in events} == {"Dr. Rao"}
    assert {e["source"] for e in events} == {"manual"}


def test_history_filters_and_delete_removes_a_mistaken_entry(client):
    h, pid = _auth(client, "history2@x.com")
    base = f"/api/patients/{pid}/medications"
    a = client.post(base, json={"name": "Amlodipine", "dose": "5 mg"}, headers=h).json()
    b = client.post(base, json={"name": "Atorvastatin", "dose": "10 mg"}, headers=h).json()

    only_a = client.get(f"{base}/events?medication_id={a['id']}", headers=h).json()
    assert [e["medication_name"] for e in only_a] == ["Amlodipine"]
    assert len(client.get(f"{base}/events?days=30", headers=h).json()) == 2

    client.delete(f"{base}/{b['id']}", headers=h)
    assert [e["medication_name"] for e in client.get(f"{base}/events", headers=h).json()] == [
        "Amlodipine"
    ]
