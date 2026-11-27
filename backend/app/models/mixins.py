from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock

# default=clock.now stamps ORM inserts with the app clock, so a demo replay frozen in the
# past gets past timestamps; server_default stays the fallback for raw SQL inserts.


class CreatedAtMixin:
    """For append-only / immutable rows that only record creation time."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=clock.now, server_default=func.now(), nullable=False
    )


class TimestampMixin:
    """For rows that get updated in place (created + updated audit)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=clock.now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=clock.now,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
