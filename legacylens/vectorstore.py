"""Pinecone vector store operations."""

import hashlib
from collections.abc import Callable

from pinecone import Pinecone, SearchQuery, ServerlessSpec

from .config import settings
from .models import CodeChunk


METADATA_CONTENT_LIMIT = 10000  # Pinecone 40KB metadata limit
TEXT_FIELD = "chunk_text"  # field name for Pinecone integrated indexes


def _semantic_summary(chunk: CodeChunk) -> str:
    """Build a concise semantic summary for retrieval context and UI display."""
    parts = [f"{chunk.chunk_type} {chunk.name} in {chunk.file_name}"]

    if chunk.copy_references:
        refs = ", ".join(chunk.copy_references[:4])
        suffix = "..." if len(chunk.copy_references) > 4 else ""
        parts.append(f"uses COPY refs: {refs}{suffix}")

    if chunk.calls_to:
        calls = ", ".join(chunk.calls_to[:4])
        suffix = "..." if len(chunk.calls_to) > 4 else ""
        parts.append(f"invokes: {calls}{suffix}")

    if chunk.comments:
        comment = chunk.comments.strip().splitlines()[0][:120]
        if comment:
            parts.append(f"comment hint: {comment}")

    return ". ".join(parts) + "."


def _build_filter_dict(
    file_type_filter: str | None = None,
    metadata_filters: dict[str, str] | None = None,
) -> dict | None:
    filter_dict: dict[str, dict[str, str]] = {}
    if file_type_filter:
        filter_dict["file_type"] = {"$eq": file_type_filter}
    if metadata_filters:
        for key, value in metadata_filters.items():
            if value:
                filter_dict[key] = {"$eq": value}
    return filter_dict or None


def _is_not_found_error(exc: Exception) -> bool:
    """Return True for namespace-not-found style errors."""
    status = getattr(exc, "status", None) or getattr(exc, "status_code", None)
    if status == 404:
        return True
    return "404" in str(exc)


def make_vector_id(chunk: CodeChunk) -> str:
    """Build a stable, unique vector ID for a chunk."""
    path_digest = hashlib.sha1(chunk.file_path.encode("utf-8")).hexdigest()[:12]
    return f"{chunk.file_name}:{path_digest}:{chunk.start_line}-{chunk.end_line}"


def _chunk_metadata(chunk: CodeChunk) -> dict:
    """Build metadata dict for a chunk."""
    return {
        "file_path": chunk.file_path,
        "file_name": chunk.file_name,
        "file_type": chunk.file_type,
        "chunk_type": chunk.chunk_type,
        "name": chunk.name,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "parent_program": chunk.parent_program,
        "comments": chunk.comments[:1000],
        "has_comments": bool(chunk.comments.strip()),
        "content": chunk.content[:METADATA_CONTENT_LIMIT],
        "preamble": chunk.preamble,
        "summary": chunk.summary or _semantic_summary(chunk),
        "copy_references": ",".join(chunk.copy_references),
        "calls_to": ",".join(chunk.calls_to),
    }


def get_index(
    *,
    settings_obj=settings,
    pinecone_factory: Callable[..., Pinecone] = Pinecone,
):
    """Get or create the Pinecone index."""
    pc = pinecone_factory(api_key=settings_obj.pinecone_api_key)

    existing = [idx.name for idx in pc.list_indexes()]
    if settings_obj.pinecone_index_name not in existing:
        if settings_obj.embedding_provider == "pinecone":
            pc.create_index_for_model(
                name=settings_obj.pinecone_index_name,
                cloud="aws",
                region="us-east-1",
                embed={
                    "model": settings_obj.pinecone_model,
                    "field_map": {"text": TEXT_FIELD},
                },
            )
        else:
            pc.create_index(
                name=settings_obj.pinecone_index_name,
                dimension=settings_obj.embedding_dimensions,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )

    return pc.Index(settings_obj.pinecone_index_name)


def upsert_chunks(
    chunks: list[CodeChunk],
    embeddings: list[list[float]],
    batch_size: int = 100,
    *,
    index=None,
    settings_obj=settings,
) -> int:
    """Upsert chunk embeddings into Pinecone (OpenAI provider)."""
    active_index = index or get_index(settings_obj=settings_obj)
    total = 0

    for i in range(0, len(chunks), batch_size):
        batch_chunks = chunks[i : i + batch_size]
        batch_embeds = embeddings[i : i + batch_size]

        vectors = []
        for chunk, embedding in zip(batch_chunks, batch_embeds):
            vec_id = make_vector_id(chunk)
            metadata = _chunk_metadata(chunk)
            vectors.append({"id": vec_id, "values": embedding, "metadata": metadata})

        active_index.upsert(vectors=vectors, namespace=settings_obj.pinecone_namespace)
        total += len(vectors)

    return total


def upsert_records(
    chunks: list[CodeChunk],
    embed_texts: list[str],
    batch_size: int = 96,
    *,
    index=None,
    settings_obj=settings,
) -> int:
    """Upsert records for Pinecone integrated embedding (server-side)."""
    active_index = index or get_index(settings_obj=settings_obj)
    total = 0

    for i in range(0, len(chunks), batch_size):
        batch_chunks = chunks[i : i + batch_size]
        batch_texts = embed_texts[i : i + batch_size]

        records = []
        for chunk, text in zip(batch_chunks, batch_texts):
            record = _chunk_metadata(chunk)
            record["_id"] = make_vector_id(chunk)
            record[TEXT_FIELD] = text
            records.append(record)

        active_index.upsert_records(settings_obj.pinecone_namespace, records)
        total += len(batch_chunks)

    return total


def query_vectors(
    embedding: list[float],
    top_k: int | None = None,
    file_type_filter: str | None = None,
    metadata_filters: dict[str, str] | None = None,
    *,
    index=None,
    settings_obj=settings,
) -> list[dict]:
    """Query Pinecone for similar vectors (OpenAI provider)."""
    active_index = index or get_index(settings_obj=settings_obj)
    k = top_k or settings_obj.top_k

    results = active_index.query(
        vector=embedding,
        top_k=k,
        include_metadata=True,
        namespace=settings_obj.pinecone_namespace,
        filter=_build_filter_dict(file_type_filter, metadata_filters),
    )

    return [
        {
            "id": match.id,
            "score": match.score,
            "metadata": match.metadata,
        }
        for match in results.matches
    ]


def search_records(
    query: str,
    top_k: int | None = None,
    file_type_filter: str | None = None,
    metadata_filters: dict[str, str] | None = None,
    *,
    index=None,
    settings_obj=settings,
) -> list[dict]:
    """Search Pinecone integrated index with text query (server-side embedding)."""
    active_index = index or get_index(settings_obj=settings_obj)
    k = top_k or settings_obj.top_k

    response = active_index.search_records(
        namespace=settings_obj.pinecone_namespace,
        query=SearchQuery(
            inputs={"text": query},
            top_k=k,
            filter=_build_filter_dict(file_type_filter, metadata_filters),
        ),
    )

    return [
        {
            "id": hit.get("_id") or hit.id,
            "score": hit.get("_score") or hit.score,
            "metadata": hit.fields or {},
        }
        for hit in response.result.hits
    ]


def delete_namespace(*, index=None, settings_obj=settings):
    """Delete all vectors in the namespace."""
    active_index = index or get_index(settings_obj=settings_obj)
    try:
        active_index.delete(delete_all=True, namespace=settings_obj.pinecone_namespace)
    except Exception as exc:
        if not _is_not_found_error(exc):
            raise
