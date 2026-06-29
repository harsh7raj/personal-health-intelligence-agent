from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class PatientCreate(BaseModel):
    name: str
    age: Optional[int] = None
    sex: Optional[str] = None
    height: Optional[float] = None
    weight: Optional[float] = None
    blood_group: Optional[str] = None
    contact: Optional[str] = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class PatientUpdate(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    sex: Optional[str] = None
    height: Optional[float] = None
    weight: Optional[float] = None
    blood_group: Optional[str] = None
    contact: Optional[str] = None
    attributes: Optional[dict[str, Any]] = None


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    age: Optional[int] = None
    sex: Optional[str] = None
    height: Optional[float] = None
    weight: Optional[float] = None
    blood_group: Optional[str] = None
    contact: Optional[str] = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class BackgroundUpdate(BaseModel):
    conditions: Optional[list[Any]] = None
    allergies: Optional[list[Any]] = None
    family_history: Optional[list[Any]] = None
    surgical_history: Optional[list[Any]] = None
    lifestyle: Optional[dict[str, Any]] = None


class BackgroundOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    patient_id: int
    conditions: list[Any] = Field(default_factory=list)
    allergies: list[Any] = Field(default_factory=list)
    family_history: list[Any] = Field(default_factory=list)
    surgical_history: list[Any] = Field(default_factory=list)
    lifestyle: dict[str, Any] = Field(default_factory=dict)
