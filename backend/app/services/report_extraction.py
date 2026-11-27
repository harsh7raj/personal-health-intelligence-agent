"""Report extraction service (Part 1).

Runs on upload as a background task: pulls raw text out of an uploaded report
file, sends it to the LLM for structured extraction, and persists the result on the
``reports`` row (status / report_type / test_date / extracted_values / parse_error).

NO ChromaDB, Memory, or Reasoning wiring here — that is Part 2. This module only
produces and stores the structured extraction.
"""

import base64
import io
import json
import logging
from datetime import date, datetime, time, timezone
from pathlib import Path

from sqlalchemy import select

from app.core import clock
from app.core.llm import is_available, llm_json, llm_vision_json
from app.db.session import SessionLocal
from app.models.clinical import VitalReading
from app.models.records import Report
from app.services import lab_values
from app.services.language_guard import is_diagnostic
from app.services.report_indexing import index_report
from app.services.vitals_trend import (
    lab_vital_type,
    record_lab_readings_and_recompute,
)

logger = logging.getLogger(__name__)

# Minimum characters of extractable text before we trust a PDF as text-based
# (rather than a scanned image that yields a few stray glyphs).
_MIN_TEXT_CHARS = 20

_VALID_FLAGS = {"normal", "high", "low", "unknown"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
_MAX_PAGES = 3  # first pages of a scanned PDF sent to the vision model
_MAX_SIDE = 2000  # px; enough to read small print, keeps the request small
_KNOWN_TYPES = {
    "Diabetes Panel",
    "Lipid Panel",
    "CBC",
    "Thyroid Panel",
    "Kidney Function",
    "Liver Function",
    "Vitamin Panel",
    "Urine Routine",
    "Discharge Summary",
    "Prescription",
    "Other",
}

_SYSTEM_PROMPT = """You are a clinical document data-extraction engine. You are given the \
raw text of a medical report. Extract its structure and return ONLY a JSON object \
(no prose) with EXACTLY these keys:
- report_type: one of "Diabetes Panel" (HbA1c / glucose), "Lipid Panel", "CBC", \
"Thyroid Panel", "Kidney Function" (creatinine, urea, eGFR, electrolytes), "Liver Function", \
"Vitamin Panel" (vitamin D, B12), "Urine Routine", "Discharge Summary", "Prescription", "Other". \
Pick the one that covers most of the results; use "Other" if unsure.
- test_date: the date the tests/sample were taken or the document was issued, as \
"YYYY-MM-DD". If no date is present, use null. Do not invent a date.
- values: an array of measured results. Each item is an object with EXACTLY these keys:
    - test_name: string (e.g. "LDL Cholesterol", "Hemoglobin", "TSH")
    - value: the measured value as a string (e.g. "142", "13.5"); null if not numeric
    - unit: string unit (e.g. "mg/dL", "g/dL", "mIU/L"); null if absent
    - reference_range: string as printed (e.g. "0-100", "<200", "13.5-17.5"); null if absent
    - flag: one of "normal", "high", "low", "unknown" — based ONLY on how the value \
compares to its printed reference_range. Use "unknown" if there is no range to compare against.

Rules:
- For non-lab documents (discharge summaries, prescriptions, notes) that have no \
measured numeric results, return "values": [] (an empty array). Do not fabricate results.
- Extract only what is written. NEVER add a diagnosis, interpretation, cause, or \
treatment recommendation. This is data extraction, not clinical judgement.
- If the text is empty or unintelligible, return report_type "Other", test_date null, \
values []."""


class ExtractionError(Exception):
    """Raised when raw text cannot be obtained from the uploaded file."""


class OcrRequiredError(ExtractionError):
    """The file appears to be a scanned/image-only PDF with no embedded text.

    parse_report then reads the pages with the vision model instead (D33).
    """


def extract_text_from_file(path: str | Path) -> str:
    """Extract raw text from an uploaded report file.

    Supports text-based PDFs and plain-text files. Photos and image-only/scanned PDFs
    raise OcrRequiredError; parse_report sends those to the vision model.
    """
    p = Path(path)
    if not p.exists():
        raise ExtractionError(f"file not found on disk: {p}")

    suffix = p.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        raise OcrRequiredError("photo of a report: read with the vision model")
    if suffix == ".pdf":
        return _extract_pdf_text(p)
    if suffix in {".txt", ".text", ".md", ""}:
        return p.read_text(encoding="utf-8", errors="replace").strip()

    # Best-effort: try to read anything else as UTF-8 text; bail if it's binary.
    try:
        text = p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, ValueError) as exc:
        raise ExtractionError(f"unsupported file type for extraction: {suffix}") from exc
    return text.strip()


def _extract_pdf_text(p: Path) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(p))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # malformed/encrypted PDF
        raise ExtractionError(f"could not read PDF: {exc}") from exc

    text = "\n".join(pages).strip()
    if len(text) < _MIN_TEXT_CHARS:
        # Almost no embedded text -> very likely a scanned/photographed report.
        raise OcrRequiredError(
            "PDF has little or no embedded text (likely scanned/image-only); "
            "OCR is not yet supported"
        )
    return text


def _coerce_date(raw: object) -> date | None:
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _clean_values(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        return []
    cleaned: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("test_name")
        if not name:
            continue
        flag = str(item.get("flag") or "unknown").lower()
        if flag not in _VALID_FLAGS:
            flag = "unknown"
        cleaned.append(
            {
                "test_name": str(name),
                "value": None if item.get("value") is None else str(item.get("value")),
                "unit": _str_or_none(item.get("unit")),
                "reference_range": _str_or_none(item.get("reference_range")),
                "flag": flag,
            }
        )
    return cleaned


def _str_or_none(v: object) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def extract_report_data(text: str) -> dict:
    """Send extracted text to the LLM and return normalized structured fields:

    ``{"report_type": str, "test_date": date|None, "values": list[dict]}``.

    Raises if no LLM is available/configured — the caller marks the report failed.
    (Unlike intake, we do NOT silently fabricate a fallback extraction: an unparsed
    report must be visibly 'failed', never a hollow 'parsed'.)
    """
    if not is_available():
        raise ExtractionError("No LLM configured — cannot extract report structure")

    return _normalize(llm_json("report_extract", _SYSTEM_PROMPT, text))


_VISION_PROMPT = _SYSTEM_PROMPT + """
You are given photos or scanned pages of the report instead of its text. Read them carefully. Skip any value you cannot read clearly; never guess a digit. Add one more key:
- raw_text: the report's text as you read it, as plain text (test, value, unit, range per line)."""


def page_images(path: str | Path) -> list[str]:
    """A photo, or the first pages of a scanned PDF, as JPEG data: URLs for the vision model."""
    from PIL import Image, ImageOps

    p = Path(path)
    if p.suffix.lower() == ".pdf":
        import pypdfium2

        pdf = pypdfium2.PdfDocument(str(p))
        try:
            pages = [pdf[i].render(scale=2).to_pil() for i in range(min(len(pdf), _MAX_PAGES))]
        finally:
            pdf.close()
    else:
        try:
            pages = [ImageOps.exif_transpose(Image.open(p))]  # phone photos carry their rotation
        except Exception as exc:
            raise ExtractionError(f"could not open image: {exc}") from exc
    urls = []
    for img in pages:
        img = img.convert("RGB")
        img.thumbnail((_MAX_SIDE, _MAX_SIDE))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        urls.append("data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode())
    if not urls:
        raise ExtractionError("the file has no pages")
    return urls


def extract_report_data_from_images(images: list[str]) -> dict:
    """Same output as extract_report_data, read from photos/scans; adds raw_text."""
    if not is_available():
        raise ExtractionError("No LLM configured — cannot read report images")
    raw = llm_vision_json("report_vision", _VISION_PROMPT, "Extract this report.", images)
    return {**_normalize(raw), "raw_text": _str_or_none(raw.get("raw_text"))}


def _normalize(raw: dict) -> dict:
    report_type = raw.get("report_type")
    if report_type not in _KNOWN_TYPES:
        report_type = "Other"

    return {
        "report_type": report_type,
        "test_date": _coerce_date(raw.get("test_date")),
        # Ranges as numbers, flags, test keys and critical values are decided in code (D33).
        "values": lab_values.enrich(_clean_values(raw.get("values"))),
    }


_SUMMARY_SYSTEM = """You write ONE or TWO short, plain-language sentences summarizing a \
patient's lab/medical report for the patient themselves. Be factual and reassuring in tone \
but STRICTLY NON-DIAGNOSTIC: describe only what the numbers show and how they compare to the \
reference range or to prior reports. HARD RULES: never state or imply a diagnosis or disease; \
never assert a cause; never recommend treatment or medication; never say "you have X". \
You MAY say a value is "elevated", "low", "within range", or "trending up/down since <date>" \
because those describe the data. If a test is trending, mention it and the earlier date. End \
by noting results are worth discussing with their doctor if anything is flagged. Return JSON: \
{"summary": "..."} — plain text, 1-2 sentences, no bullet points."""


def _deterministic_summary(report_type: str, values: list[dict], trends: list[dict]) -> str:
    flagged = [
        f"{v['test_name']} is {v.get('flag')}"
        for v in values
        if v.get("flag") in ("high", "low") and v.get("test_name")
    ]
    rising = [t["test_name"] for t in trends if t.get("trend") == "rising"]
    parts: list[str] = []
    if flagged:
        parts.append(
            f"This {report_type.lower()} shows " + ", ".join(flagged[:3]) + "."
        )
    else:
        parts.append(f"This {report_type.lower()} shows results within their reference ranges.")
    if rising:
        parts.append(f"{', '.join(rising[:3])} appears to be trending upward across your reports.")
    parts.append("Consider discussing any flagged results with your doctor.")
    return " ".join(parts)


def generate_report_summary(
    report_type: str, values: list[dict], trends: list[dict]
) -> str | None:
    """1-2 sentence plain-language, non-diagnostic takeaway (requirement #4).

    `trends` carries cross-report movement for recurring tests so the summary can say
    "trending up since your March panel". Falls back to a deterministic sentence when no
    LLM is available or the LLM output trips the non-diagnostic guard.
    """
    if not values and not trends:
        return None
    if not is_available():
        return _deterministic_summary(report_type, values, trends)

    payload = {
        "report_type": report_type,
        "values": [
            {
                "test_name": v.get("test_name"),
                "value": v.get("value"),
                "unit": v.get("unit"),
                "reference_range": v.get("reference_range"),
                "flag": v.get("flag"),
            }
            for v in values
        ],
        "trends": trends,
    }
    try:
        raw = llm_json("report_summary", _SUMMARY_SYSTEM, json.dumps(payload), temperature=0.2)
        summary = (raw.get("summary") or "").strip()
    except Exception:
        logger.warning("report ai_summary generation failed — using fallback", exc_info=True)
        return _deterministic_summary(report_type, values, trends)

    if not summary or is_diagnostic(summary):
        if summary:
            logger.warning("dropped diagnostic-sounding report summary: %s", summary)
        return _deterministic_summary(report_type, values, trends)
    return summary


def _report_timestamp(report: Report) -> datetime:
    """When to date this report's lab readings: the reported test_date (midnight UTC) so
    cross-report ordering is chronological, else the row's creation time."""
    if report.test_date:
        return datetime.combine(report.test_date, time.min, tzinfo=timezone.utc)
    if report.created_at:
        return report.created_at
    return clock.now()


TREND_THRESHOLD_PCT = 5.0  # first -> latest change smaller than this reads as "stable"


def _lab_trends(db, patient_id: int, values: list[dict]) -> list[dict]:
    """For each recurring lab test in this report: its values across reports and a direction
    computed in code from the first to the latest (D34), so the ai_summary can say "down from
    8.4 in April". The rolling-average trend used for vitals misreads 2-3 report points as
    stable, so it isn't used here. Only tests with >=2 readings are returned."""
    trends: list[dict] = []
    seen: set[str] = set()
    for v in values:
        name = v.get("test_name")
        if not name:
            continue
        vt = lab_vital_type(name)
        if vt in seen:
            continue
        seen.add(vt)
        readings = db.scalars(
            select(VitalReading).where(
                VitalReading.patient_id == patient_id, VitalReading.vital_type == vt
            ).order_by(VitalReading.recorded_at)
        ).all()
        if len(readings) < 2:
            continue  # need at least two reports to speak of a trend
        first, latest = readings[0].value, readings[-1].value
        pct = (latest - first) / first * 100 if first else 0.0
        trend = "rising" if pct > TREND_THRESHOLD_PCT else "falling" if pct < -TREND_THRESHOLD_PCT else "stable"
        trends.append(
            {
                "test_name": name,
                "trend": trend,
                "change_pct_first_to_latest": round(pct, 1),
                "values": [{"date": r.recorded_at.date().isoformat(), "value": r.value} for r in readings[-5:]],
                "n_reports": len(readings),
                "since": readings[0].recorded_at.date().isoformat(),
            }
        )
    return trends


def parse_report(report_id: int) -> None:
    """Background task: extract + persist structured data for one report.

    Owns its own DB session (the request session is already closed by the time this
    runs). Never raises — failures are captured on the row as status='failed'.
    """
    with SessionLocal() as db:
        report = db.get(Report, report_id)
        if report is None:
            logger.warning("parse_report: report %s no longer exists", report_id)
            return
        report.status = "parsing"
        db.commit()

        try:
            try:
                text = extract_text_from_file(report.path)
                data = extract_report_data(text)
            except OcrRequiredError:  # a photo or a scan: read the pages with the vision model
                data = extract_report_data_from_images(page_images(report.path))
                text = data.get("raw_text") or ""
            report.extracted_text = text
            report.report_type = data["report_type"]
            report.test_date = data["test_date"]
            report.extracted_values = data["values"]
            report.parse_error = None
            report.status = "parsed"

            # (3) Feed recurring lab tests into the SAME rolling-average trend as vitals.
            recorded_at = _report_timestamp(report)
            record_lab_readings_and_recompute(
                db, report.patient_id, report.id, data["values"], recorded_at
            )
            db.flush()

            # (4) Plain-language, non-diagnostic takeaway — informed by cross-report trends.
            trends = _lab_trends(db, report.patient_id, data["values"])
            report.ai_summary = generate_report_summary(
                data["report_type"], data["values"], trends
            )
            db.commit()

            # (1) Index findings into Chroma so the Memory agent can retrieve them.
            db.refresh(report)
            index_report(report)

            logger.info(
                "parse_report: report %s parsed as %s (%d values, %d lab trends)",
                report_id,
                data["report_type"],
                len(data["values"]),
                len(trends),
            )
        except Exception as exc:  # noqa: BLE001 - background task must not crash
            db.rollback()
            report = db.get(Report, report_id)
            if report is not None:
                report.status = "failed"
                report.parse_error = f"{type(exc).__name__}: {exc}"
                logger.warning("parse_report: report %s failed: %s", report_id, exc)
            db.commit()


def reconcile_orphaned_parses() -> int:
    """Fail any report still stuck in 'parsing' from a prior process.

    Extraction runs as a FastAPI BackgroundTask, which does NOT survive a process
    restart/crash. Any row left in 'parsing' at startup is orphaned — its worker is
    gone and it would otherwise sit in 'parsing' forever. We flip those to 'failed'
    with a clear parse_error so the record is never stuck and the patient can re-upload.

    Returns the number of reports reconciled. Called at app startup (best-effort).
    """
    with SessionLocal() as db:
        orphaned = list(
            db.scalars(select(Report).where(Report.status == "parsing")).all()
        )
        for report in orphaned:
            report.status = "failed"
            report.parse_error = (
                "Parsing was interrupted before it finished (the server restarted "
                "mid-parse). Please re-upload the report to try again."
            )
        if orphaned:
            db.commit()
            logger.warning(
                "reconcile_orphaned_parses: marked %d stuck report(s) as failed",
                len(orphaned),
            )
        return len(orphaned)


def extraction_summary(report: Report) -> str:
    """Human-readable one-liner (handy for the test script / logs)."""
    return json.dumps(
        {
            "id": report.id,
            "status": report.status,
            "report_type": report.report_type,
            "test_date": report.test_date.isoformat() if report.test_date else None,
            "n_values": len(report.extracted_values or []),
            "parse_error": report.parse_error,
        }
    )
