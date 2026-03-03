"""Phase 1: Run benchmark queries against multiple LLMs and save responses.

Retrieves RAG chunks once per query, then sends the same context to each model.
Measures response latency and saves full answers for grading in Phase 2.

Usage:
    python benchmarks/run_llm_benchmark.py
    python benchmarks/run_llm_benchmark.py --models openai:gpt-4o-mini,anthropic:claude-sonnet-4-20250514
    python benchmarks/run_llm_benchmark.py --max-queries 5
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from benchmarks.config import DEFAULT_QUERY_SET, QUERY_SETS, load_queries
from benchmarks.llm_config import DEFAULT_MODELS, call_llm, parse_model_spec
from legacylens.chain import SYSTEM_PROMPT, _format_context
from legacylens.retriever import retrieve

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def run_llm_benchmark(
    models: list,
    queries: list,
    top_k: int,
    max_queries: int | None = None,
) -> dict:
    """Run Phase 1: retrieve chunks, generate responses from each model."""
    if max_queries:
        queries = queries[:max_queries]

    model_names = [m.name for m in models]
    total = len(models) * len(queries)

    print(f"LLM Benchmark: {len(models)} models x {len(queries)} queries = {total} responses")
    print(f"Models: {', '.join(model_names)}")
    print(f"Top-k: {top_k}")
    print()

    # Phase 1a: Retrieve chunks once per query
    print(f"Retrieving chunks for {len(queries)} queries (top_k={top_k})...")
    query_data = []
    for i, q in enumerate(queries, 1):
        results = retrieve(q.query, top_k=top_k)
        formatted_context = _format_context(results)
        chunk_summaries = [
            {
                "file_name": r.file_name,
                "name": r.name,
                "start_line": r.start_line,
                "end_line": r.end_line,
                "score": round(r.score, 4),
                "chunk_type": r.chunk_type,
            }
            for r in results
        ]
        query_data.append({
            "query": q.query,
            "description": q.description,
            "formatted_context": formatted_context,
            "chunk_summaries": chunk_summaries,
            "responses": [],
        })
        print(f"  [{i}/{len(queries)}] {q.description}")

    # Phase 1b: Generate responses from each model
    print(f"\nGenerating responses...")
    count = 0
    for qd in query_data:
        system_prompt = SYSTEM_PROMPT.replace("{context}", qd["formatted_context"])
        for model in models:
            count += 1
            answer, latency = call_llm(model, system_prompt, qd["query"])
            error = answer if answer.startswith("ERROR:") else None
            qd["responses"].append({
                "model": model.name,
                "provider": model.provider,
                "model_id": model.model_id,
                "latency_s": round(latency, 3),
                "answer": answer,
                "error": error,
            })
            status = f"{latency:.2f}s" if not error else error[:60]
            print(f"  [{count}/{total}] {model.name:<30} | {status} | {qd['description']}")

    return {
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "models_tested": model_names,
            "query_count": len(queries),
            "top_k": top_k,
        },
        "queries": query_data,
    }


def save_results(data: dict, output_dir: Path) -> Path:
    """Save benchmark results as JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"llm_responses_{timestamp}.json"
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"\nResults saved: {json_path}")
    return json_path


def main():
    parser = argparse.ArgumentParser(description="Run LLM answer quality benchmark (Phase 1)")
    parser.add_argument(
        "--models",
        help="Comma-separated provider:model_id specs (e.g. openai:gpt-4o-mini,anthropic:claude-sonnet-4-20250514)",
    )
    parser.add_argument("--top-k", type=int, default=10, help="Number of chunks to retrieve (default: 10)")
    parser.add_argument("--max-queries", type=int, help="Limit number of queries (for testing)")
    parser.add_argument(
        "--queries",
        choices=list(QUERY_SETS.keys()),
        default=DEFAULT_QUERY_SET,
        help=f"Query set to use (default: {DEFAULT_QUERY_SET})",
    )
    parser.add_argument("--output", help="Override output filename")
    args = parser.parse_args()

    # Parse models
    if args.models:
        models = [parse_model_spec(s.strip()) for s in args.models.split(",")]
    else:
        models = DEFAULT_MODELS

    queries = load_queries(args.queries)

    data = run_llm_benchmark(models, queries, args.top_k, args.max_queries)
    save_results(data, RESULTS_DIR)

    # Quick summary
    print(f"\n{'Model':<30} {'Avg Latency':>12} {'Errors':>8}")
    print("-" * 52)
    for model in models:
        latencies = []
        errors = 0
        for qd in data["queries"]:
            for resp in qd["responses"]:
                if resp["model"] == model.name:
                    if resp["error"]:
                        errors += 1
                    else:
                        latencies.append(resp["latency_s"])
        avg_lat = sum(latencies) / len(latencies) if latencies else 0
        print(f"{model.name:<30} {avg_lat:>10.2f}s {errors:>8}")


if __name__ == "__main__":
    main()
