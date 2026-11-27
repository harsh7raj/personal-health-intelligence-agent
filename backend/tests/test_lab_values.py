"""Lab values decided in code (D33): aliases, numeric ranges, flags, critical values."""

import pytest

from app.data.critical_values import CRITICAL
from app.data.lab_glossary import GLOSSARY, key_for, lookup, mentioned
from app.services import lab_values as lv
from app.services.language_guard import is_diagnostic
from app.services.vitals_trend import lab_vital_type


@pytest.mark.parametrize("printed,key", [
    ("LDL-C", "ldl_cholesterol"),
    ("LDL Cholesterol (Direct)", "ldl_cholesterol"),
    ("LDL Cholesterol", "ldl_cholesterol"),
    ("HbA1c (Glycated haemoglobin)", "hba1c"),
    ("Glycosylated Hemoglobin", "hba1c"),
    ("SGPT / ALT", "alt"),
    ("S. Creatinine", "creatinine"),
    ("Fasting plasma glucose", "fasting_glucose"),
    ("25-OH Vitamin D", "vitamin_d"),
    ("TSH (Ultrasensitive)", "tsh"),
    ("Platelet Count", "platelet_count"),
    ("Something unheard of", None),
])
def test_printed_names_map_to_one_key(printed, key):
    assert key_for(printed) == key


def test_aliases_share_one_trend_series():
    assert lab_vital_type("LDL-C") == lab_vital_type("LDL Cholesterol (Direct)") == "lab_ldl_cholesterol"
    assert lab_vital_type("Mystery Marker 9") == "lab_mystery_marker_9"  # unknown: slug as before


def test_glossary_is_complete_and_its_text_passes_the_guard():
    assert len(GLOSSARY) >= 40
    for key, e in GLOSSARY.items():
        assert e["measures"] and e["high"] and e["low"] and e["units"], key
        assert e["url"].startswith("https://medlineplus.gov/"), key
        for text in [e["measures"], *e["high"], *e["low"]]:
            assert not is_diagnostic(text), (key, text)
    assert set(CRITICAL) <= set(GLOSSARY)


def test_mentioned_finds_tests_in_questions_without_false_hits():
    assert mentioned("What is TSH?") == ["tsh"]
    assert "hba1c" in mentioned("how did my HbA1c change")
    assert mentioned("can I eat a banana today") == []  # 'na' / 'ca' are not matched
    assert lookup("ldl")["name"] == "LDL cholesterol"


@pytest.mark.parametrize("text,expected", [
    ("4.0 - 5.6", (4.0, 5.6)),
    ("70–100", (70.0, 100.0)),
    ("13.5 to 17.5", (13.5, 17.5)),
    ("<200", (None, 200.0)),
    ("Up to 40", (None, 40.0)),
    (">40", (40.0, None)),
    ("1,50,000 - 4,10,000", (150000.0, 410000.0)),
    ("Desirable: <200; Borderline: 200-239; High: >=240", (None, 200.0)),
    ("Male: 13.5-17.5; Female: 12.0-15.5", (None, None)),  # two bands, none marked: don't guess
    ("Negative", (None, None)),
    (None, (None, None)),
])
def test_parse_range(text, expected):
    assert lv.parse_range(text) == expected


def test_to_number():
    assert lv.to_number("6.9") == 6.9
    assert lv.to_number("1,50,000") == 150000
    assert lv.to_number("13.5 g/dL") == 13.5
    assert lv.to_number("Nil") is None
    assert lv.to_number("<0.5") is None


def test_enrich_flags_from_the_range_not_the_llm():
    [v] = lv.enrich([{"test_name": "HbA1c", "value": "6.9", "unit": "%", "reference_range": "4.0 - 5.6",
                      "flag": "normal"}])  # the LLM got it wrong
    assert v["flag"] == "high" and v["test_key"] == "hba1c"
    assert (v["range_low"], v["range_high"]) == (4.0, 5.6)
    assert v["critical"] is None
    assert lv.outside_by(v) == {"direction": "above", "amount": 1.3, "percent": 23.2}
    # No numeric range: the LLM's flag stays.
    [u] = lv.enrich([{"test_name": "Urine protein", "value": "Trace", "unit": None,
                      "reference_range": "Nil", "flag": "high"}])
    assert u["flag"] == "high" and lv.outside_by(u) is None


@pytest.mark.parametrize("name,value,unit,direction", [
    ("Potassium", "6.8", "mmol/L", "high"),
    ("Serum Sodium", "119", "mEq/L", "low"),
    ("Fasting blood sugar", "48", "mg/dL", "low"),
    ("Fasting blood sugar", "2.5", "mmol/L", "low"),  # 45 mg/dL
    ("Haemoglobin", "6.1", "g/dL", "low"),
    ("Haemoglobin", "61", "g/L", "low"),
    ("Platelet count", "0.4", "lakhs/cumm", "low"),
    ("Platelet count", "35", "10^3/µL", "low"),
    ("Platelet count", "35000", "/cumm", "low"),
])
def test_critical_values(name, value, unit, direction):
    [v] = lv.enrich([{"test_name": name, "value": value, "unit": unit, "reference_range": None, "flag": "unknown"}])
    assert v["critical"]["direction"] == direction
    assert "contact your doctor today" in v["critical"]["message"]


@pytest.mark.parametrize("name,value,unit", [
    ("Potassium", "4.2", "mmol/L"),
    ("Fasting blood sugar", "62", "mg/dL"),   # low, but not critical
    ("Platelet count", "2.1", "lakhs/cumm"),
    ("Platelet count", "35", None),           # unclear unit: never guess a critical
    ("LDL Cholesterol", "250", "mg/dL"),      # not on the critical list
])
def test_not_critical(name, value, unit):
    [v] = lv.enrich([{"test_name": name, "value": value, "unit": unit, "reference_range": None, "flag": "unknown"}])
    assert v["critical"] is None
