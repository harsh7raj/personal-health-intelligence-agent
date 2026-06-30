"""Idempotent demo seed: a longitudinal patient with months of history — a developing
BP trend, a resolved problem, an increasing recurring problem, and a symptom cluster.

Run:  uv run python -m scripts.seed_demo
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.clinical import Medication, Problem, SymptomCluster, VitalReading
from app.models.intelligence import Observation
from app.models.patient import MedicalBackground, Patient
from app.models.records import Entry
from app.models.user import User
from app.services.alerts import create_alerts_for_readings
from app.services.language_guard import is_diagnostic
from app.services.missing_info import check_missing_info, suggested_actions
from app.services.observations import generate_observations
from app.services.vitals_trend import recompute_summary
from app.vectorstore.collections import get_entries_collection

settings = get_settings()

DEMO_EMAIL = "demo@phia.health"
DEMO_PASSWORD = "demo-pass-123"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _days_ago(n: int) -> datetime:
    return _now() - timedelta(days=n)


def _wipe_existing(db) -> None:
    user = db.scalar(select(User).where(User.email == DEMO_EMAIL))
    if user is None:
        return
    patient = db.scalar(select(Patient).where(Patient.user_id == user.id))
    if patient is not None:
        try:
            get_entries_collection().delete(where={"patient_id": patient.id})
        except Exception:
            pass
    db.delete(user)  # cascades to patient + all owned rows
    db.commit()


def seed() -> None:
    db = SessionLocal()
    try:
        _wipe_existing(db)

        user = User(email=DEMO_EMAIL, password_hash=hash_password(DEMO_PASSWORD), role="patient")
        db.add(user)
        db.flush()

        patient = Patient(user_id=user.id, name="Dana Demo", age=54, sex="F", blood_group="O+")
        db.add(patient)
        db.flush()
        pid = patient.id

        db.add(
            MedicalBackground(
                patient_id=pid,
                conditions=["Hypertension"],
                allergies=["Penicillin"],
                family_history=["Father: hypertension"],
                surgical_history=[],
                lifestyle={"smoking": False, "alcohol": "occasional"},
            )
        )
        db.add(Medication(patient_id=pid, name="Amlodipine", dose="5mg", frequency="once daily"))
        db.add(Medication(patient_id=pid, name="Vitamin D", dose="1000 IU", frequency="once daily"))

        # --- Vitals: BP rising over ~6 months ---
        bp = [(180, 120, 78), (150, 124, 80), (120, 130, 84), (90, 134, 86), (60, 140, 90), (30, 146, 92), (3, 144, 91)]
        for days, sys_v, dia_v in bp:
            ts = _days_ago(days)
            db.add(VitalReading(patient_id=pid, vital_type="bp_systolic", value=sys_v, unit="mmHg", recorded_at=ts))
            db.add(VitalReading(patient_id=pid, vital_type="bp_diastolic", value=dia_v, unit="mmHg", recorded_at=ts))
        for days, w in [(180, 71), (90, 70), (3, 70)]:
            db.add(VitalReading(patient_id=pid, vital_type="weight", value=w, unit="kg", recorded_at=_days_ago(days)))
        db.flush()
        for vt in ("bp_systolic", "bp_diastolic", "weight"):
            recompute_summary(db, pid, vt)
        # Alerts from the recent elevated readings.
        create_alerts_for_readings(db, pid, [("bp_systolic", 144, "mmHg"), ("bp_diastolic", 91, "mmHg")])

        # --- Entries (symptoms) over months, embedded in Chroma ---
        entries = [
            (155, "sore throat with fever for two days", {"name": "sore throat", "attributes": {"severity": "moderate"}}),
            (150, "migraine headache, moderate, lasted a few hours", {"name": "migraine", "attributes": {"severity": "moderate"}}),
            (110, "migraine again this month, throbbing", {"name": "migraine", "attributes": {"severity": "moderate"}}),
            (70, "migraine with some nausea", {"name": "migraine", "attributes": {"severity": "moderate"}}),
            (35, "migraine headache and felt very fatigued", {"name": "migraine", "attributes": {"severity": "moderate"}}),
            (35, "very tired and low energy today", {"name": "fatigue", "attributes": {}}),
            (14, "bad migraine with light sensitivity", {"name": "migraine", "attributes": {"severity": "severe"}}),
            (7, "another migraine, also fatigued", {"name": "migraine", "attributes": {"severity": "moderate"}}),
            (7, "ongoing fatigue", {"name": "fatigue", "attributes": {}}),
        ]
        embed_docs, embed_ids, embed_meta = [], [], []
        for days, text, struct in entries:
            ts = _days_ago(days)
            fact = {"type": "symptom", **struct, "complete": True}
            e = Entry(patient_id=pid, type="symptom", raw_text=text, structured=fact, source="seed")
            e.created_at = ts
            db.add(e)
            db.flush()
            embed_docs.append(text)
            embed_ids.append(f"entry_{e.id}")
            embed_meta.append({"patient_id": pid, "entry_id": e.id, "type": "symptom", "date": ts.isoformat()})

        # --- Problems ---
        db.add(
            Problem(
                patient_id=pid, name="migraine", status="active", severity="moderate",
                frequency="6 episodes", trend="increasing", first_seen=_days_ago(150),
                last_seen=_days_ago(7), attributes={"episode_count": 6},
            )
        )
        db.add(
            Problem(
                patient_id=pid, name="strep throat", status="resolved", severity="moderate",
                frequency="1 episode", first_seen=_days_ago(155), last_seen=_days_ago(150),
                resolved_at=_days_ago(120), attributes={"episode_count": 1},
            )
        )
        db.add(
            Problem(
                patient_id=pid, name="vitamin D deficiency", status="managed", trend="stable",
                first_seen=_days_ago(200), last_seen=_days_ago(30), attributes={},
            )
        )
        # --- Cluster: migraine + fatigue ---
        db.add(
            SymptomCluster(patient_id=pid, symptoms=["fatigue", "migraine"], occurrences=2, last_seen=_days_ago(7))
        )

        db.commit()

        # Chroma embeddings (after commit so ids are final)
        if embed_ids:
            try:
                get_entries_collection().add(documents=embed_docs, ids=embed_ids, metadatas=embed_meta)
            except Exception as exc:  # noqa: BLE001
                print(f"  ! Chroma embedding skipped: {exc}")

        # --- Missing info + suggested actions ---
        missing = check_missing_info(db, pid)
        suggested_actions(db, pid, [{"kind": "high_bp"}], missing)
        db.commit()

        # --- Observations: LLM if key, else canned non-diagnostic ---
        if settings.GROQ_API_KEY:
            generate_observations(db, pid, {"type": "symptom", "name": "migraine"}, None)
        else:
            for text in [
                "Migraine episodes have increased from roughly monthly to weekly over the past five months.",
                "Blood pressure has trended upward from 120/78 to about 144/91 over six months.",
                "Fatigue has co-occurred with several recent migraine episodes.",
            ]:
                if not is_diagnostic(text):
                    db.add(Observation(patient_id=pid, text=text, evidence={"source": "seed"}))
        db.commit()

        print("Seeded demo patient:")
        print(f"  login: {DEMO_EMAIL} / {DEMO_PASSWORD}  (patient id {pid})")
        print(f"  vitals: {len(bp) * 2 + 3} readings | entries: {len(entries)} | problems: 3 (1 resolved)")
        print("  BP trend rising, migraine increasing, strep resolved, migraine+fatigue cluster.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
