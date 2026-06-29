from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base. Sole metadata source for SQLAlchemy models and Alembic."""

    pass
