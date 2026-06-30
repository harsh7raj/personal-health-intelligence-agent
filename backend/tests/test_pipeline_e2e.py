def _auth(client, email: str) -> dict:
    client.post("/api/auth/register", json={"email": email, "password": "pw123456"})
    r = client.post("/api/auth/login", data={"username": email, "password": "pw123456"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_full_pipeline(client):
    h = _auth(client, "e2e@x.com")
    pid = client.post("/api/patients", json={"name": "E2E"}, headers=h).json()["id"]
    client.put(f"/api/patients/{pid}/background", json={"conditions": ["Hypertension"]}, headers=h)

    # symptom intake -> active problem
    r = client.post(f"/api/patients/{pid}/intake", json={"raw_text": "I have a bad migraine headache"}, headers=h)
    assert r.json()["status"] == "processed"
    # vital intake -> readings + summary + alert
    r = client.post(f"/api/patients/{pid}/intake", json={"raw_text": "blood pressure 150 over 95"}, headers=h)
    assert r.json()["status"] == "processed"

    snap = client.get(f"/api/patients/{pid}/snapshot", headers=h).json()
    assert "migraine" in [p["name"] for p in snap["active_problems"]]

    vs = client.get(f"/api/patients/{pid}/vitals/summary", headers=h).json()
    assert any(s["vital_type"] == "bp_systolic" for s in vs)

    alerts = client.get(f"/api/patients/{pid}/alerts", headers=h).json()
    assert any(a["kind"] == "high_bp" for a in alerts)

    # story falls back (no key in tests) but still 200
    story = client.get(f"/api/patients/{pid}/story", headers=h).json()
    assert story["generated_by"] == "fallback"
    assert story["story"]

    # doctor token -> shared works -> revoke -> 403
    tok = client.post(f"/api/patients/{pid}/doctor-access", json={}, headers=h).json()
    assert client.get(f"/api/shared/{tok['token']}/snapshot").status_code == 200
    client.delete(f"/api/patients/{pid}/doctor-access/{tok['id']}", headers=h)
    assert client.get(f"/api/shared/{tok['token']}/snapshot").status_code == 403


def test_clarify_branch_writes_nothing(client):
    h = _auth(client, "e2e2@x.com")
    pid = client.post("/api/patients", json={"name": "E2E2"}, headers=h).json()["id"]
    r = client.post(f"/api/patients/{pid}/intake", json={"raw_text": "vague"}, headers=h)
    body = r.json()
    assert body["status"] == "clarification_needed"
    assert body["question"]
    # nothing recorded yet
    snap = client.get(f"/api/patients/{pid}/snapshot", headers=h).json()
    assert snap["active_problems"] == []


def test_cross_user_forbidden(client):
    ha = _auth(client, "owner@x.com")
    pid = client.post("/api/patients", json={"name": "Owner"}, headers=ha).json()["id"]
    hb = _auth(client, "intruder@x.com")
    assert client.get(f"/api/patients/{pid}/snapshot", headers=hb).status_code == 403
