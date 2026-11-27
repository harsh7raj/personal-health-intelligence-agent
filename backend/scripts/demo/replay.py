"""Replay a demo patient through the REAL pipeline, in date order, with the app clock frozen at
each event (memory.md D32). Problems, trends, clusters, alerts, observations and embeddings
therefore all come from the app's own code. Every LLM answer is cached in scripts/demo/cache,
so after the first run a reset is offline, free and identical.

Stop the API before running: the embedded Chroma store takes one writer at a time.
"""

import shutil
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select

from app.core import clock, llm
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.graph.graph import graph
from app.models.clinical import DoseLog, Medication, VitalReading
from app.models.patient import MedicalBackground, Patient
from app.models.records import Report
from app.models.user import User
from app.services import med_events
from app.services.alerts import create_alerts_for_readings
from app.services.missing_info import check_missing_info
from app.services.problems import refresh_problem_trends
from app.services.report_extraction import parse_report
from app.services.vitals_trend import recompute_summary
from app.vectorstore.collections import get_entries_collection, get_reports_collection
from scripts.demo.generate import GENERATED_DIR, Event, build_timeline, load_script, make_lab_pdf

CACHE_DIR = Path(__file__).resolve().parent / "cache"


def wipe(email: str) -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            return
        patient = db.scalar(select(Patient).where(Patient.user_id == user.id))
        if patient is not None:
            for coll in (get_entries_collection, get_reports_collection):
                try:
                    coll().delete(where={"patient_id": patient.id})
                except Exception:
                    pass
            for rep in db.scalars(select(Report).where(Report.patient_id == patient.id)).all():
                Path(rep.path).unlink(missing_ok=True)
        db.delete(user)  # cascades to everything the patient owns
        db.commit()


def _create(script: dict, today: date) -> tuple[int, dict[str, int]]:
    with SessionLocal() as db:
        user = User(email=script["login"]["email"], password_hash=hash_password(script["login"]["password"]))
        db.add(user)
        db.flush()
        patient = Patient(user_id=user.id, **script["patient"])
        db.add(patient)
        db.flush()
        db.add(MedicalBackground(patient_id=patient.id, **script["background"]))
        meds: dict[str, int] = {}
        for m in script["medicines"]:
            started = today - timedelta(days=m["started_days_ago"])
            med = Medication(
                patient_id=patient.id, name=m["name"], dose=m["dose"], frequency=m["frequency"],
                dose_times=m["dose_times"], purpose=m.get("purpose"), prescriber=m.get("prescriber"),
                prescriber_specialty=m.get("specialty"), started_on=started,
            )
            db.add(med)
            db.flush()
            med_events.record(db, med, "start", event_date=started, new_dose=med.dose)
            meds[m["name"]] = med.id
        db.commit()
        return patient.id, meds


def _entry(pid: int, text: str) -> None:
    result = graph.invoke({"patient_id": pid, "raw_input": text})
    if result.get("needs_clarification"):  # a demo log is complete as written
        graph.invoke({"patient_id": pid, "raw_input": f"{text}\nAdditional info: nothing else to add.",
                      "skip_router": True})


def _reading(pid: int, readings: list[tuple[str, float, str]], when) -> None:
    with SessionLocal() as db:
        for vt, value, unit in readings:
            db.add(VitalReading(patient_id=pid, vital_type=vt, value=value, unit=unit, recorded_at=when))
        db.flush()
        for vt in {r[0] for r in readings}:
            recompute_summary(db, pid, vt)
        create_alerts_for_readings(db, pid, readings)  # same path as the vitals form
        check_missing_info(db, pid)
        db.commit()


def _report(pid: int, script: dict, ev: Event) -> None:
    sample_day = clock.to_local(ev.at).date()
    pdf = make_lab_pdf(GENERATED_DIR / script["key"] / f"hba1c_report_{ev.data['index']}.pdf",
                       script, ev.data, sample_day)
    dest = Path(get_settings().UPLOAD_DIR) / str(pid) / pdf.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pdf, dest)
    with SessionLocal() as db:
        rep = Report(patient_id=pid, filename=pdf.name, path=str(dest), status="uploaded")
        db.add(rep)
        db.commit()
        rid = rep.id
    parse_report(rid)  # the real extraction: text -> LLM values -> lab trends -> summary -> Chroma


def replay(key: str, log=print) -> int:
    script = load_script(key)
    today = clock.today()
    timeline = build_timeline(script, today)
    wipe(script["login"]["email"])
    with llm.response_cache(CACHE_DIR / key, prune=True):  # drop answers to old prompts
        pid, meds = _create(script, today)
        for i, ev in enumerate(timeline, start=1):
            with clock.frozen_at(ev.at):
                if ev.kind == "entry":
                    _entry(pid, ev.data["text"])
                elif ev.kind == "reading":
                    _reading(pid, [(ev.data["vital_type"], ev.data["value"], ev.data["unit"])], ev.at)
                elif ev.kind == "bp":
                    _reading(pid, [("bp_systolic", ev.data["systolic"], "mmHg"),
                                   ("bp_diastolic", ev.data["diastolic"], "mmHg")], ev.at)
                elif ev.kind == "dose":
                    with SessionLocal() as db:
                        db.add(DoseLog(patient_id=pid, medication_id=meds[ev.data["medicine"]],
                                       scheduled_date=date.fromisoformat(ev.data["date"]),
                                       scheduled_time=ev.data["time"], taken_at=ev.at))
                        db.commit()
                elif ev.kind == "med_change":
                    with SessionLocal() as db:
                        med = db.get(Medication, meds[ev.data["medicine"]])
                        before = med_events.snapshot(med)
                        med.dose = ev.data["dose"]
                        for change in med_events.record_changes(
                            db, med, before, event_date=clock.to_local(ev.at).date()
                        ):
                            change.note = ev.data.get("note")
                        db.commit()
                elif ev.kind == "report":
                    _report(pid, script, ev)
            if i % 50 == 0 or i == len(timeline):
                log(f"  {key}: {i}/{len(timeline)} events")
        with SessionLocal() as db:  # trends as of today
            refresh_problem_trends(db, pid)
            db.commit()
    return pid
