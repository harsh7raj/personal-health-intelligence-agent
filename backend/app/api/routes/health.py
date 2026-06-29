from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db.session import engine
from app.vectorstore.chroma import chroma_heartbeat

router = APIRouter(tags=["system"])


def _check_postgres() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@router.get("/health")
def health() -> JSONResponse:
    pg_ok = _check_postgres()
    chroma_ok = chroma_heartbeat()
    healthy = pg_ok and chroma_ok
    body = {
        "status": "ok" if healthy else "degraded",
        "postgres": "ok" if pg_ok else "fail",
        "chroma": "ok" if chroma_ok else "fail",
    }
    return JSONResponse(status_code=200 if healthy else 503, content=body)
