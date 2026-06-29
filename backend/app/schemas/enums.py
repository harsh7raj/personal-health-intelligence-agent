from enum import Enum


class Role(str, Enum):
    patient = "patient"
    # Reserved; doctors use doctor_access tokens, not accounts.
    doctor = "doctor"


class ProblemStatus(str, Enum):
    active = "active"
    managed = "managed"
    resolved = "resolved"


class Trend(str, Enum):
    rising = "rising"
    falling = "falling"
    stable = "stable"


class VitalType(str, Enum):
    bp_systolic = "bp_systolic"
    bp_diastolic = "bp_diastolic"
    weight = "weight"
    heart_rate = "heart_rate"
    blood_glucose = "blood_glucose"
    spo2 = "spo2"


class EntryType(str, Enum):
    symptom = "symptom"
    vital = "vital"
    report = "report"
    medication = "medication"
    note = "note"


class OutputType(str, Enum):
    snapshot = "snapshot"
    story = "story"
    pdf = "pdf"
