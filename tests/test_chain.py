"""Unit tests for the RAG chain module (no API calls)."""

from legacylens.chain import _format_context, _serialize_source
from legacylens.models import QueryResult


def _make_result(**overrides):
    defaults = dict(
        content="MOVE A TO B.",
        file_path="/app/cbl/FOO.cbl",
        file_name="FOO.cbl",
        file_type="cbl",
        chunk_type="paragraph",
        name="1000-PROCESS",
        start_line=100,
        end_line=120,
        score=0.85,
        preamble="File: FOO.cbl\nParagraph: 1000-PROCESS",
        summary="Moves A into B for the main processing step.",
        comments="Process input",
        copy_references=["COPYLIB"],
        calls_to=["PERFORM 2000-DO-STUFF"],
    )
    defaults.update(overrides)
    return QueryResult(**defaults)


class TestFormatContext:
    def test_includes_source_number(self):
        results = [_make_result()]
        ctx = _format_context(results)
        assert "Source 1:" in ctx

    def test_includes_file_and_lines(self):
        results = [_make_result()]
        ctx = _format_context(results)
        assert "FOO.cbl" in ctx
        assert "100" in ctx
        assert "120" in ctx

    def test_includes_score(self):
        results = [_make_result(score=0.912)]
        ctx = _format_context(results)
        assert "0.912" in ctx

    def test_includes_preamble(self):
        results = [_make_result(preamble="File: FOO.cbl\nParagraph: MAIN")]
        ctx = _format_context(results)
        assert "Paragraph: MAIN" in ctx

    def test_includes_summary(self):
        results = [_make_result(summary="This paragraph initializes working storage.")]
        ctx = _format_context(results)
        assert "Summary: This paragraph initializes working storage." in ctx

    def test_includes_content(self):
        results = [_make_result(content="PERFORM 1000-INIT.")]
        ctx = _format_context(results)
        assert "PERFORM 1000-INIT." in ctx

    def test_multiple_results(self):
        results = [_make_result(name="A"), _make_result(name="B")]
        ctx = _format_context(results)
        assert "Source 1:" in ctx
        assert "Source 2:" in ctx

    def test_trims_lower_ranked_source_content(self):
        long_text = "X" * 800
        results = [
            _make_result(name="A", content="short-a"),
            _make_result(name="B", content="short-b"),
            _make_result(name="C", content="short-c"),
            _make_result(name="D", content=long_text),
        ]
        ctx = _format_context(results)
        assert "Source 4:" in ctx
        assert "... [truncated]" in ctx

    def test_empty_results(self):
        ctx = _format_context([])
        assert ctx == ""


class TestSerializeSource:
    def test_all_fields_present(self):
        r = _make_result()
        s = _serialize_source(r)
        assert s["file_path"] == "/app/cbl/FOO.cbl"
        assert s["file_name"] == "FOO.cbl"
        assert s["file_type"] == "cbl"
        assert s["name"] == "1000-PROCESS"
        assert s["start_line"] == 100
        assert s["end_line"] == 120
        assert s["score"] == 0.85
        assert s["chunk_type"] == "paragraph"
        assert s["preamble"] == "File: FOO.cbl\nParagraph: 1000-PROCESS"
        assert s["summary"] == "Moves A into B for the main processing step."
        assert s["content"] == "MOVE A TO B."
        assert s["comments"] == "Process input"
        assert s["copy_references"] == ["COPYLIB"]
        assert s["calls_to"] == ["PERFORM 2000-DO-STUFF"]

    def test_empty_optional_fields(self):
        r = _make_result(preamble="", summary="", comments="", copy_references=[], calls_to=[])
        s = _serialize_source(r)
        assert s["preamble"] == ""
        assert s["summary"] == ""
        assert s["comments"] == ""
        assert s["copy_references"] == []
        assert s["calls_to"] == []
