"""Run ingestion benchmarks: discover -> chunk -> embed -> upsert.

Measures throughput for the full ingestion pipeline across different
embedding model configs using temporary Pinecone indexes.

Usage:
    python benchmarks/run_ingest_benchmark.py
    python benchmarks/run_ingest_benchmark.py --configs llama,e5
    python benchmarks/run_ingest_benchmark.py --strategies paragraph
    python benchmarks/run_ingest_benchmark.py --keep-indexes
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from benchmarks.config import CONFIGS, BenchmarkConfig
from benchmarks.ingest_all import (
    NAMESPACE,
    _wait_for_index,
    create_index,
    ingest_openai,
    ingest_pinecone_integrated,
)
from legacylens.chunker import chunk_file
from legacylens.config import settings
from legacylens.ingest import discover_files

RESULTS_DIR = Path(__file__).resolve().parent / "results"
LOC_TARGET = 10_000
TIME_TARGET_S = 5 * 60  # 5 minutes


def _dedup_configs(configs: list[BenchmarkConfig]) -> list[BenchmarkConfig]:
    """Deduplicate configs by ingestion-relevant fields.

    Rerank/hybrid configs share the same ingestion path as their base,
    so we keep only one config per unique
    (embedding_provider, embedding_model, embedding_dimensions, chunking_strategy).
    """
    seen: set[tuple] = set()
    unique: list[BenchmarkConfig] = []
    for c in configs:
        key = (c.embedding_provider, c.embedding_model, c.embedding_dimensions, c.chunking_strategy)
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def _filter_configs(
    configs: list[BenchmarkConfig],
    name_filters: list[str] | None,
    strategy_filters: list[str] | None,
) -> list[BenchmarkConfig]:
    """Filter configs by name substring and/or chunking strategy."""
    result = configs
    if name_filters:
        result = [c for c in result if any(f in c.name for f in name_filters)]
    if strategy_filters:
        result = [c for c in result if c.chunking_strategy in strategy_filters]
    return result


def _count_loc(file_path: str) -> int:
    """Count non-blank lines in a file."""
    try:
        with open(file_path, "r", errors="replace") as f:
            return sum(1 for line in f if line.strip())
    except Exception:
        return 0


def _temp_index_name(config: BenchmarkConfig) -> str:
    """Generate a temporary index name for benchmarking."""
    ts = int(time.time())
    short = config.name[:30]
    return f"ingest-bench-{short}-{ts}"


def run_ingest_benchmark(
    configs: list[BenchmarkConfig],
    keep_indexes: bool = False,
) -> list[dict]:
    """Run the ingestion benchmark for each config."""
    from pinecone import Pinecone

    pc = Pinecone(api_key=settings.pinecone_api_key)

    # Phase 1: Discovery
    print("\n--- Phase 1: Discovery ---")
    t0 = time.perf_counter()
    all_files = discover_files(settings.carddemo_path)
    discover_time = time.perf_counter() - t0

    total_loc = sum(_count_loc(f) for f in all_files)
    print(f"  Found {len(all_files)} files, {total_loc:,} LOC in {discover_time:.2f}s")

    # Phase 2: Chunking (cache by strategy)
    print("\n--- Phase 2: Chunking ---")
    chunks_by_strategy: dict[str, list] = {}
    chunk_times: dict[str, float] = {}

    strategies_needed = {c.chunking_strategy for c in configs}
    for strategy in sorted(strategies_needed):
        t0 = time.perf_counter()
        chunks = []
        errors = 0
        for f in all_files:
            try:
                chunks.extend(chunk_file(f, strategy=strategy))
            except Exception as e:
                errors += 1
                print(f"  ERROR chunking {Path(f).name}: {e}")
        elapsed = time.perf_counter() - t0
        chunks_by_strategy[strategy] = chunks
        chunk_times[strategy] = elapsed
        print(f"  Strategy '{strategy}': {len(chunks)} chunks in {elapsed:.2f}s ({errors} errors)")

    # Phase 3+4: Index create + embed/upsert per config
    results = []

    for config in configs:
        temp_name = _temp_index_name(config)
        # Patch config to use temp index name
        original_index = config.index_name
        config.index_name = temp_name

        print(f"\n--- Config: {config.name} ---")
        print(f"  Provider: {config.embedding_provider}, Model: {config.embedding_model}")
        print(f"  Dims: {config.embedding_dimensions}, Chunking: {config.chunking_strategy}")
        print(f"  Temp index: {temp_name}")

        chunks = chunks_by_strategy[config.chunking_strategy]
        chunk_time = chunk_times[config.chunking_strategy]
        status = "PASS"
        error_msg = ""
        index_create_time = 0.0
        embed_upsert_time = 0.0

        try:
            # Create temp index
            t0 = time.perf_counter()
            create_index(pc, config, clean=True)
            index_create_time = time.perf_counter() - t0
            print(f"  Index created in {index_create_time:.2f}s")

            # Embed + upsert
            t0 = time.perf_counter()
            if config.is_pinecone_integrated:
                ingest_pinecone_integrated(pc, config, chunks)
            else:
                ingest_openai(pc, config, chunks)
            embed_upsert_time = time.perf_counter() - t0
            print(f"  Embed+upsert in {embed_upsert_time:.2f}s")

        except Exception as e:
            status = "FAIL"
            error_msg = str(e)
            print(f"  ERROR: {e}")

        finally:
            # Restore original index name
            config.index_name = original_index

            # Cleanup temp index
            if not keep_indexes:
                try:
                    pc.delete_index(temp_name)
                    print(f"  Deleted temp index {temp_name}")
                except Exception:
                    print(f"  WARNING: Could not delete temp index {temp_name}")

        # Compute throughput
        pipeline_time = discover_time + chunk_time + embed_upsert_time
        loc_per_s = total_loc / pipeline_time if pipeline_time > 0 else 0
        chunks_per_s = len(chunks) / pipeline_time if pipeline_time > 0 else 0
        meets_target = (total_loc >= LOC_TARGET and pipeline_time <= TIME_TARGET_S) if status == "PASS" else False

        result = {
            "config": config.name,
            "embedding_provider": config.embedding_provider,
            "embedding_model": config.embedding_model,
            "embedding_dimensions": config.embedding_dimensions,
            "chunking_strategy": config.chunking_strategy,
            "files": len(all_files),
            "total_loc": total_loc,
            "chunks": len(chunks),
            "discover_time_s": round(discover_time, 3),
            "chunk_time_s": round(chunk_time, 3),
            "index_create_time_s": round(index_create_time, 3),
            "embed_upsert_time_s": round(embed_upsert_time, 3),
            "pipeline_time_s": round(pipeline_time, 3),
            "loc_per_s": round(loc_per_s, 1),
            "chunks_per_s": round(chunks_per_s, 1),
            "meets_target": meets_target,
            "status": status,
            "error": error_msg,
        }
        results.append(result)

    return results


def print_summary(results: list[dict]):
    """Print a console summary table."""
    print(f"\n{'='*120}")
    print("INGESTION BENCHMARK RESULTS")
    print(f"{'='*120}")

    header = (
        f"{'Config':<35} {'Provider':<9} {'Dims':>5} {'Chunk':<10} "
        f"{'Files':>5} {'LOC':>7} {'Chunks':>6} "
        f"{'Disc':>6} {'Chunk':>6} {'Idx':>6} {'E+U':>7} {'Total':>7} "
        f"{'LOC/s':>8} {'C/s':>7} {'Result':>6}"
    )
    print(header)
    print("-" * 120)

    for r in results:
        verdict = "PASS" if r["meets_target"] else r["status"]
        print(
            f"{r['config']:<35} {r['embedding_provider']:<9} {r['embedding_dimensions']:>5} "
            f"{r['chunking_strategy']:<10} "
            f"{r['files']:>5} {r['total_loc']:>7,} {r['chunks']:>6} "
            f"{r['discover_time_s']:>5.1f}s {r['chunk_time_s']:>5.1f}s "
            f"{r['index_create_time_s']:>5.1f}s {r['embed_upsert_time_s']:>6.1f}s "
            f"{r['pipeline_time_s']:>6.1f}s "
            f"{r['loc_per_s']:>7.0f} {r['chunks_per_s']:>6.0f} "
            f"{verdict:>6}"
        )

    print(f"\nTarget: {LOC_TARGET:,}+ LOC in <{TIME_TARGET_S}s ({TIME_TARGET_S // 60} min)")


def save_results(results: list[dict]):
    """Save results as JSON and CSV."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # JSON
    json_path = RESULTS_DIR / f"ingest_benchmark_{timestamp}.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nJSON results: {json_path}")

    # CSV
    csv_path = RESULTS_DIR / f"ingest_benchmark_{timestamp}.csv"
    with open(csv_path, "w") as f:
        headers = [
            "config", "embedding_provider", "embedding_model", "embedding_dimensions",
            "chunking_strategy", "files", "total_loc", "chunks",
            "discover_time_s", "chunk_time_s", "index_create_time_s", "embed_upsert_time_s",
            "pipeline_time_s", "loc_per_s", "chunks_per_s", "meets_target", "status",
        ]
        f.write(",".join(headers) + "\n")
        for r in results:
            row = [str(r[h]) for h in headers]
            f.write(",".join(row) + "\n")
    print(f"CSV results:  {csv_path}")


def main():
    parser = argparse.ArgumentParser(description="Run LegacyLens ingestion benchmarks")
    parser.add_argument(
        "--configs",
        help="Comma-separated config name substrings to include (e.g. 'llama,e5')",
    )
    parser.add_argument(
        "--strategies",
        help="Comma-separated chunking strategies to include (e.g. 'paragraph')",
    )
    parser.add_argument(
        "--keep-indexes",
        action="store_true",
        help="Do not delete temporary indexes after benchmarking",
    )
    args = parser.parse_args()

    # Validate env
    if not settings.pinecone_api_key:
        print("ERROR: PINECONE_API_KEY must be set")
        sys.exit(1)
    if not settings.carddemo_path:
        print("ERROR: CARDDEMO_PATH must be set")
        sys.exit(1)

    # Filter and deduplicate configs
    name_filters = [f.strip() for f in args.configs.split(",")] if args.configs else None
    strategy_filters = [s.strip() for s in args.strategies.split(",")] if args.strategies else None

    configs = _dedup_configs(CONFIGS)
    configs = _filter_configs(configs, name_filters, strategy_filters)

    if not configs:
        print("No matching configs after filtering.")
        print(f"Available (deduplicated): {', '.join(c.name for c in _dedup_configs(CONFIGS))}")
        sys.exit(1)

    # Check for OpenAI key if needed
    needs_openai = any(not c.is_pinecone_integrated for c in configs)
    if needs_openai and not settings.openai_api_key:
        print("ERROR: OPENAI_API_KEY must be set for OpenAI embedding configs")
        sys.exit(1)

    print(f"Ingestion Benchmark: {len(configs)} unique configs")
    for c in configs:
        print(f"  - {c.name} ({c.embedding_provider}/{c.embedding_model}, {c.chunking_strategy})")

    results = run_ingest_benchmark(configs, keep_indexes=args.keep_indexes)
    print_summary(results)
    save_results(results)


if __name__ == "__main__":
    main()
