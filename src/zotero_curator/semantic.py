"""Optional semantic search helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zotero_curator.formatting import normalize_whitespace
from zotero_curator.settings import load_config


class OptionalSemanticDependencyError(RuntimeError):
    pass


@dataclass(frozen=True)
class SemanticDocument:
    key: str
    text: str
    metadata: dict[str, str]


def require_semantic_dependencies():
    try:
        import chromadb  # type: ignore[import-not-found]
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional extra
        raise OptionalSemanticDependencyError(
            "Semantic search requires the optional semantic extra. Install with "
            "`uv tool install 'zotero-curator[semantic]'` or `uv pip install -e '.[semantic]'`."
        ) from exc
    return chromadb, SentenceTransformer


def semantic_store_dir() -> Path:
    cfg = load_config()
    base = cfg.data_dir or (Path.home() / ".local" / "share" / "zotero-curator")
    return base / "semantic"


def document_from_item(item: dict[str, Any]) -> SemanticDocument | None:
    data = item.get("data", {})
    key = str(data.get("key") or item.get("key") or "")
    if not key:
        return None
    creators = data.get("creators") or []
    creator_names = []
    for creator in creators:
        if name := creator.get("name"):
            creator_names.append(str(name))
        else:
            creator_names.append(" ".join(part for part in [creator.get("firstName"), creator.get("lastName")] if part))
    fields = [
        data.get("title"),
        "; ".join(creator_names),
        data.get("abstractNote"),
        data.get("publicationTitle"),
        data.get("DOI"),
        data.get("url"),
    ]
    text = normalize_whitespace("\n".join(str(field) for field in fields if field))
    if not text:
        return None
    return SemanticDocument(
        key=key,
        text=text,
        metadata={
            "key": key,
            "title": str(data.get("title") or "Untitled"),
            "itemType": str(data.get("itemType") or "unknown"),
            "url": str(data.get("url") or ""),
        },
    )


def build_semantic_index(zot: Any, limit: int = 500, collection_name: str = "zotero-items") -> dict[str, Any]:
    chromadb, SentenceTransformer = require_semantic_dependencies()
    store = semantic_store_dir()
    store.mkdir(parents=True, exist_ok=True)
    model = SentenceTransformer("all-MiniLM-L6-v2")
    client = chromadb.PersistentClient(path=str(store))
    collection = client.get_or_create_collection(collection_name)
    items = zot.items(limit=limit)
    documents = [doc for item in items if (doc := document_from_item(item))]
    if not documents:
        return {"indexed": 0, "store": str(store), "collection": collection_name}
    embeddings = model.encode([doc.text for doc in documents], normalize_embeddings=True).tolist()
    collection.upsert(
        ids=[doc.key for doc in documents],
        documents=[doc.text for doc in documents],
        metadatas=[doc.metadata for doc in documents],
        embeddings=embeddings,
    )
    return {"indexed": len(documents), "store": str(store), "collection": collection_name}


def semantic_search(query: str, n_results: int = 5, collection_name: str = "zotero-items") -> dict[str, Any]:
    if not query.strip():
        raise ValueError("Provide a query for semantic search.")
    chromadb, SentenceTransformer = require_semantic_dependencies()
    store = semantic_store_dir()
    model = SentenceTransformer("all-MiniLM-L6-v2")
    client = chromadb.PersistentClient(path=str(store))
    collection = client.get_or_create_collection(collection_name)
    embedding = model.encode([query], normalize_embeddings=True).tolist()[0]
    return collection.query(query_embeddings=[embedding], n_results=n_results)
