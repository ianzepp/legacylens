"""Unit tests for refactored testability seams."""

from types import SimpleNamespace

import legacylens.chain as chain_mod
import legacylens.cli as cli_mod
import legacylens.embeddings as embeddings_mod
import legacylens.vectorstore as vectorstore_mod
from legacylens.chain import ChainDependencies, ask, ask_stream
from legacylens.models import QueryResult


class _FakeChain:
    def __init__(self, llm):
        self._llm = llm

    def invoke(self, _payload):
        return self._llm.answer

    def stream(self, _payload):
        for chunk in self._llm.chunks:
            yield chunk


class _FakePromptAfterLlm:
    def __init__(self, llm):
        self._llm = llm

    def __or__(self, _parser):
        return _FakeChain(self._llm)


class _FakePrompt:
    def __or__(self, llm):
        return _FakePromptAfterLlm(llm)


def _sample_result():
    return QueryResult(
        content="MOVE A TO B.",
        file_path="/tmp/FOO.cbl",
        file_name="FOO.cbl",
        file_type="cbl",
        chunk_type="paragraph",
        name="1000-MAIN",
        start_line=10,
        end_line=20,
        score=0.93,
        preamble="File: FOO.cbl",
    )


class TestChainDependencySeams:
    def test_ask_uses_injected_dependencies(self, monkeypatch):
        monkeypatch.setattr(chain_mod, "_build_prompt", lambda: _FakePrompt())
        calls = {"retrieve": 0}

        def retrieve_fn(_question, **_kwargs):
            calls["retrieve"] += 1
            return [_sample_result()]

        deps = ChainDependencies(
            retrieve_fn=retrieve_fn,
            build_llm_fn=lambda _model, _streaming: SimpleNamespace(answer="answer-text", chunks=[]),
            count_tokens_fn=lambda text: len(text),
            clock_fn=lambda: 100.0,
        )

        out = ask("what", deps=deps)
        assert out["answer"] == "answer-text"
        assert out["sources"][0]["file_name"] == "FOO.cbl"
        assert out["stats"]["rag_cached"] is False
        assert out["stats"]["tokens_out"] == len("answer-text")
        assert calls["retrieve"] == 1

    def test_ask_stream_uses_cached_results_without_retrieval(self, monkeypatch):
        monkeypatch.setattr(chain_mod, "_build_prompt", lambda: _FakePrompt())
        deps = ChainDependencies(
            retrieve_fn=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("retrieve should not run")),
            build_llm_fn=lambda _model, _streaming: SimpleNamespace(answer="", chunks=["A", "B"]),
            count_tokens_fn=lambda text: len(text),
            clock_fn=lambda: 200.0,
        )

        events = list(ask_stream("what", results=[_sample_result()], deps=deps))
        assert events[0][0] == "sources"
        assert events[1] == ("token", "A")
        assert events[2] == ("token", "B")
        assert events[3][0] == "stats"
        assert events[3][1]["rag_cached"] is True

    def test_ask_returns_no_context_message_when_no_results(self):
        deps = ChainDependencies(
            retrieve_fn=lambda *_args, **_kwargs: [],
            build_llm_fn=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("llm should not run")),
            count_tokens_fn=lambda text: len(text),
            clock_fn=lambda: 300.0,
        )
        out = ask("missing", deps=deps)
        assert "could not retrieve any relevant code chunks" in out["answer"].lower()
        assert out["stats"]["chunks"] == 0

    def test_ask_stream_returns_no_context_message_when_no_results(self, monkeypatch):
        monkeypatch.setattr(chain_mod, "_build_prompt", lambda: _FakePrompt())
        deps = ChainDependencies(
            retrieve_fn=lambda *_args, **_kwargs: [],
            build_llm_fn=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("llm should not run")),
            count_tokens_fn=lambda text: len(text),
            clock_fn=lambda: 400.0,
        )
        events = list(ask_stream("missing", deps=deps))
        assert events[0] == ("sources", [])
        assert events[1][0] == "token"
        assert "could not retrieve any relevant code chunks" in events[1][1].lower()
        assert events[2][0] == "stats"
        assert events[2][1]["chunks"] == 0


class TestCliHelpers:
    def test_run_ask_formats_output(self):
        lines = []
        cli_mod._run_ask(
            question="q",
            top_k=3,
            file_type=None,
            ask_fn=lambda *_args, **_kwargs: {
                "answer": "hello",
                "sources": [{"file_name": "FOO.cbl", "start_line": 1, "end_line": 2, "name": "MAIN", "score": 0.5}],
            },
            echo=lines.append,
        )
        assert lines[0].startswith("Querying:")
        assert "hello" in lines
        assert any("FOO.cbl:1-2" in line for line in lines)

    def test_run_search_prints_result_rows(self):
        lines = []
        cli_mod._run_search(
            query="q",
            top_k=2,
            file_type="cbl",
            retrieve_fn=lambda *_args, **_kwargs: [_sample_result()],
            echo=lines.append,
        )
        assert any("Result 1" in line for line in lines)
        assert any("File: FOO.cbl:10-20" in line for line in lines)

    def test_run_ingest_supports_clean_mode(self):
        lines = []
        state = {"deleted": 0}

        cli_mod._run_ingest(
            path="/tmp/x",
            clean=True,
            delete_namespace_fn=lambda: state.__setitem__("deleted", state["deleted"] + 1),
            ingest_fn=lambda *_args, **_kwargs: {"files": 1, "chunks": 2, "vectors": 3},
            echo=lines.append,
        )
        assert state["deleted"] == 1
        assert any("Done: 1 files, 2 chunks, 3 vectors" in line for line in lines)


class TestEmbeddingClientInjection:
    def test_openai_path_uses_client_factory_and_batches(self):
        calls = []

        class FakeClient:
            class embeddings:
                @staticmethod
                def create(*, model, input, dimensions):
                    calls.append((model, tuple(input), dimensions))
                    return SimpleNamespace(data=[SimpleNamespace(embedding=[float(i)]) for i, _ in enumerate(input)])

        out = embeddings_mod.get_embeddings(
            ["a", "b", "c"],
            batch_size=2,
            use_ollama=False,
            client_factory=lambda **_kwargs: FakeClient(),
        )
        assert len(calls) == 2
        assert len(out) == 3

    def test_ollama_path_uses_client_factory(self):
        called = {"yes": 0}

        class FakeClient:
            class embeddings:
                @staticmethod
                def create(*, model, input):
                    called["yes"] += 1
                    assert model
                    return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1]) for _ in input])

        out = embeddings_mod.get_embeddings(
            ["a"],
            use_ollama=True,
            client_factory=lambda **_kwargs: FakeClient(),
        )
        assert called["yes"] == 1
        assert out == [[0.1]]


class TestVectorstoreHelpers:
    def test_build_filter_dict(self):
        filt = vectorstore_mod._build_filter_dict(
            file_type_filter="cbl",
            metadata_filters={"name": "MAIN", "empty": ""},
        )
        assert filt == {"file_type": {"$eq": "cbl"}, "name": {"$eq": "MAIN"}}
        assert vectorstore_mod._build_filter_dict() is None

    def test_get_index_uses_model_based_creation_for_integrated_provider(self):
        created = {"model": 0, "dense": 0}

        class FakePinecone:
            def __init__(self, **_kwargs):
                pass

            @staticmethod
            def list_indexes():
                return []

            @staticmethod
            def create_index_for_model(**_kwargs):
                created["model"] += 1

            @staticmethod
            def create_index(**_kwargs):
                created["dense"] += 1

            @staticmethod
            def Index(name):
                return {"name": name}

        cfg = SimpleNamespace(
            pinecone_api_key="k",
            pinecone_index_name="idx",
            embedding_provider="pinecone",
            pinecone_model="llama-text-embed-v2",
            embedding_dimensions=1536,
            pinecone_namespace="ns",
            top_k=5,
        )
        out = vectorstore_mod.get_index(settings_obj=cfg, pinecone_factory=FakePinecone)
        assert out["name"] == "idx"
        assert created["model"] == 1
        assert created["dense"] == 0
