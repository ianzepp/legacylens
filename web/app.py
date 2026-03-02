"""FastAPI web application for LegacyLens."""

import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

load_dotenv()

app = FastAPI(title="LegacyLens", description="Query legacy COBOL codebases")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))


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

    result = ask(question, top_k=top_k, file_type=file_type, model=model)
    return result


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
