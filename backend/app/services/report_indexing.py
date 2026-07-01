"""Index parsed report findings into ChromaDB so the Memory agent can retrieve them.

Reports live in the dedicated ``patient_reports`` collection (memory.md section 5:
"Embedded report text chunks ... read by Memory Agent"). We chunk a parsed report into
embeddable natural-language strings — one per lab value plus a whole-report summary chunk —
and tag every chunk with patient_id / report_id / date / report_type (+ test_name, flag) so
they are filterable, mirroring the metadata convention used for ``patient_entries``.
"""

import logging

from app.models.records import Report
from app.vectorstore.collections import get_reports_collection

logger = logging.getLogger(__name__)


def _report_date(report: Report) -> str:
    if report.test_date:
        return report.test_date.isoformat()
    if report.created_at:
        return report.created_at.date().isoformat()
    return ""


def _value_sentence(report_type: str, date: str, v: dict) -> str:
    name = v.get("test_name") or "Result"
    value = v.get("value")
    unit = v.get("unit") or ""
    ref = v.get("reference_range")
    flag = v.get("flag") or "unknown"
    measured = f"{value} {unit}".strip() if value is not None else "recorded"
    ref_part = f" (reference {ref})" if ref else ""
    flag_part = "" if flag in ("unknown", "normal") else f", flagged {flag}"
    when = f" on {date}" if date else ""
    return f"{report_type}{when}: {name} measured {measured}{ref_part}{flag_part}."


def build_report_chunks(report: Report) -> list[tuple[str, str, dict]]:
    """Return [(chunk_id, text, metadata), ...] for one parsed report.

    A summary chunk anchors retrieval for whole-report queries; per-value chunks give
    fine-grained, test-name-filterable recall (e.g. an 'LDL trend' query).
    """
    report_type = report.report_type or "Report"
    date = _report_date(report)
    values = report.extracted_values or []

    base_meta = {
        "patient_id": report.patient_id,
        "report_id": report.id,
        "report_type": report_type,
        "date": date,
        "kind": "report",
    }

    chunks: list[tuple[str, str, dict]] = []

    # Whole-report summary chunk (always present, even for non-lab documents).
    value_brief = "; ".join(
        f"{v.get('test_name')}={v.get('value')} {v.get('unit') or ''}".strip()
        for v in values
        if v.get("test_name")
    )
    summary_text = " ".join(
        part
        for part in [
            f"{report_type}" + (f" from {date}" if date else "") + ".",
            report.ai_summary or "",
            (f"Findings: {value_brief}." if value_brief else ""),
        ]
        if part
    ).strip()
    if not summary_text:
        summary_text = f"{report_type}" + (f" from {date}" if date else "")
    chunks.append(
        (
            f"report_{report.id}_summary",
            summary_text,
            {**base_meta, "chunk": "summary"},
        )
    )

    # One chunk per lab value, tagged with its test_name + flag for filtering.
    for i, v in enumerate(values):
        if not v.get("test_name"):
            continue
        meta = {
            **base_meta,
            "chunk": "value",
            "test_name": str(v.get("test_name")),
            "flag": str(v.get("flag") or "unknown"),
        }
        chunks.append(
            (f"report_{report.id}_v{i}", _value_sentence(report_type, date, v), meta)
        )

    return chunks


def index_report(report: Report) -> int:
    """Upsert all chunks for a report into the patient_reports collection.

    Clears any prior chunks for this report first (idempotent re-index), then adds the
    current set. Returns the number of chunks indexed. Never raises — indexing failure
    must not fail the parse pipeline.
    """
    try:
        collection = get_reports_collection()
        # Remove any stale chunks from a previous parse of this report.
        collection.delete(where={"report_id": report.id})

        chunks = build_report_chunks(report)
        if not chunks:
            return 0
        collection.upsert(
            ids=[c[0] for c in chunks],
            documents=[c[1] for c in chunks],
            metadatas=[c[2] for c in chunks],
        )
        logger.info("indexed report %s into Chroma (%d chunks)", report.id, len(chunks))
        return len(chunks)
    except Exception:
        logger.warning("failed to index report %s into Chroma", report.id, exc_info=True)
        return 0
