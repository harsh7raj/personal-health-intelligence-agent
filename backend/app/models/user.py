from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import CreatedAtMixin

if TYPE_CHECKING:
    from app.models.patient import Patient


class User(CreatedAtMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # Patients only have accounts; doctors authenticate via doctor_access tokens.
    role: Mapped[str] = mapped_column(
        String(32), nullable=False, default="patient", server_default="patient"
    )

    patient: Mapped["Patient"] = relationship(back_populates="user", uselist=False)
