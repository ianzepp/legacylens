"""LangChain RAG chain for answering questions about COBOL code."""

import time
from collections.abc import Callable
from dataclasses import dataclass

import tiktoken
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from .config import settings
from .retriever import retrieve

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

_encoder = None


def _count_tokens(text: str) -> int:
    """Approximate token count using tiktoken."""
    global _encoder
    if _encoder is None:
        try:
            _encoder = tiktoken.encoding_for_model(settings.chat_model)
        except Exception:
            _encoder = tiktoken.get_encoding("cl100k_base")
    return len(_encoder.encode(text))

SYSTEM_PROMPT = """\
You are LegacyLens, an expert assistant for understanding legacy COBOL codebases.
You answer questions about the AWS CardDemo credit card management application.

Rules:
- Base your answers on the retrieved code context below. Do not make up information.
- When the question is broad or vague, describe what the retrieved code reveals about the topic.
- Cite sources as [FileName:StartLine-EndLine] when referencing specific code.
- Explain COBOL concepts in plain English when relevant.
- Be concise but thorough. Your answers should be no more than 1-2 paragraphs, unless the response clearly requires an extended answer.

Retrieved context:
{context}
"""

USER_PROMPT = "{question}"
NO_CONTEXT_MESSAGE = (
    "I could not retrieve any relevant code chunks for this question. "
    "Please try rephrasing, broadening the question, or checking index/namespace configuration."
)


@dataclass(frozen=True)
class ChainDependencies:
    """Dependency bundle for ask/ask_stream execution."""

    retrieve_fn: Callable[..., list]
    build_llm_fn: Callable[[str, bool], ChatOpenAI]
    count_tokens_fn: Callable[[str], int]
    clock_fn: Callable[[], float]


def _default_dependencies() -> ChainDependencies:
    return ChainDependencies(
        retrieve_fn=retrieve,
        build_llm_fn=_build_llm,
        count_tokens_fn=_count_tokens,
        clock_fn=time.perf_counter,
    )


def _format_context(results: list) -> str:
    """Format retrieved results into context string."""
    parts = []
    for i, r in enumerate(results, 1):
        score_str = f"{r.score:.3f}" if r.score is not None else "n/a"
        parts.append(
            f"--- Source {i}: {r.file_path}:{r.start_line}-{r.end_line} "
            f"(score: {score_str}) ---\n"
            f"{r.preamble}\n\n"
            f"{r.content}\n"
        )
    return "\n".join(parts)


def _is_openrouter_model(model: str) -> bool:
    """Models with a '/' are OpenRouter provider/model format."""
    return "/" in model


def _build_llm(model: str, streaming: bool = False) -> ChatOpenAI:
    """Build a ChatOpenAI instance, routing to OpenRouter if model contains '/'."""
    kwargs: dict = {"model": model, "streaming": streaming}

    if _is_openrouter_model(model):
        kwargs["api_key"] = settings.openrouter_api_key
        kwargs["base_url"] = OPENROUTER_BASE_URL
    else:
        kwargs["api_key"] = settings.openai_api_key
        if not model.startswith("gpt-5"):
            kwargs["temperature"] = 0

    return ChatOpenAI(**kwargs)


def _serialize_source(result) -> dict:
    """Map retrieval result to API response payload."""
    return {
        "file_path": result.file_path,
        "file_name": result.file_name,
        "file_type": result.file_type,
        "name": result.name,
        "start_line": result.start_line,
        "end_line": result.end_line,
        "score": result.score,
        "chunk_type": result.chunk_type,
        "preamble": result.preamble,
        "content": result.content,
        "comments": result.comments,
        "copy_references": result.copy_references,
        "calls_to": result.calls_to,
    }


def _build_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", USER_PROMPT),
    ])


def _resolve_results(
    question: str,
    *,
    top_k: int | None,
    file_type: str | None,
    results: list | None,
    retrieve_fn: Callable[..., list],
) -> tuple[list, bool]:
    if results is not None:
        return results, True
    return retrieve_fn(question, top_k=top_k, file_type=file_type), False


def _prepare_common(
    question: str,
    *,
    top_k: int | None,
    file_type: str | None,
    model: str | None,
    results: list | None,
    deps: ChainDependencies,
) -> dict:
    t_start = deps.clock_fn()
    resolved_results, rag_cached = _resolve_results(
        question,
        top_k=top_k,
        file_type=file_type,
        results=results,
        retrieve_fn=deps.retrieve_fn,
    )
    t_rag = deps.clock_fn()
    context = _format_context(resolved_results)
    effective_model = model or settings.chat_model
    input_text = SYSTEM_PROMPT.replace("{context}", context) + question
    tokens_in = deps.count_tokens_fn(input_text)
    return {
        "t_start": t_start,
        "t_rag": t_rag,
        "context": context,
        "effective_model": effective_model,
        "tokens_in": tokens_in,
        "results": resolved_results,
        "rag_cached": rag_cached,
    }


def _build_stats(
    *,
    t_start: float,
    t_rag: float,
    t_llm_first: float,
    t_llm_end: float,
    tokens_in: int,
    tokens_out: int,
    chunk_count: int,
    model: str,
    rag_cached: bool,
) -> dict:
    return {
        "rag_s": round(t_rag - t_start, 3),
        "llm_first_token_s": round(t_llm_first - t_rag, 3),
        "llm_total_s": round(t_llm_end - t_rag, 3),
        "total_s": round(t_llm_end - t_start, 3),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "chunks": chunk_count,
        "model": model,
        "rag_cached": rag_cached,
    }


def ask_stream(
    question: str,
    top_k: int | None = None,
    file_type: str | None = None,
    model: str | None = None,
    results: list | None = None,
    *,
    deps: ChainDependencies | None = None,
):
    """Stream answer tokens, then yield sources.

    Yields (type, data) tuples:
      ("sources", list) — serialized sources list (first item)
      ("token", str)   — an answer chunk
    """
    active_deps = deps or _default_dependencies()
    shared = _prepare_common(
        question,
        top_k=top_k,
        file_type=file_type,
        model=model,
        results=results,
        deps=active_deps,
    )
    yield ("sources", [_serialize_source(r) for r in shared["results"]])
    if not shared["results"]:
        tokens_out = active_deps.count_tokens_fn(NO_CONTEXT_MESSAGE)
        yield ("token", NO_CONTEXT_MESSAGE)
        t_now = active_deps.clock_fn()
        yield ("stats", _build_stats(
            t_start=shared["t_start"],
            t_rag=shared["t_rag"],
            t_llm_first=t_now,
            t_llm_end=t_now,
            tokens_in=shared["tokens_in"],
            tokens_out=tokens_out,
            chunk_count=0,
            model=shared["effective_model"],
            rag_cached=shared["rag_cached"],
        ))
        return

    llm = active_deps.build_llm_fn(shared["effective_model"], True)
    chain = _build_prompt() | llm | StrOutputParser()

    answer_chunks = []
    t_llm_first = None
    for chunk in chain.stream({"context": shared["context"], "question": question}):
        if t_llm_first is None:
            t_llm_first = active_deps.clock_fn()
        answer_chunks.append(chunk)
        yield ("token", chunk)
    t_llm = active_deps.clock_fn()
    if t_llm_first is None:
        t_llm_first = t_llm

    answer_text = "".join(answer_chunks)
    tokens_out = active_deps.count_tokens_fn(answer_text)

    yield ("stats", _build_stats(
        t_start=shared["t_start"],
        t_rag=shared["t_rag"],
        t_llm_first=t_llm_first,
        t_llm_end=t_llm,
        tokens_in=shared["tokens_in"],
        tokens_out=tokens_out,
        chunk_count=len(shared["results"]),
        model=shared["effective_model"],
        rag_cached=shared["rag_cached"],
    ))


def ask(
    question: str,
    top_k: int | None = None,
    file_type: str | None = None,
    model: str | None = None,
    results: list | None = None,
    *,
    deps: ChainDependencies | None = None,
) -> dict:
    """Ask a question about the codebase and get an answer with sources."""
    active_deps = deps or _default_dependencies()
    shared = _prepare_common(
        question,
        top_k=top_k,
        file_type=file_type,
        model=model,
        results=results,
        deps=active_deps,
    )
    if not shared["results"]:
        answer = NO_CONTEXT_MESSAGE
        t_llm = active_deps.clock_fn()
        tokens_out = active_deps.count_tokens_fn(answer)
    else:
        llm = active_deps.build_llm_fn(shared["effective_model"], False)
        chain = _build_prompt() | llm | StrOutputParser()
        answer = chain.invoke({"context": shared["context"], "question": question})
        t_llm = active_deps.clock_fn()
        tokens_out = active_deps.count_tokens_fn(answer)

    return {
        "answer": answer,
        "sources": [_serialize_source(r) for r in shared["results"]],
        "stats": _build_stats(
            t_start=shared["t_start"],
            t_rag=shared["t_rag"],
            t_llm_first=t_llm,
            t_llm_end=t_llm,
            tokens_in=shared["tokens_in"],
            tokens_out=tokens_out,
            chunk_count=len(shared["results"]),
            model=shared["effective_model"],
            rag_cached=shared["rag_cached"],
        ),
    }
