from app.db.session import SessionLocal
from app.graph.state import GraphState
from app.services.alerts import create_alerts_for_readings
from app.services.clusters import update_clusters
from app.services.missing_info import check_missing_info, suggested_actions
from app.services.observations import generate_observations
from app.services.problems import (
    auto_resolve,
    refresh_problem_trends,
    upsert_problem_from_symptom,
)
from app.services.vitals_trend import record_vital_and_recompute


def reasoning_node(state: GraphState) -> dict:
    ne = state.new_entry
    if not ne:
        return {}

    pid = state.patient_id
    etype = ne.get("type")
    summary: dict = {"entry_type": etype}

    with SessionLocal() as db:
        alerts: list[dict] = []

        if etype == "vital":
            readings = record_vital_and_recompute(db, pid, ne)
            alerts = create_alerts_for_readings(db, pid, readings)
            summary["vitals_updated"] = sorted({r[0] for r in readings})
            summary["alerts"] = alerts
        elif etype == "symptom":
            prob = upsert_problem_from_symptom(db, pid, ne)
            db.flush()
            update_clusters(db, pid, ne)
            summary["problem"] = prob.name

        refresh_problem_trends(db, pid)
        summary["resolved"] = auto_resolve(db, pid)
        missing = check_missing_info(db, pid)
        summary["missing_info"] = missing
        summary["suggested_actions"] = suggested_actions(db, pid, alerts, missing)
        db.commit()

        # Observations read the just-updated state, then persist.
        summary["observations"] = generate_observations(db, pid, ne, state.context_bundle)
        db.commit()

    return {"reasoning_summary": summary}
