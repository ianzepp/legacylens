"""LangChain RAG chain for answering questions about COBOL code."""

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from .config import settings
from .retriever import retrieve

SYSTEM_PROMPT = """\
You are LegacyLens, an expert assistant for understanding legacy COBOL codebases.
You answer questions about the AWS CardDemo credit card management application.

Rules:
- Only use the retrieved code context below to answer. Do not make up information.
- Cite sources as [FileName:StartLine-EndLine] when referencing specific code.
- Explain COBOL concepts in plain English when relevant.
- If the context doesn't contain enough information, say so clearly.
- Be concise but thorough.

Retrieved context:
{context}
"""

USER_PROMPT = "{question}"


def _format_context(results: list) -> str:
    """Format retrieved results into context string."""
    parts = []
    for i, r in enumerate(results, 1):
        parts.append(
            f"--- Source {i}: {r.file_path}:{r.start_line}-{r.end_line} "
            f"(score: {r.score:.3f}) ---\n"
            f"{r.preamble}\n\n"
            f"{r.content}\n"
        )
    return "\n".join(parts)


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


def ask(
    question: str,
    top_k: int | None = None,
    file_type: str | None = None,
    model: str | None = None,
) -> dict:
    """Ask a question about the codebase and get an answer with sources."""
    results = retrieve(question, top_k=top_k, file_type=file_type)
    context = _format_context(results)

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", USER_PROMPT),
    ])

    llm = ChatOpenAI(
        model=model or settings.chat_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )

    chain = prompt | llm | StrOutputParser()
    answer = chain.invoke({"context": context, "question": question})

    return {
        "answer": answer,
        "sources": [_serialize_source(r) for r in results],
    }
