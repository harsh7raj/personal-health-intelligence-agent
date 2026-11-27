"""SQLAlchemy models. Importing this package registers every table on Base.metadata
(relied on by alembic/env.py for autogenerate)."""

from app.db.base import Base
from app.models.access import DoctorAccess
from app.models.drugs import DrugClassInfo, DrugLabel, MedCheckRun
from app.models.clinical import (
    DoseLog,
    Medication,
    MedicationEvent,
    Problem,
    SymptomCluster,
    VitalReading,
    VitalSummary,
)
from app.models.intelligence import (
    Alert,
    MissingInformation,
    Observation,
    SuggestedAction,
)
from app.models.patient import MedicalBackground, Patient
from app.models.records import ChatMessage, Entry, MemoryLog, Report
from app.models.reference import DrugInteraction
from app.models.user import User
from app.models.visits import Reminder, SavedQuestion, Visit

__all__ = [
    "Base",
    "User",
    "Patient",
    "MedicalBackground",
    "Medication",
    "MedicationEvent",
    "DoseLog",
    "Problem",
    "VitalReading",
    "VitalSummary",
    "SymptomCluster",
    "Observation",
    "Alert",
    "MissingInformation",
    "SuggestedAction",
    "ChatMessage",
    "Entry",
    "Report",
    "MemoryLog",
    "DoctorAccess",
    "DrugInteraction",
    "DrugLabel",
    "DrugClassInfo",
    "MedCheckRun",
    "Visit",
    "Reminder",
    "SavedQuestion",
]
