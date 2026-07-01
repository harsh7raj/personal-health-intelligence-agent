"""Reference data (NOT patient-owned): the local, sourced drug-drug interaction
table imported from DDInter 2.0 (CC BY-NC-SA 4.0). Read-only at request time.
Interactions are surfaced ONLY from this table — never generated."""

from sqlalchemy import BigInteger, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DrugInteraction(Base):
    __tablename__ = "drug_interactions"
    __table_args__ = (
        # One row per unordered, normalized drug pair.
        Index("ix_ddi_pair", "drug_lo", "drug_hi", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # Normalized (lowercased) pair, stored sorted so lookup is order-independent.
    drug_lo: Mapped[str] = mapped_column(String(255), nullable=False)
    drug_hi: Mapped[str] = mapped_column(String(255), nullable=False)
    # Original display names from the source.
    name_a: Mapped[str] = mapped_column(String(255), nullable=False)
    name_b: Mapped[str] = mapped_column(String(255), nullable=False)
    level: Mapped[str] = mapped_column(String(32), nullable=False)  # Major|Moderate|Minor|Unknown
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="DDInter 2.0")
