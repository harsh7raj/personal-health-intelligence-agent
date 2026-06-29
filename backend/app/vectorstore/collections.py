"""Chroma collections (memory.md section 5). Two collections, both embedded with the
frozen all-MiniLM-L6-v2 model (chromadb DefaultEmbeddingFunction, ONNX)."""

from chromadb.api.models.Collection import Collection
from chromadb.utils import embedding_functions

from app.vectorstore.chroma import get_chroma_client

ENTRIES_COLLECTION = "patient_entries"
REPORTS_COLLECTION = "patient_reports"

# all-MiniLM-L6-v2; embeddings computed client-side over HttpClient.
_embedding_fn = embedding_functions.DefaultEmbeddingFunction()


def get_entries_collection() -> Collection:
    return get_chroma_client().get_or_create_collection(
        name=ENTRIES_COLLECTION, embedding_function=_embedding_fn
    )


def get_reports_collection() -> Collection:
    return get_chroma_client().get_or_create_collection(
        name=REPORTS_COLLECTION, embedding_function=_embedding_fn
    )


def bootstrap_collections() -> list[str]:
    """Create both collections if absent. Called at app startup."""
    get_entries_collection()
    get_reports_collection()
    return [ENTRIES_COLLECTION, REPORTS_COLLECTION]
