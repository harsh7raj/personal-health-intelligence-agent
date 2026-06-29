"""SQLAlchemy models. Importing this package registers every table on Base.metadata
(relied on by alembic/env.py for autogenerate)."""

from app.db.base import Base
from app.models.access import DoctorAccess
from app.models.clinical import (
    Medication,
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
from app.models.records import Entry, MemoryLog, Report
from app.models.user import User

__all__ = [
    "Base",
    "User",
    "Patient",
    "MedicalBackground",
    "Medication",
    "Problem",
    "VitalReading",
    "VitalSummary",
    "SymptomCluster",
    "Observation",
    "Alert",
    "MissingInformation",
    "SuggestedAction",
    "Entry",
    "Report",
    "MemoryLog",
    "DoctorAccess",
]
