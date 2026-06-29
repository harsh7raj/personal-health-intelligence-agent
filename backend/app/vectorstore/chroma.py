from functools import lru_cache

import chromadb
from chromadb.api import ClientAPI

from app.core.config import get_settings


@lru_cache
def get_chroma_client() -> ClientAPI:
    settings = get_settings()
    return chromadb.HttpClient(host=settings.CHROMA_HOST, port=settings.CHROMA_PORT)


def chroma_heartbeat() -> bool:
    """Readiness probe for the Chroma server. True if reachable."""
    try:
        get_chroma_client().heartbeat()
        return True
    except Exception:
        return False
