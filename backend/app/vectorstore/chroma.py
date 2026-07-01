from functools import lru_cache

import chromadb
from chromadb.api import ClientAPI

from app.core.config import get_settings


@lru_cache
def get_chroma_client() -> ClientAPI:
    settings = get_settings()
    if settings.CHROMA_MODE == "cloud":
        # Managed Chroma Cloud — used in production.
        return chromadb.CloudClient(
            api_key=settings.CHROMA_API_KEY,
            tenant=settings.CHROMA_TENANT,
            database=settings.CHROMA_DATABASE,
        )
    if settings.CHROMA_MODE == "embedded":
        # In-process persistence — no separate Chroma server to host.
        return chromadb.PersistentClient(path=settings.CHROMA_PATH)
    return chromadb.HttpClient(host=settings.CHROMA_HOST, port=settings.CHROMA_PORT)


def chroma_heartbeat() -> bool:
    """Readiness probe for the vector store. True if reachable."""
    try:
        get_chroma_client().heartbeat()
        return True
    except Exception:
        return False
