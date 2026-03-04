"""WebSocket streaming tests for web UI transport protocol."""

import json

from fastapi.testclient import TestClient

from web.app import app


def _recv_jsonl_event(ws):
    text = ws.receive_text()
    line = text.strip()
    assert line, "expected non-empty JSONL line"
    return json.loads(line)


def test_ws_ask_streams_jsonl_events(monkeypatch):
    def fake_ask_stream(_question, top_k=None, file_type=None, model=None):
        assert top_k == 7
        assert file_type == "cbl"
        assert model == "x-model"
        yield ("sources", [{"file_name": "FOO.cbl", "start_line": 1, "end_line": 2, "name": "MAIN", "score": 0.7}])
        yield ("token", "hello ")
        yield ("token", "world")
        yield ("stats", {"total_s": 1.23, "chunks": 1})

    monkeypatch.setattr("legacylens.chain.ask_stream", fake_ask_stream)

    client = TestClient(app)
    with client.websocket_connect("/ws/ask") as ws:
        ws.send_json({
            "question": "test question",
            "top_k": 7,
            "file_type": "cbl",
            "model": "x-model",
        })

        evt1 = _recv_jsonl_event(ws)
        evt2 = _recv_jsonl_event(ws)
        evt3 = _recv_jsonl_event(ws)
        evt4 = _recv_jsonl_event(ws)
        evt5 = _recv_jsonl_event(ws)
        evt6 = _recv_jsonl_event(ws)
        evt7 = _recv_jsonl_event(ws)

    assert evt1 == {"type": "sources_begin", "data": {"count": 1}}
    assert evt2["type"] == "source"
    assert evt2["data"]["file_name"] == "FOO.cbl"
    assert evt3 == {"type": "sources_end", "data": {"count": 1}}
    assert evt4 == {"type": "token", "data": "hello "}
    assert evt5 == {"type": "token", "data": "world"}
    assert evt6 == {"type": "stats", "data": {"total_s": 1.23, "chunks": 1}}
    assert evt7 == {"type": "done", "data": None}


def test_ws_ask_requires_question():
    client = TestClient(app)
    with client.websocket_connect("/ws/ask") as ws:
        ws.send_json({"question": "   "})
        evt1 = _recv_jsonl_event(ws)
        evt2 = _recv_jsonl_event(ws)

    assert evt1 == {"type": "error", "data": "Question is required"}
    assert evt2 == {"type": "done", "data": None}
