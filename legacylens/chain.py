"""LangChain RAG chain for answering questions about COBOL code."""

import os
import time

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


def ask_stream(
    question: str,
    top_k: int | None = None,
    file_type: str | None = None,
    model: str | None = None,
    results: list | None = None,
):
    """Stream answer tokens, then yield sources.

    Yields (type, data) tuples:
      ("token", str)   — an answer chunk
      ("sources", list) — serialized sources list (final item)
    """
    t_start = time.perf_counter()
    rag_cached = results is not None
    if results is None:
        results = retrieve(question, top_k=top_k, file_type=file_type)
    t_rag = time.perf_counter()
    context = _format_context(results)

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", USER_PROMPT),
    ])

    effective_model = model or settings.chat_model
    input_text = SYSTEM_PROMPT.replace("{context}", context) + question
    tokens_in = _count_tokens(input_text)

    llm = _build_llm(effective_model, streaming=True)

    chain = prompt | llm | StrOutputParser()
    answer_chunks = []
    t_llm_first = None
    for chunk in chain.stream({"context": context, "question": question}):
        if t_llm_first is None:
            t_llm_first = time.perf_counter()
        answer_chunks.append(chunk)
        yield ("token", chunk)
    t_llm = time.perf_counter()
    if t_llm_first is None:
        t_llm_first = t_llm

    answer_text = "".join(answer_chunks)
    tokens_out = _count_tokens(answer_text)

    yield ("sources", [_serialize_source(r) for r in results])
    yield ("stats", {
        "rag_s": round(t_rag - t_start, 3),
        "llm_first_token_s": round(t_llm_first - t_rag, 3),
        "llm_total_s": round(t_llm - t_rag, 3),
        "total_s": round(t_llm - t_start, 3),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "chunks": len(results),
        "model": effective_model,
        "rag_cached": rag_cached,
    })


def ask(
    question: str,
    top_k: int | None = None,
    file_type: str | None = None,
    model: str | None = None,
    results: list | None = None,
) -> dict:
    """Ask a question about the codebase and get an answer with sources."""
    t_start = time.perf_counter()
    rag_cached = results is not None
    if results is None:
        results = retrieve(question, top_k=top_k, file_type=file_type)
    t_rag = time.perf_counter()
    context = _format_context(results)

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", USER_PROMPT),
    ])

    effective_model = model or settings.chat_model
    input_text = SYSTEM_PROMPT.replace("{context}", context) + question
    tokens_in = _count_tokens(input_text)

    llm = _build_llm(effective_model)

    chain = prompt | llm | StrOutputParser()
    answer = chain.invoke({"context": context, "question": question})
    t_llm = time.perf_counter()

    tokens_out = _count_tokens(answer)

    return {
        "answer": answer,
        "sources": [_serialize_source(r) for r in results],
        "stats": {
            "rag_s": round(t_rag - t_start, 3),
            "llm_first_token_s": round(t_llm - t_rag, 3),
            "llm_total_s": round(t_llm - t_rag, 3),
            "total_s": round(t_llm - t_start, 3),
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "chunks": len(results),
            "model": effective_model,
            "rag_cached": rag_cached,
        },
    }
