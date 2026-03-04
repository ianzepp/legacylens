"""Tests for web L2 cache key behavior."""

from web.app import _make_ask_cache_key


def test_cache_key_changes_when_l1_toggle_changes():
    on_key = _make_ask_cache_key("Q", "gpt-4o-mini", 5, None, True)
    off_key = _make_ask_cache_key("Q", "gpt-4o-mini", 5, None, False)
    assert on_key != off_key


def test_cache_key_changes_when_top_k_changes():
    k5 = _make_ask_cache_key("Q", "gpt-4o-mini", 5, None, True)
    k10 = _make_ask_cache_key("Q", "gpt-4o-mini", 10, None, True)
    assert k5 != k10


def test_cache_key_includes_file_type_filter():
    cbl = _make_ask_cache_key("Q", "gpt-4o-mini", 5, "cbl", True)
    all_files = _make_ask_cache_key("Q", "gpt-4o-mini", 5, None, True)
    assert cbl != all_files
