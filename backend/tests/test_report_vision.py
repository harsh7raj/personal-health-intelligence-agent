"""Photos and scanned PDFs go to the vision model (D33); text PDFs keep the text path."""

import base64
import io

import pytest
from PIL import Image

from app.core import llm
from app.models.patient import Patient
from app.models.records import Report
from app.models.user import User
from app.services import report_extraction as rx


def _photo(path, size=(2400, 1200)):
    Image.new("RGB", size, "white").save(path)
    return path


def test_a_photo_becomes_one_downscaled_jpeg(tmp_path):
    [url] = rx.page_images(_photo(tmp_path / "report.png"))
    assert url.startswith("data:image/jpeg;base64,")
    img = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))
    assert max(img.size) <= 2000


def test_a_scanned_pdf_needs_vision_and_renders_its_pages(tmp_path):
    pdf = tmp_path / "scan.pdf"
    Image.new("RGB", (800, 1100), "white").save(pdf)  # image-only PDF, no text layer
    with pytest.raises(rx.OcrRequiredError):
        rx.extract_text_from_file(pdf)
    assert len(rx.page_images(pdf)) == 1
    with pytest.raises(rx.OcrRequiredError):
        rx.extract_text_from_file(_photo(tmp_path / "p.jpg", (100, 100)))


def test_vision_calls_carry_images_and_cache_by_image(monkeypatch, tmp_path):
    seen = []

    def fake_live(task, system, user, temperature, as_json, max_tokens, images=None):
        seen.append((task, images))
        return {"ok": len(seen)}

    monkeypatch.setattr(llm, "_route_live", fake_live)
    with llm.response_cache(tmp_path / "c"):
        assert llm.llm_vision_json("report_vision", "s", "u", ["data:a"]) == {"ok": 1}
        assert llm.llm_vision_json("report_vision", "s", "u", ["data:a"]) == {"ok": 1}  # cached
        assert llm.llm_vision_json("report_vision", "s", "u", ["data:b"]) == {"ok": 2}  # new image
    assert seen == [("report_vision", ["data:a"]), ("report_vision", ["data:b"])]
    assert llm._content("hi", None) == "hi"
    assert llm._content("hi", ["data:a"])[1] == {"type": "image_url", "image_url": {"url": "data:a"}}


def test_parse_report_reads_a_photo_with_the_vision_model(db, monkeypatch, tmp_path):
    user = User(email="vision@x.com", password_hash="x", role="patient")
    db.add(user)
    db.flush()
    patient = Patient(user_id=user.id, name="V")
    db.add(patient)
    db.flush()
    rep = Report(patient_id=patient.id, filename="hba1c.jpg", path=str(_photo(tmp_path / "hba1c.jpg")),
                 status="uploaded")
    db.add(rep)
    db.commit()

    def fake_vision(task, system, user_text, images, **_kw):
        assert task == "report_vision" and len(images) == 1 and "raw_text" in system
        return {"report_type": "Diabetes Panel", "test_date": "2026-10-14", "raw_text": "HbA1c 6.9 % 4.0-5.6",
                "values": [{"test_name": "HbA1c", "value": "6.9", "unit": "%", "reference_range": "4.0 - 5.6",
                            "flag": "unknown"}]}

    monkeypatch.setattr(rx, "is_available", lambda: True)
    monkeypatch.setattr(rx, "llm_vision_json", fake_vision)
    monkeypatch.setattr(rx, "llm_json", lambda *a, **k: pytest.fail("text path must not run for a photo"))
    monkeypatch.setattr(rx, "generate_report_summary", lambda *a, **k: None)
    monkeypatch.setattr(rx, "index_report", lambda r: None)
    rx.parse_report(rep.id)

    db.expire_all()
    got = db.get(Report, rep.id)
    assert got.status == "parsed" and got.report_type == "Diabetes Panel"
    assert got.extracted_text == "HbA1c 6.9 % 4.0-5.6"
    [v] = got.extracted_values
    assert v["flag"] == "high" and v["test_key"] == "hba1c" and v["range_high"] == 5.6
