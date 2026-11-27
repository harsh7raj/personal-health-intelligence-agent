import os

# Point the app at an isolated test DB and force offline LLM BEFORE importing app modules.
TEST_DB_URL = "postgresql+psycopg://phia:phia@localhost:5432/phia_test"
ADMIN_URL = "postgresql+psycopg://phia:phia@localhost:5432/postgres"
os.environ["DATABASE_URL"] = TEST_DB_URL
# Offline: no LLM provider configured (env beats backend/.env) and no usage-log file.
for _var in ("LLM_BASE_URL", "LLM_API_KEY", "FALLBACK_API_KEY", "GROQ_API_KEY", "LLM_USAGE_LOG"):
    os.environ[_var] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

import app.models  # noqa: E402,F401  (register models on Base.metadata)
from app.db import session as db_session  # noqa: E402
from app.db.base import Base  # noqa: E402


class _FakeCollection:
    """Stand-in for a Chroma collection so tests never touch the vector store."""

    def add(self, **_kw):
        return None

    def delete(self, **_kw):
        return None

    def count(self):
        return 0

    def upsert(self, **_kw):
        return None

    def query(self, **_kw):
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}


def _stub_parse(text: str) -> dict:
    import re

    t = text.lower()
    m = re.search(r"(\d{2,3})\s*(?:/|over)\s*(\d{2,3})", t)
    if "blood pressure" in t or "bp" in t or m:
        attrs = {"systolic": int(m.group(1)), "diastolic": int(m.group(2))} if m else {}
        return {"type": "vital", "name": "blood pressure", "attributes": attrs,
                "value": None, "unit": None, "complete": True, "clarifying_question": None}
    if "vague" in t or len(t) < 6:
        return {"type": "symptom", "name": "unclear", "attributes": {},
                "complete": False, "clarifying_question": "Can you say more?"}
    name = "migraine" if ("migraine" in t or "headache" in t) else "symptom"
    return {"type": "symptom", "name": name, "attributes": {"severity": "moderate"},
            "value": None, "unit": None, "complete": True, "clarifying_question": None}


class _BlockedLLMClient:
    """Any attempt to build a real LLM client in tests fails loudly (no network)."""

    def __init__(self, *_a, **_kw):
        raise RuntimeError("Tests must not call a real LLM; stub it instead.")


@pytest.fixture(autouse=True)
def _no_external_calls(monkeypatch):
    """Keep the whole suite offline: no LLM, no RxNav, no DDInter download."""
    import app.core.llm as llm

    client_factory = llm._client  # tests may swap llm._client; clear the real cache
    client_factory.cache_clear()
    monkeypatch.setattr(llm, "OpenAI", _BlockedLLMClient)
    # RxNav, RxClass and openFDA: every reference API call goes through http.get_json.
    monkeypatch.setattr("app.services.rxnorm._get_json", lambda _url: None)
    monkeypatch.setattr("app.services.http.get_json", lambda *_a, **_k: None)
    yield
    client_factory.cache_clear()


@pytest.fixture(scope="session", autouse=True)
def _setup_test_db():
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS phia_test WITH (FORCE)"))
        conn.execute(text("CREATE DATABASE phia_test"))
    admin.dispose()
    Base.metadata.create_all(db_session.engine)
    yield
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS phia_test WITH (FORCE)"))
    admin.dispose()


@pytest.fixture(autouse=True)
def _clean_tables(_setup_test_db):
    yield
    with db_session.engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE'))


@pytest.fixture
def db():
    s = db_session.SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def client(monkeypatch):
    fake = _FakeCollection()
    for mod in (
        "app.graph.nodes.intake",
        "app.graph.nodes.memory",
        "app.api.routes.symptoms",
        "app.vectorstore.collections",
    ):
        monkeypatch.setattr(f"{mod}.get_entries_collection", lambda: fake, raising=False)
    # Reports live in a separate collection the Memory node now also queries.
    monkeypatch.setattr(
        "app.graph.nodes.memory.get_reports_collection", lambda: fake, raising=False
    )
    monkeypatch.setattr("app.services.retrieval.get_entries_collection", lambda: fake)
    monkeypatch.setattr("app.services.retrieval.get_reports_collection", lambda: fake)
    monkeypatch.setattr("app.graph.nodes.intake.parse_entry", _stub_parse)

    import app.main as main_mod
    import scripts.import_ddinter as ddinter

    monkeypatch.setattr(main_mod, "bootstrap_collections", lambda: [])
    # App startup would otherwise download DDInter (+ RxNav lookups) into phia_test.
    monkeypatch.setattr(ddinter, "bootstrap_if_empty", lambda: 0)
    with TestClient(main_mod.app) as c:
        yield c
