"""FastAPI web application for LegacyLens."""

import asyncio
import json
import os

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


async def _send_ws_jsonl_event(websocket: WebSocket, event_type: str, data):
    payload = {"type": event_type, "data": data}
    await websocket.send_text(json.dumps(payload) + "\n")


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

    from legacylens.chain import ask
    try:
        result = await asyncio.to_thread(ask, question, top_k, file_type, model)
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

    if not question.strip():
        async def error_stream():
            yield f"event: error\ndata: {json.dumps('Question is required')}\n\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")

    # Stream from LLM
    from legacylens.chain import ask_stream

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
            gen = ask_stream(question, top_k=top_k, file_type=file_type, model=model)

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

    if not question.strip():
        await _send_ws_jsonl_event(websocket, "error", "Question is required")
        await _send_ws_jsonl_event(websocket, "done", None)
        return

    from legacylens.chain import ask_stream

    _sentinel = object()

    def _next_chunk(gen):
        return next(gen, _sentinel)

    try:
        gen = ask_stream(question, top_k=top_k, file_type=file_type, model=model)

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

    if not query.strip():
        return {"error": "Query is required"}

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
