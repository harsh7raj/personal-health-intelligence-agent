"""Non-diagnostic language audit. Scans a patient's stored observations + generated story
for diagnostic/prescriptive phrasing. Exits nonzero if any violations are found.

Run:  uv run python -m scripts.audit_language <patient_id>
"""

import sys

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.intelligence import Observation
from app.services.language_guard import violations
from app.services.story import build_story


def audit(patient_id: int) -> int:
    db = SessionLocal()
    issues: list[tuple[str, str, list[str]]] = []
    try:
        for o in db.scalars(
            select(Observation).where(Observation.patient_id == patient_id)
        ).all():
            v = violations(o.text)
            if v:
                issues.append((f"observation#{o.id}", o.text, v))
        story = build_story(db, patient_id)["story"]
        v = violations(story)
        if v:
            issues.append(("story", story[:140], v))
    finally:
        db.close()

    if issues:
        print(f"FOUND {len(issues)} non-diagnostic violation(s) for patient {patient_id}:")
        for where, text, v in issues:
            print(f"  [{where}] matched {v}\n      {text[:120]}")
        return 1
    print(f"No non-diagnostic-language violations for patient {patient_id}. ✓")
    return 0


if __name__ == "__main__":
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    sys.exit(audit(pid))
