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
