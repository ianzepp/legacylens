"""FastAPI web application for LegacyLens."""

import asyncio
import hashlib
import json
import logging
import os
import threading
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

load_dotenv()

app = FastAPI(title="LegacyLens", description="Query legacy COBOL codebases")
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))
logger = logging.getLogger(__name__)
CACHE_DIR = Path(__file__).resolve().parent / "cache" / "search"

_warmup_started = False
_warmup_lock = threading.Lock()


def _claim_warmup_slot() -> bool:
    global _warmup_started
    with _warmup_lock:
        if _warmup_started:
            return False
        _warmup_started = True
        return True


def _run_llm_warmup():
    """Warm the chat model with the existing system prompt and a synthetic user message."""
    from legacylens.chain import ask
    from legacylens.models import QueryResult

    warmup_result = QueryResult(
        content="WARMUP-CONTEXT.",
        file_path="warmup://synthetic",
        file_name="WARMUP.cbl",
        file_type="cbl",
        chunk_type="paragraph",
        name="WARMUP",
        start_line=1,
        end_line=1,
        score=1.0,
        preamble="File: WARMUP.cbl\nParagraph: WARMUP (lines 1-1)",
    )

    try:
        ask(
            "Warmup ping. Ignore this request and respond briefly.",
            top_k=1,
            results=[warmup_result],
        )
    except Exception as exc:
        # Warmup is opportunistic and should never fail the user request path.
        logger.debug("LLM warmup skipped/failed: %s", exc)


def _trigger_llm_warmup_once():
    if not _claim_warmup_slot():
        return
    loop = asyncio.get_running_loop()
    loop.create_task(asyncio.to_thread(_run_llm_warmup))


def _is_truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _cache_file_for_query(query: str) -> Path:
    digest = hashlib.sha256(query.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def _get_cached_results(query: str, top_k: int, file_type: str | None) -> list[dict] | None:
    """Return cached search results if present and request is cache-eligible."""
    if file_type:
        return None

    cache_file = _cache_file_for_query(query)
    if not cache_file.is_file():
        return None

    try:
        with cache_file.open(encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as exc:
        logger.debug("L1 cache read failed for %s: %s", cache_file, exc)
        return None

    if payload.get("query") != query:
        logger.debug("L1 cache hash collision/mismatch for %s", cache_file)
        return None

    results = payload.get("results")
    if not isinstance(results, list):
        return None

    try:
        k = int(top_k)
    except (TypeError, ValueError):
        k = 10
    return results[:k]


async def _send_ws_jsonl_event(websocket: WebSocket, event_type: str, data):
    payload = {"type": event_type, "data": data}
    await websocket.send_text(json.dumps(payload) + "\n")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    _trigger_llm_warmup_once()
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/ask")
async def api_ask(request: Request):
    body = await request.json()
    question = body.get("question", "")
    top_k = body.get("top_k", 10)
    file_type = body.get("file_type") or None
    model = body.get("model") or None
    verbosity = body.get("verbosity") or None
    use_l1 = _is_truthy(body.get("l1_cache", False))
    use_l1_trim = _is_truthy(body.get("l1_trim", True))

    if not question.strip():
        return {"error": "Question is required"}

    from legacylens.chain import ask
    from legacylens.models import QueryResult
    try:
        cached = _get_cached_results(question, top_k, file_type) if use_l1 else None
        ask_kwargs = {
            "top_k": top_k,
            "file_type": file_type,
            "model": model,
            "verbosity": verbosity,
            "trim_context": use_l1_trim,
        }
        if cached is not None:
            ask_kwargs["results"] = [QueryResult(**r) for r in cached]
            result = await asyncio.to_thread(ask, question, **ask_kwargs)
        else:
            result = await asyncio.to_thread(ask, question, **ask_kwargs)
    except Exception as exc:
        return {"error": str(exc), "sources": []}

    return result


@app.post("/api/ask/stream")
async def api_ask_stream(request: Request):
    body = await request.json()
    question = body.get("question", "")
    top_k = body.get("top_k", 10)
    file_type = body.get("file_type") or None
    model = body.get("model") or None
    verbosity = body.get("verbosity") or None
    use_l1 = _is_truthy(body.get("l1_cache", False))
    use_l1_trim = _is_truthy(body.get("l1_trim", True))

    if not question.strip():
        async def error_stream():
            yield f"event: error\ndata: {json.dumps('Question is required')}\n\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")

    # Stream from LLM
    from legacylens.chain import ask_stream
    from legacylens.models import QueryResult

    cached = _get_cached_results(question, top_k, file_type) if use_l1 else None
    results = [QueryResult(**r) for r in cached] if cached is not None else None

    _sentinel = object()

    def _next_chunk(gen):
        """Wrapper around next() that returns a sentinel instead of raising StopIteration.

        StopIteration cannot propagate through asyncio.to_thread into an async
        generator — Python converts it to RuntimeError, silently killing the stream.
        """
        return next(gen, _sentinel)

    async def event_stream():
        sources = []
        stats = {}
        try:
            stream_kwargs = {"top_k": top_k, "file_type": file_type, "model": model}
            if results is not None:
                stream_kwargs["results"] = results
            if verbosity is not None:
                stream_kwargs["verbosity"] = verbosity
            stream_kwargs["trim_context"] = use_l1_trim
            gen = ask_stream(question, **stream_kwargs)

            while True:
                result = await asyncio.to_thread(_next_chunk, gen)
                if result is _sentinel:
                    break
                typ, data = result
                if typ == "token":
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

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.websocket("/ws/ask")
async def ws_ask(websocket: WebSocket):
    await websocket.accept()

    try:
        body = await websocket.receive_json()
    except Exception:
        await _send_ws_jsonl_event(websocket, "error", "Invalid JSON payload")
        await _send_ws_jsonl_event(websocket, "done", None)
        return

    question = body.get("question", "")
    top_k = body.get("top_k", 10)
    file_type = body.get("file_type") or None
    model = body.get("model") or None
    verbosity = body.get("verbosity") or None
    use_l1 = _is_truthy(body.get("l1_cache", False))
    use_l1_trim = _is_truthy(body.get("l1_trim", True))

    if not question.strip():
        await _send_ws_jsonl_event(websocket, "error", "Question is required")
        await _send_ws_jsonl_event(websocket, "done", None)
        return

    from legacylens.chain import ask_stream
    from legacylens.models import QueryResult

    cached = _get_cached_results(question, top_k, file_type) if use_l1 else None
    results = [QueryResult(**r) for r in cached] if cached is not None else None

    _sentinel = object()

    def _next_chunk(gen):
        return next(gen, _sentinel)

    try:
        stream_kwargs = {"top_k": top_k, "file_type": file_type, "model": model}
        if results is not None:
            stream_kwargs["results"] = results
        if verbosity is not None:
            stream_kwargs["verbosity"] = verbosity
        stream_kwargs["trim_context"] = use_l1_trim
        gen = ask_stream(question, **stream_kwargs)

        while True:
            result = await asyncio.to_thread(_next_chunk, gen)
            if result is _sentinel:
                break

            typ, data = result
            if typ == "token":
                await _send_ws_jsonl_event(websocket, "token", data)
            elif typ == "sources":
                sources = data if isinstance(data, list) else []
                await _send_ws_jsonl_event(websocket, "sources_begin", {"count": len(sources)})
                for source in sources:
                    await _send_ws_jsonl_event(websocket, "source", source)
                await _send_ws_jsonl_event(websocket, "sources_end", {"count": len(sources)})
            elif typ == "stats":
                await _send_ws_jsonl_event(websocket, "stats", data)

        await _send_ws_jsonl_event(websocket, "done", None)
        # Keep socket alive briefly so client can acknowledge receipt of `done`
        # before the server side disconnects.
        try:
            ack = await asyncio.wait_for(websocket.receive_json(), timeout=1.5)
            if isinstance(ack, dict) and ack.get("type") == "ack_done":
                return
        except Exception:
            pass
    except WebSocketDisconnect:
        return
    except Exception as exc:
        try:
            await _send_ws_jsonl_event(websocket, "error", str(exc))
            await _send_ws_jsonl_event(websocket, "done", None)
        except Exception:
            pass


@app.post("/api/search")
async def api_search(request: Request):
    body = await request.json()
    query = body.get("query", "")
    top_k = body.get("top_k", 10)
    file_type = body.get("file_type") or None
    use_l1 = _is_truthy(body.get("l1_cache", False))

    if not query.strip():
        return {"error": "Query is required"}

    cached = _get_cached_results(query, top_k, file_type) if use_l1 else None
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
                "summary": r.summary,
                "comments": r.comments,
                "copy_references": r.copy_references,
                "calls_to": r.calls_to,
            }
            for r in results
        ]
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
