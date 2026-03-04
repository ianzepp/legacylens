"""Query embedding and Pinecone search."""

from collections.abc import Callable
from dataclasses import dataclass

from .config import settings
from .models import QueryResult
from .vectorstore import query_vectors, search_records


@dataclass(frozen=True)
class RetrieverDependencies:
    """Dependency bundle for retrieval execution."""

    search_records_fn: Callable[..., list[dict]]
    query_vectors_fn: Callable[..., list[dict]]
    get_query_embedding_fn: Callable[[str], list[float]]


def _default_dependencies() -> RetrieverDependencies:
    from .embeddings import get_query_embedding

    return RetrieverDependencies(
        search_records_fn=search_records,
        query_vectors_fn=query_vectors,
        get_query_embedding_fn=get_query_embedding,
    )


def _parse_result(r: dict) -> QueryResult:
    meta = r["metadata"]
    copy_references = [ref for ref in meta.get("copy_references", "").split(",") if ref]
    calls_to = [call for call in meta.get("calls_to", "").split(",") if call]
    return QueryResult(
        content=meta.get("content", ""),
        file_path=meta.get("file_path", ""),
        file_name=meta.get("file_name", ""),
        file_type=meta.get("file_type", ""),
        chunk_type=meta.get("chunk_type", ""),
        name=meta.get("name", ""),
        start_line=meta.get("start_line", 0),
        end_line=meta.get("end_line", 0),
        score=r["score"],
        preamble=meta.get("preamble", ""),
        summary=meta.get("summary", ""),
        comments=meta.get("comments", ""),
        copy_references=copy_references,
        calls_to=calls_to,
    )


def _run_retrieval(
    query: str,
    *,
    top_k: int | None,
    file_type: str | None,
    metadata_filters: dict[str, str] | None,
    embedding_provider: str,
    deps: RetrieverDependencies,
) -> list[dict]:
    if embedding_provider == "pinecone":
        return deps.search_records_fn(
            query,
            top_k=top_k,
            file_type_filter=file_type,
            metadata_filters=metadata_filters,
        )

    embedding = deps.get_query_embedding_fn(query)
    return deps.query_vectors_fn(
        embedding,
        top_k=top_k,
        file_type_filter=file_type,
        metadata_filters=metadata_filters,
    )


def retrieve(
    query: str,
    top_k: int | None = None,
    file_type: str | None = None,
    metadata_filters: dict[str, str] | None = None,
    *,
    embedding_provider: str | None = None,
    deps: RetrieverDependencies | None = None,
) -> list[QueryResult]:
    """Embed a query and retrieve matching code chunks."""
    raw_results = _run_retrieval(
        query,
        top_k=top_k,
        file_type=file_type,
        metadata_filters=metadata_filters,
        embedding_provider=embedding_provider or settings.embedding_provider,
        deps=deps or _default_dependencies(),
    )

    return [_parse_result(r) for r in raw_results]
