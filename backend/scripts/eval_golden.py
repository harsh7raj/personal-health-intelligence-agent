"""Run the LLM eval set (tests/eval/golden.yaml) against the demo patients with REAL models.

    uv run python -m scripts.eval_golden              # all cases, then reset the demo patients
    uv run python -m scripts.eval_golden H01 P07      # some cases
    uv run python -m scripts.eval_golden --no-reset

Stop the app first (embedded Chroma takes one writer). Writes tests/eval/results.md with the pass
rate and every failure. Costs roughly $0.01-0.02 per case (Sonnet).
"""

import argparse
import re
import sys
import time
from datetime import date
from pathlib import Path

import yaml
from sqlalchemy import delete, select

from app.core import clock
from app.db.session import SessionLocal
from app.graph.graph import graph
from app.models.clinical import VitalReading
from app.models.intelligence import Alert
from app.models.patient import Patient
from app.models.records import ChatMessage, Entry, Report
from app.models.user import User
from app.services import report_explainer
from app.services.language_guard import violations
from scripts.demo.generate import load_script

EVAL_DIR = Path(__file__).resolve().parents[1] / "tests" / "eval"
_CITE = re.compile(r"\[([A-Z]\d+)\]")


def _pid(db, key: str) -> int:
    email = load_script(key)["login"]["email"]
    pid = db.scalar(select(Patient.id).join(User, User.id == Patient.user_id).where(User.email == email))
    if pid is None:
        raise SystemExit(f"demo patient {key} isn't loaded: run `python -m scripts.demo reset` first")
    return pid


def _report(db, pid: int, spec) -> Report:
    reps = db.scalars(select(Report).where(Report.patient_id == pid, Report.status == "parsed")
                      .order_by(Report.test_date)).all()
    if spec == "latest" or not isinstance(spec, dict):
        return reps[-1]
    target = clock.today().toordinal() - spec["days_ago"]
    return min(reps, key=lambda r: abs((r.test_date or date.today()).toordinal() - target))


def run_case(case: dict, global_must_not: list[str]) -> tuple[bool, list[str], str]:
    with SessionLocal() as db:
        pid = _pid(db, case["patient"])
        last_entry = db.scalar(select(Entry.id).where(Entry.patient_id == pid).order_by(Entry.id.desc()).limit(1)) or 0
        last_reading = db.scalar(select(VitalReading.id).where(VitalReading.patient_id == pid)
                                 .order_by(VitalReading.id.desc()).limit(1)) or 0
        last_alert = db.scalar(select(Alert.id).where(Alert.patient_id == pid).order_by(Alert.id.desc()).limit(1)) or 0
        if "explain_report" in case:
            out = report_explainer.explain(db, pid, _report(db, pid, case["explain_report"]))
            out["escalation"] = None
        else:
            focus = None
            if case.get("focus_report"):
                focus = {"type": "report", "id": _report(db, pid, case["focus_report"]).id}
            out = graph.invoke({"patient_id": pid, "raw_input": case["message"], "chat": True,
                                "defer_observations": True, "focus": focus})
        reply = out.get("reply") or ""
        problems: list[str] = []
        if case.get("escalation"):
            if not out.get("escalation"):
                problems.append("expected an escalation")
        else:
            if out.get("escalation"):
                problems.append("unexpected escalation")
            if out.get("generated_by") != "llm":
                problems.append(f"not an LLM reply ({out.get('generated_by')})")
            for pat in case.get("must", []):
                if not re.search(pat, reply, re.I | re.S):
                    problems.append(f"missing /{pat}/")
            for pat in case.get("must_not", []) + global_must_not:
                m = re.search(pat, reply, re.I)
                if m:
                    problems.append(f"must not say {m.group(0)!r}")
            bad = violations(reply)
            if bad:
                problems.append(f"diagnosis guard: {bad}")
            evidence = out.get("evidence") or []
            ids = {e.get("id") for e in evidence}
            unknown = [c for c in _CITE.findall(reply) if c not in ids]
            if unknown:
                problems.append(f"cites unknown ids {unknown}")
            kinds = {e.get("kind") for e in evidence}
            for k in case.get("cites", []):
                if k not in kinds:
                    problems.append(f"doesn't cite a {k}")
            if case.get("cites_older_than_days"):
                oldest = max((clock.today() - date.fromisoformat(e["date"][:10])).days
                             for e in evidence if e.get("date")) if any(e.get("date") for e in evidence) else 0
                if oldest < case["cites_older_than_days"]:
                    problems.append(f"no cited item older than {case['cites_older_than_days']} days")
        # leave the record as it was (logs made by the eval are removed; a reset follows anyway)
        new = db.scalars(select(Entry.id).where(Entry.patient_id == pid, Entry.id > last_entry)).all()
        if new:
            db.execute(delete(Entry).where(Entry.id.in_(new)))
        db.execute(delete(VitalReading).where(VitalReading.patient_id == pid, VitalReading.id > last_reading))
        db.execute(delete(Alert).where(Alert.patient_id == pid, Alert.id > last_alert))
        db.execute(delete(ChatMessage).where(ChatMessage.patient_id == pid))
        db.commit()
    return not problems, problems, reply


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")
    ap = argparse.ArgumentParser(prog="python -m scripts.eval_golden")
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--no-reset", action="store_true")
    args = ap.parse_args()
    spec = yaml.safe_load((EVAL_DIR / "golden.yaml").read_text(encoding="utf-8"))
    cases = [c for c in spec["cases"] if not args.ids or c["id"] in args.ids]
    results = []
    started = time.perf_counter()
    for c in cases:
        try:
            ok, problems, reply = run_case(c, spec.get("global_must_not", []))
        except Exception as exc:  # noqa: BLE001
            ok, problems, reply = False, [f"error: {type(exc).__name__}: {exc}"], ""
        results.append((c, ok, problems, reply))
        print(f"{'PASS' if ok else 'FAIL'} {c['id']}" + ("" if ok else f"  {'; '.join(problems)}"))
    passed = sum(1 for _c, ok, _p, _r in results if ok)
    rate = 100 * passed / max(1, len(results))
    lines = [f"# Eval results ({clock.today().isoformat()})", "",
             f"**{passed}/{len(results)} passed ({rate:.0f}%)** in {time.perf_counter() - started:.0f}s.", ""]
    for c, ok, problems, reply in results:
        if not ok:
            lines += [f"## {c['id']} ({c['patient']}): {c.get('message') or 'explain report'}", "",
                      *[f"- {p}" for p in problems], "", "> " + reply.replace("\n", "\n> "), ""]
    (EVAL_DIR / "results.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"\n{passed}/{len(results)} passed ({rate:.0f}%). Details: tests/eval/results.md")
    if not args.no_reset:
        from scripts.demo.replay import replay

        for key in sorted({c["patient"] for c in cases}):
            print(f"resetting {key}...")
            replay(key, log=lambda *_a: None)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
