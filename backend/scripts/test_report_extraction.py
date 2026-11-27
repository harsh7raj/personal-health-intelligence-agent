"""Quick smoke test for the report extraction service (Part 1).

Generates a couple of sample report files (a lab panel + a non-lab discharge
summary), runs the extraction directly, and prints the structured JSON so we can
eyeball that it looks sane. Does NOT touch the DB or the API — pure service test.

Run:  uv run python -m scripts.test_report_extraction
Requires an LLM key (LLM_API_KEY or FALLBACK_API_KEY) in backend/.env for the LLM step.
"""

import json
import tempfile
from pathlib import Path

from app.services.report_extraction import (
    ExtractionError,
    extract_report_data,
    extract_text_from_file,
)

LIPID_PANEL = """\
RIVERSIDE DIAGNOSTICS LABORATORY
Patient: Dana Demo            Collected: 2026-05-14
Test: LIPID PANEL (Fasting)

Test                  Result    Units     Reference Range    Flag
Total Cholesterol     232       mg/dL     <200               HIGH
LDL Cholesterol       158       mg/dL     <100               HIGH
HDL Cholesterol       41        mg/dL     >40                NORMAL
Triglycerides         180       mg/dL     <150               HIGH

Performed by Riverside Diagnostics. For physician review.
"""

DISCHARGE_SUMMARY = """\
ST. MARGARET'S HOSPITAL — DISCHARGE SUMMARY
Patient: Dana Demo        Admitted: 2026-03-02   Discharged: 2026-03-05

Reason for admission: observation following an episode of dizziness.
Course: patient remained stable; vitals monitored. No acute events.
Discharge instructions: rest, hydrate, follow up with primary care in 2 weeks.
Medications on discharge: continue existing amlodipine 5mg daily.

This is a narrative document with no tabulated laboratory results.
"""

SAMPLES = [
    ("lipid_panel.txt", LIPID_PANEL),
    ("discharge_summary.txt", DISCHARGE_SUMMARY),
]


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="report_extract_"))
    for name, body in SAMPLES:
        path = tmp / name
        path.write_text(body, encoding="utf-8")
        print(f"\n{'=' * 70}\nFILE: {name}\n{'=' * 70}")
        try:
            text = extract_text_from_file(path)
            print(f"[extracted {len(text)} chars of raw text]")
            data = extract_report_data(text)
            # test_date is a date object -> serialize for display
            printable = {
                "report_type": data["report_type"],
                "test_date": data["test_date"].isoformat() if data["test_date"] else None,
                "values": data["values"],
            }
            print(json.dumps(printable, indent=2))
        except ExtractionError as exc:
            print(f"EXTRACTION ERROR: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
