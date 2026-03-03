"""FastAPI web application for LegacyLens."""

import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

load_dotenv()

app = FastAPI(title="LegacyLens", description="Query legacy COBOL codebases")
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

# Pre-computed search cache for suggestion queries
_search_cache: dict[str, list[dict]] = {}
_cache_file = os.path.join(os.path.dirname(__file__), "cache", "search_cache.json")
if os.path.isfile(_cache_file):
    with open(_cache_file) as _f:
        _search_cache = json.load(_f)

# In-memory LLM answer cache, keyed by (question, model)
_ask_cache: dict[tuple[str, str], dict] = {}


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

    if not question.strip():
        return {"error": "Question is required"}

    # Check LLM answer cache (keyed by question + model)
    from legacylens.config import settings
    effective_model = model or settings.chat_model
    cache_key = (question, effective_model)
    if cache_key in _ask_cache and not file_type:
        return _ask_cache[cache_key]

    from legacylens.chain import ask
    from legacylens.models import QueryResult

    cached = _get_cached_results(question, top_k, file_type)
    if cached is not None:
        results = [QueryResult(**r) for r in cached]
        result = ask(question, top_k=top_k, file_type=file_type, model=model, results=results)
    else:
        result = ask(question, top_k=top_k, file_type=file_type, model=model)

    # Cache the LLM answer for future requests
    if not file_type:
        _ask_cache[cache_key] = result

    return result


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
