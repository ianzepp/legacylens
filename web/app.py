"""FastAPI web application for LegacyLens."""

import asyncio
import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

load_dotenv()

LAYER_1_CACHE = os.environ.get("LAYER_1_CACHE", "true").lower() == "true"
LAYER_2_CACHE = os.environ.get("LAYER_2_CACHE", "true").lower() == "true"

app = FastAPI(title="LegacyLens", description="Query legacy COBOL codebases")
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

# Layer 1: Pre-computed search cache for suggestion queries
_search_cache: dict[str, list[dict]] = {}
if LAYER_1_CACHE:
    _cache_file = os.path.join(os.path.dirname(__file__), "cache", "search_cache.json")
    if os.path.isfile(_cache_file):
        with open(_cache_file) as _f:
            _search_cache = json.load(_f)

# In-memory LLM answer cache, keyed by request settings that can change RAG context.
_ask_cache: dict[tuple[str, str, int, str | None, bool], dict] = {}


def _make_ask_cache_key(
    question: str,
    model: str,
    top_k: int,
    file_type: str | None,
    use_l1: bool,
) -> tuple[str, str, int, str | None, bool]:
    """Build a stable L2 cache key for answer requests."""
    return (question, model, int(top_k), file_type, bool(use_l1))


def _get_cached_results(query: str, top_k: int, file_type: str | None) -> list[dict] | None:
    """Return cached search results if available for this query with default params."""
    if file_type or query not in _search_cache:
        return None
    results = _search_cache[query]
    return results[:top_k]


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/ask")
async def api_ask(request: Request):
    body = await request.json()
    question = body.get("question", "")
    top_k = body.get("top_k", 10)
    file_type = body.get("file_type") or None
    model = body.get("model") or None
    use_l1 = body.get("l1_cache", LAYER_1_CACHE)
    use_l2 = body.get("l2_cache", LAYER_2_CACHE)

    if not question.strip():
        return {"error": "Question is required"}

    # Check LLM answer cache (keyed by question + model)
    from legacylens.config import settings
    effective_model = model or settings.chat_model
    cache_key = _make_ask_cache_key(question, effective_model, top_k, file_type, use_l1)
    if use_l2 and cache_key in _ask_cache and not file_type:
        cached = _ask_cache[cache_key]
        cached_stats = dict(cached.get("stats", {}))
        cached_stats["l2_cached"] = True
        return {**cached, "stats": cached_stats}

    from legacylens.chain import ask
    from legacylens.models import QueryResult

    try:
        cached = _get_cached_results(question, top_k, file_type) if use_l1 else None
        if cached is not None:
            results = [QueryResult(**r) for r in cached]
            result = await asyncio.to_thread(ask, question, top_k, file_type, model, results)
        else:
            result = await asyncio.to_thread(ask, question, top_k, file_type, model)
    except Exception as exc:
        return {"error": str(exc), "sources": []}

    # Cache the LLM answer for future requests
    if use_l2 and not file_type:
        _ask_cache[cache_key] = result

    return result


@app.post("/api/ask/stream")
async def api_ask_stream(request: Request):
    body = await request.json()
    question = body.get("question", "")
    top_k = body.get("top_k", 10)
    file_type = body.get("file_type") or None
    model = body.get("model") or None
    use_l1 = body.get("l1_cache", LAYER_1_CACHE)
    use_l2 = body.get("l2_cache", LAYER_2_CACHE)

    if not question.strip():
        async def error_stream():
            yield f"event: error\ndata: {json.dumps('Question is required')}\n\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")

    from legacylens.config import settings
    effective_model = model or settings.chat_model
    cache_key = _make_ask_cache_key(question, effective_model, top_k, file_type, use_l1)

    # Check Layer 2 cache — stream cached answer as single chunk
    if use_l2 and cache_key in _ask_cache and not file_type:
        cached = _ask_cache[cache_key]

        async def cached_stream():
            yield f"data: {json.dumps(cached['answer'])}\n\n"
            yield f"event: sources\ndata: {json.dumps(cached['sources'])}\n\n"
            cached_stats = cached.get('stats', {})
            cached_stats['l2_cached'] = True
            yield f"event: stats\ndata: {json.dumps(cached_stats)}\n\n"
            yield "event: done\ndata: \n\n"

        return StreamingResponse(cached_stream(), media_type="text/event-stream")

    # Stream from LLM
    from legacylens.chain import ask_stream
    from legacylens.models import QueryResult

    cached_results = _get_cached_results(question, top_k, file_type) if use_l1 else None
    if cached_results is not None:
        results = [QueryResult(**r) for r in cached_results]
    else:
        results = None

    _sentinel = object()

    def _next_chunk(gen):
        """Wrapper around next() that returns a sentinel instead of raising StopIteration.

        StopIteration cannot propagate through asyncio.to_thread into an async
        generator — Python converts it to RuntimeError, silently killing the stream.
        """
        return next(gen, _sentinel)

    async def event_stream():
        full_answer = []
        sources = []
        stats = {}
        try:
            gen = ask_stream(question, top_k=top_k, file_type=file_type, model=model, results=results)

            while True:
                result = await asyncio.to_thread(_next_chunk, gen)
                if result is _sentinel:
                    break
                typ, data = result
                if typ == "token":
                    full_answer.append(data)
                    yield f"data: {json.dumps(data)}\n\n"
                elif typ == "sources":
                    sources = data
                elif typ == "stats":
                    stats = data
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps(str(exc))}\n\n"
            yield "event: done\ndata: \n\n"
            return

        yield f"event: sources\ndata: {json.dumps(sources)}\n\n"
        yield f"event: stats\ndata: {json.dumps(stats)}\n\n"
        yield "event: done\ndata: \n\n"

        # Cache the complete answer
        if use_l2 and not file_type:
            _ask_cache[cache_key] = {"answer": "".join(full_answer), "sources": sources, "stats": stats}

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/search")
async def api_search(request: Request):
    body = await request.json()
    query = body.get("query", "")
    top_k = body.get("top_k", 10)
    file_type = body.get("file_type") or None

    if not query.strip():
        return {"error": "Query is required"}

    cached = _get_cached_results(query, top_k, file_type)
    if cached is not None:
        return {"results": cached}

    from legacylens.retriever import retrieve

    results = retrieve(query, top_k=top_k, file_type=file_type)
    return {
        "results": [
            {
                "file_path": r.file_path,
                "file_name": r.file_name,
                "file_type": r.file_type,
                "name": r.name,
                "chunk_type": r.chunk_type,
                "start_line": r.start_line,
                "end_line": r.end_line,
                "score": r.score,
                "content": r.content,
                "preamble": r.preamble,
                "comments": r.comments,
                "copy_references": r.copy_references,
                "calls_to": r.calls_to,
            }
            for r in results
        ]
    }


@app.get("/api/cache-status")
async def cache_status():
    return {
        "layer_1_enabled": LAYER_1_CACHE,
        "layer_2_enabled": LAYER_2_CACHE,
        "cached_queries": len(_search_cache),
        "cached_answers": len(_ask_cache),
    }


@app.post("/api/file")
async def api_file_context(request: Request):
    body = await request.json()
    file_path = body.get("file_path", "")

    if not file_path:
        return {"error": "file_path is required"}

    if not os.path.isfile(file_path):
        return {"error": f"File not found: {file_path}"}

    with open(file_path, encoding="utf-8", errors="replace") as handle:
        lines = handle.read().splitlines()

    return {
        "file_path": file_path,
        "line_count": len(lines),
        "content": "\n".join(lines[:2000]),
        "truncated": len(lines) > 2000,
    }
