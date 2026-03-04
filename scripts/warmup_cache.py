"""Pre-compute L1 search cache files for suggestion queries.

Runs each query against Pinecone (top_k=10) and saves serialized results
as one JSON file per query under web/cache/search/.

File name: SHA-256 hash of the query text.
Payload: {"query": "...", "top_k_built": 10, "results": [...]}

Usage:
    python scripts/warmup_cache.py
"""

import hashlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from benchmarks.queries_suggestions import QUERIES_SUGGESTIONS
from legacylens.chain import _serialize_source
from legacylens.retriever import retrieve

CACHE_DIR = Path(__file__).resolve().parent.parent / "web" / "cache" / "search"
TOP_K = 10


def _cache_file_for_query(query: str) -> Path:
    digest = hashlib.sha256(query.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    queries = [q.query for q in QUERIES_SUGGESTIONS]
    print(f"Warming up L1 search cache for {len(queries)} queries (top_k={TOP_K})...")
    t0 = time.time()
    written_files = []

    for i, q in enumerate(queries, 1):
        results = retrieve(q, top_k=TOP_K)
        payload = {
            "query": q,
            "top_k_built": TOP_K,
            "results": [_serialize_source(r) for r in results],
        }
        cache_file = _cache_file_for_query(q)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, separators=(",", ":"))
        written_files.append(cache_file)

        elapsed = time.time() - t0
        rate = elapsed / i
        remaining = rate * (len(queries) - i)
        print(f"  [{i}/{len(queries)}] {elapsed:.0f}s elapsed, ~{remaining:.0f}s remaining | {q[:60]}")

    # Remove stale cache files from prior query sets.
    live_files = {p.name for p in written_files}
    stale = 0
    for p in CACHE_DIR.glob("*.json"):
        if p.name not in live_files:
            p.unlink(missing_ok=True)
            stale += 1

    total_size_bytes = sum(os.path.getsize(p) for p in written_files if p.exists())
    size_mb = total_size_bytes / 1024 / 1024
    print(
        f"\nDone in {time.time() - t0:.0f}s. "
        f"Wrote {len(written_files)} files to {CACHE_DIR} ({size_mb:.1f} MB), removed {stale} stale files."
    )


if __name__ == "__main__":
    main()
