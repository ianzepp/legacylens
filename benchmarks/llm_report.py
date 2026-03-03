"""Analyze LLM grading results and produce summary reports.

Usage:
    python benchmarks/llm_report.py                                        # latest grades
    python benchmarks/llm_report.py benchmarks/results/llm_grades_*.json   # specific file
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

from benchmarks.grade_responses import SCORE_FIELDS

RESULTS_DIR = Path(__file__).resolve().parent / "results"

DIMENSION_NAMES = {
    "accuracy": "Accuracy",
    "completeness": "Complete",
    "citation_quality": "Citation",
    "clarity": "Clarity",
    "conciseness": "Concise",
    "overall": "Overall",
}


def load_grades(path: Path | None = None) -> dict:
    if path:
        with open(path) as f:
            return json.load(f)

    json_files = sorted(RESULTS_DIR.glob("llm_grades_*.json"))
    if not json_files:
        print("No llm_grades_*.json files found in benchmarks/results/")
        sys.exit(1)

    latest = json_files[-1]
    print(f"Loading: {latest}\n")
    with open(latest) as f:
        return json.load(f)


def _load_latencies(grades_data: dict) -> dict[str, list[float]]:
    """Try to load latency data from the matching responses file."""
    source_file = grades_data["metadata"].get("source_file", "")
    if not source_file:
        return {}

    responses_path = RESULTS_DIR / source_file
    if not responses_path.exists():
        return {}

    with open(responses_path) as f:
        responses_data = json.load(f)

    latencies: dict[str, list[float]] = defaultdict(list)
    for qd in responses_data.get("queries", []):
        for resp in qd.get("responses", []):
            if not resp.get("error"):
                latencies[resp["model"]].append(resp["latency_s"])
    return dict(latencies)


def print_overall_ranking(grades: list[dict], latencies: dict[str, list[float]]):
    """Print overall model ranking sorted by overall score."""
    print("=" * 100)
    print("OVERALL MODEL RANKING")
    print("=" * 100)

    # Aggregate scores by model
    model_scores: dict[str, dict[str, list]] = {}
    for g in grades:
        if not g.get("scores"):
            continue
        model = g["model"]
        if model not in model_scores:
            model_scores[model] = {f: [] for f in SCORE_FIELDS}
        for f in SCORE_FIELDS:
            model_scores[model][f].append(g["scores"][f])

    # Header
    dim_headers = " ".join(f"{DIMENSION_NAMES[f]:>8}" for f in SCORE_FIELDS)
    print(f"{'Model':<30} {dim_headers} {'Latency':>8} {'Count':>6}")
    print("-" * 100)

    # Rows sorted by overall desc
    rows = []
    for model, scores in model_scores.items():
        avgs = {f: sum(scores[f]) / len(scores[f]) for f in SCORE_FIELDS}
        lat = latencies.get(model, [])
        avg_lat = sum(lat) / len(lat) if lat else 0
        rows.append((model, avgs, avg_lat, len(scores["overall"])))

    for model, avgs, avg_lat, count in sorted(rows, key=lambda x: -x[1]["overall"]):
        dim_values = " ".join(f"{avgs[f]:>8.2f}" for f in SCORE_FIELDS)
        lat_str = f"{avg_lat:.2f}s" if avg_lat else "n/a"
        print(f"{model:<30} {dim_values} {lat_str:>8} {count:>6}")


def print_category_breakdown(grades: list[dict]):
    """Print scores aggregated by query category."""
    print(f"\n{'=' * 100}")
    print("PER-CATEGORY BREAKDOWN (average overall score by model)")
    print(f"{'=' * 100}")

    # Collect all models and categories
    models = sorted({g["model"] for g in grades if g.get("scores")})
    cat_model_scores: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))

    for g in grades:
        if not g.get("scores"):
            continue
        cat = g.get("description", "unknown")
        cat_model_scores[cat][g["model"]].append(g["scores"]["overall"])

    model_headers = " ".join(f"{m[:12]:>12}" for m in models)
    print(f"{'Category':<35} {model_headers}")
    print("-" * (35 + 13 * len(models)))

    for cat in sorted(cat_model_scores.keys()):
        model_vals = []
        for m in models:
            scores = cat_model_scores[cat].get(m, [])
            avg = sum(scores) / len(scores) if scores else 0
            model_vals.append(f"{avg:>12.1f}" if scores else f"{'---':>12}")
        print(f"{cat:<35} {' '.join(model_vals)}")


def print_score_distribution(grades: list[dict]):
    """Print distribution of overall scores per model."""
    print(f"\n{'=' * 80}")
    print("SCORE DISTRIBUTION (overall score)")
    print(f"{'=' * 80}")

    model_dist: dict[str, dict[int, int]] = defaultdict(lambda: {1: 0, 2: 0, 3: 0, 4: 0, 5: 0})
    for g in grades:
        if not g.get("scores"):
            continue
        model_dist[g["model"]][g["scores"]["overall"]] += 1

    print(f"{'Model':<30} {'1':>6} {'2':>6} {'3':>6} {'4':>6} {'5':>6}")
    print("-" * 62)

    for model in sorted(model_dist.keys()):
        dist = model_dist[model]
        print(f"{model:<30} {dist[1]:>6} {dist[2]:>6} {dist[3]:>6} {dist[4]:>6} {dist[5]:>6}")


def print_worst_performers(grades: list[dict], n: int = 5):
    """Print the N lowest-scoring (model, query) pairs."""
    print(f"\n{'=' * 100}")
    print(f"WORST PERFORMERS (bottom {n})")
    print(f"{'=' * 100}")

    scored = [g for g in grades if g.get("scores")]
    scored.sort(key=lambda g: g["scores"]["overall"])

    print(f"{'Model':<30} {'Overall':>8} {'Query'}")
    print("-" * 100)
    for g in scored[:n]:
        query_preview = g["query"][:60] + "..." if len(g["query"]) > 60 else g["query"]
        print(f"{g['model']:<30} {g['scores']['overall']:>8} {query_preview}")
        if g.get("justification"):
            print(f"{'':>39} {g['justification'][:80]}")


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    data = load_grades(path)

    grades = data["grades"]
    scored = [g for g in grades if g.get("scores")]
    errors = [g for g in grades if g.get("error")]

    print(f"Grader: {data['metadata']['grader_model']}")
    print(f"Source: {data['metadata']['source_file']}")
    print(f"Total: {len(grades)} ({len(scored)} scored, {len(errors)} errors)")
    print()

    latencies = _load_latencies(data)

    print_overall_ranking(grades, latencies)
    print_category_breakdown(grades)
    print_score_distribution(grades)
    print_worst_performers(grades)


if __name__ == "__main__":
    main()
