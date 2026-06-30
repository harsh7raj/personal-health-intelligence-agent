"""Idempotent demo seed: a high-density, ~1-year longitudinal record for a very
active logger. Arc: blood pressure rising over the year, migraines increasing
(roughly monthly → several times a month), managed vitamin D deficiency, a resolved
strep throat early in the year, a migraine+fatigue cluster — plus two newer threads:
a resolved lower-back-pain episode and an emerging elevated-blood-glucose trend
(evidenced by its own rising glucose series, not symptom entries).

All problems carry `aliases` so the per-problem sub-timeline links the parsed symptom
names (e.g. entry 'sore throat' ↔ problem 'strep throat'). All observations are
factual/non-diagnostic and pass the language guard.

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


def _ramp(days_list: list[int], lo: float, hi: float, wobble: list[int]) -> list[tuple[int, float]]:
    """Map a list of days-ago to a value ramped lo→hi as days-ago goes high→low
    (i.e. most recent = hi), with a small deterministic wobble for realism."""
    dmin, dmax = min(days_list), max(days_list)
    span = (dmax - dmin) or 1
    out: list[tuple[int, float]] = []
    for i, d in enumerate(sorted(days_list, reverse=True)):  # oldest → newest
        frac = 1 - (d - dmin) / span
        out.append((d, round(lo + frac * (hi - lo) + wobble[i % len(wobble)])))
    return out


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
                family_history=["Father: hypertension", "Mother: type 2 diabetes"],
                surgical_history=[],
                lifestyle={"smoking": False, "alcohol": "occasional", "exercise": "light"},
            )
        )
        db.add(Medication(patient_id=pid, name="Amlodipine", dose="5mg", frequency="once daily"))
        db.add(Medication(patient_id=pid, name="Vitamin D", dose="1000 IU", frequency="once daily"))

        # --- Vitals over ~1 year, high density ---
        # BP every ~2 weeks. A gentle first half then a steeper recent climb so the
        # rolling-average rule (last 3 vs prior 3 readings, D1) still reads 'rising'
        # despite the dense spacing — clinically plausible for worsening hypertension.
        bp_old = list(range(87, 365, 14))  # older readings, ~116/74 → ~130/82
        older = [
            (d, sv, dv)
            for (d, sv), (_, dv) in zip(
                _ramp(bp_old, 116, 130, [0, 2, -1, 1, -2, 1, 0]),
                _ramp(bp_old, 74, 82, [1, -1, 0, 2, -2, 1, -1]),
            )
        ]
        # A clearly rising recent tail (last 6 readings) guarantees the 'rising' trend.
        recent_tail = [
            (73, 133, 83), (59, 136, 85), (45, 139, 87),
            (31, 141, 89), (17, 144, 91), (3, 147, 92),
        ]
        bp_all = sorted(older + recent_tail, key=lambda x: -x[0])  # oldest → newest
        recent_sys = recent_dia = None
        for d, sv, dv in bp_all:
            ts = _days_ago(d)
            db.add(VitalReading(patient_id=pid, vital_type="bp_systolic", value=sv, unit="mmHg", recorded_at=ts))
            db.add(VitalReading(patient_id=pid, vital_type="bp_diastolic", value=dv, unit="mmHg", recorded_at=ts))
            recent_sys, recent_dia = sv, dv  # last loop = most recent (oldest→newest order)
        # Weight monthly, drifting 72 → 70.
        for d, w in _ramp(list(range(15, 365, 33)), 72, 70, [0, 1, -1, 0]):
            db.add(VitalReading(patient_id=pid, vital_type="weight", value=w, unit="kg", recorded_at=_days_ago(d)))
        # Blood glucose monthly, the emerging thread: 92 → 118 (elevated, below the 200 alert line).
        for d, g in _ramp(list(range(10, 365, 33)), 92, 118, [1, -2, 1, 0, 2, -1]):
            db.add(VitalReading(patient_id=pid, vital_type="blood_glucose", value=g, unit="mg/dL", recorded_at=_days_ago(d)))
        db.flush()
        for vt in ("bp_systolic", "bp_diastolic", "weight", "blood_glucose"):
            recompute_summary(db, pid, vt)
        create_alerts_for_readings(
            db, pid, [("bp_systolic", recent_sys, "mmHg"), ("bp_diastolic", recent_dia, "mmHg")]
        )

        # --- Symptom entries over the year (dense), embedded in Chroma ---
        # (days_ago, raw_text, structured)
        def sym(name, sev=None):
            attrs = {"severity": sev} if sev else {}
            return {"name": name, "attributes": attrs}

        entries = [
            (350, "sore throat with fever for two days, hard to swallow", sym("sore throat", "moderate")),
            (345, "throat still sore, feeling run down", sym("sore throat", "mild")),
            (340, "first migraine in a while, moderate, behind one eye", sym("migraine", "moderate")),
            (300, "migraine again this month, throbbing for a few hours", sym("migraine", "moderate")),
            (262, "mild migraine, passed after resting", sym("migraine", "mild")),
            (226, "migraine with some nausea, light bothered me", sym("migraine", "moderate")),
            (210, "lower back pain after gardening, stiff in the morning", sym("lower back pain", "moderate")),
            (195, "lower back still aching, worse when sitting long", sym("lower back pain", "moderate")),
            (192, "migraine, moderate, lasted most of the afternoon", sym("migraine", "moderate")),
            (178, "back pain improving with stretching", sym("lower back pain", "mild")),
            (160, "another migraine, throbbing, took it easy", sym("migraine", "moderate")),
            (120, "migraine plus felt wiped out the rest of the day", sym("migraine", "moderate")),
            (88, "migraine with light sensitivity, fairly bad", sym("migraine", "severe")),
            (60, "migraine again, moderate", sym("migraine", "moderate")),
            (59, "very tired and low energy today", sym("fatigue")),
            (38, "bad migraine, light sensitivity, had to lie down", sym("migraine", "severe")),
            (37, "exhausted and drained, no energy", sym("fatigue")),
            (20, "migraine, moderate, throbbing", sym("migraine", "moderate")),
            (9, "another migraine this week, also fatigued", sym("migraine", "moderate")),
            (7, "ongoing fatigue, run down", sym("fatigue")),
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

        # --- Problems (aliases link parsed symptom names → clinical labels) ---
        migraine_count = sum(1 for _, _, s in entries if s["name"] == "migraine")
        db.add(
            Problem(
                patient_id=pid, name="migraine", status="active", severity="moderate",
                frequency=f"{migraine_count} episodes", trend="increasing",
                first_seen=_days_ago(340), last_seen=_days_ago(9),
                attributes={"episode_count": migraine_count, "aliases": ["migraine headache"]},
            )
        )
        db.add(
            Problem(
                patient_id=pid, name="strep throat", status="resolved", severity="moderate",
                frequency="1 episode", first_seen=_days_ago(350), last_seen=_days_ago(345),
                resolved_at=_days_ago(320), attributes={"episode_count": 1, "aliases": ["sore throat"]},
            )
        )
        db.add(
            Problem(
                patient_id=pid, name="lower back pain", status="resolved", severity="moderate",
                frequency="3 episodes", first_seen=_days_ago(210), last_seen=_days_ago(178),
                resolved_at=_days_ago(150), attributes={"episode_count": 3, "aliases": ["back pain"]},
            )
        )
        db.add(
            Problem(
                patient_id=pid, name="vitamin D deficiency", status="managed", trend="stable",
                first_seen=_days_ago(360), last_seen=_days_ago(30), attributes={},
            )
        )
        # Emerging thread: evidenced by its glucose series (vital_types), no symptom entries.
        db.add(
            Problem(
                patient_id=pid, name="elevated blood glucose", status="active", trend="rising",
                frequency="ongoing", first_seen=_days_ago(340), last_seen=_days_ago(10),
                attributes={"vital_types": ["blood_glucose"]},
            )
        )

        # --- Cluster: migraine + fatigue (co-occurred ~3 times) ---
        db.add(
            SymptomCluster(patient_id=pid, symptoms=["fatigue", "migraine"], occurrences=3, last_seen=_days_ago(7))
        )

        db.commit()

        if embed_ids:
            try:
                get_entries_collection().add(documents=embed_docs, ids=embed_ids, metadatas=embed_meta)
            except Exception as exc:  # noqa: BLE001
                print(f"  ! Chroma embedding skipped: {exc}")

        # --- Missing info + suggested actions ---
        missing = check_missing_info(db, pid)
        suggested_actions(db, pid, [{"kind": "high_bp"}], missing)
        db.commit()

        # --- Observations: factual, non-diagnostic (grounded in the seeded data) ---
        canned = [
            f"Migraine episodes have grown more frequent over the past year, totaling {migraine_count} recorded episodes.",
            "Blood pressure has trended upward from about 118/76 to roughly 145/92 over the year.",
            "Blood glucose readings have risen gradually from about 92 to 118 mg/dL across the year.",
            "Fatigue has co-occurred with several recent migraine episodes.",
            "Lower back pain was recorded across roughly two months earlier in the year and has not been logged since.",
            "Weight has stayed close to 70-72 kg throughout the year.",
        ]
        for text in canned:
            if not is_diagnostic(text):
                db.add(Observation(patient_id=pid, text=text, evidence={"source": "seed"}))
        db.commit()

        n_vitals = len(bp_all) * 2 + len(range(15, 365, 33)) + len(range(10, 365, 33))
        print("Seeded demo patient (dense, ~1 year):")
        print(f"  login: {DEMO_EMAIL} / {DEMO_PASSWORD}  (patient id {pid})")
        print(f"  vitals: {n_vitals} readings | entries: {len(entries)} | problems: 5 (2 resolved)")
        print(f"  migraine x{migraine_count} (increasing), BP rising, glucose rising, back pain resolved, strep resolved.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
