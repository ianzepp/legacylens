"""API regression tests for verbosity, L1 cache routing, and summary metadata."""

from fastapi.testclient import TestClient

from legacylens.models import QueryResult
from web.app import app


def test_api_ask_forwards_verbosity(monkeypatch):
    captured = {}

    def fake_ask(
        question,
        top_k=None,
        file_type=None,
        model=None,
        results=None,
        verbosity=None,
        trim_context=None,
    ):
        captured["question"] = question
        captured["top_k"] = top_k
        captured["file_type"] = file_type
        captured["model"] = model
        captured["results"] = results
        captured["verbosity"] = verbosity
        captured["trim_context"] = trim_context
        return {"answer": "ok", "sources": [], "stats": {}}

    monkeypatch.setattr("legacylens.chain.ask", fake_ask)

    client = TestClient(app)
    resp = client.post("/api/ask", json={
        "question": "Explain this.",
        "top_k": 7,
        "file_type": "cbl",
        "model": "x-model",
        "verbosity": "detailed",
    })

    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "ok"
    assert captured["verbosity"] == "detailed"
    assert captured["trim_context"] is True
    assert captured["top_k"] == 7
    assert captured["file_type"] == "cbl"
    assert captured["model"] == "x-model"


def test_api_search_uses_l1_cache_when_enabled(monkeypatch):
    cached = [{"file_name": "CACHED.cbl", "start_line": 1, "end_line": 2, "summary": "cached summary"}]
    cache_calls = {"count": 0}

    def fake_get_cached_results(query, top_k, file_type):
        cache_calls["count"] += 1
        assert query == "find cached"
        assert top_k == 5
        assert file_type is None
        return cached

    def fail_retrieve(*_args, **_kwargs):
        raise AssertionError("retrieve should not run when L1 cache is enabled and hit")

    monkeypatch.setattr("web.app._get_cached_results", fake_get_cached_results)
    monkeypatch.setattr("legacylens.retriever.retrieve", fail_retrieve)

    client = TestClient(app)
    resp = client.post("/api/search", json={
        "query": "find cached",
        "top_k": 5,
        "l1_cache": True,
    })

    assert resp.status_code == 200
    body = resp.json()
    assert body["results"] == cached
    assert cache_calls["count"] == 1


def test_api_search_includes_summary_in_live_results(monkeypatch):
    sample = QueryResult(
        content="MOVE A TO B.",
        file_path="/tmp/FOO.cbl",
        file_name="FOO.cbl",
        file_type="cbl",
        chunk_type="paragraph",
        name="1000-MAIN",
        start_line=10,
        end_line=20,
        score=0.9,
        preamble="File: FOO.cbl",
        summary="Main paragraph that moves input into output.",
    )

    monkeypatch.setattr("legacylens.retriever.retrieve", lambda *_args, **_kwargs: [sample])

    client = TestClient(app)
    resp = client.post("/api/search", json={
        "query": "find live",
        "top_k": 5,
        "l1_cache": False,
    })

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["results"]) == 1
    assert body["results"][0]["file_name"] == "FOO.cbl"
    assert body["results"][0]["summary"] == "Main paragraph that moves input into output."
