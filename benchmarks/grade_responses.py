"""Phase 2: Grade LLM responses using a grader model (default: Claude Opus).

Loads a Phase 1 responses file, sends each (question, context, response) triple
to a grader LLM, and saves structured scores.

Usage:
    python benchmarks/grade_responses.py
    python benchmarks/grade_responses.py benchmarks/results/llm_responses_20260303_183000.json
    python benchmarks/grade_responses.py --max-grades 10
    python benchmarks/grade_responses.py --grader anthropic:claude-opus-4-20250514
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from benchmarks.llm_config import DEFAULT_GRADER, call_llm, parse_model_spec

RESULTS_DIR = Path(__file__).resolve().parent / "results"

GRADER_SYSTEM_PROMPT = """\
You are an expert evaluator assessing the quality of AI-generated answers \
about a legacy COBOL codebase (AWS CardDemo credit card management application).

You will be given:
1. The user's question
2. The retrieved code context (the same context the AI was given)
3. The AI's response

Evaluate the response on these 5 dimensions (1=poor, 5=excellent):

ACCURACY (1-5): Are factual claims correct? No hallucinated code, \
paragraph names, or behaviors beyond what the context shows?

COMPLETENESS (1-5): Does it address all parts of the question? \
Cover key code paths and structures from the context?

CITATION_QUALITY (1-5): Does it cite sources as [FileName:StartLine-EndLine]? \
Are citations accurate to the provided context?

CLARITY (1-5): Well-organized? COBOL concepts explained in plain English?

CONCISENESS (1-5): Appropriately brief without omitting important details?

Respond ONLY with valid JSON in this exact format (no markdown, no backticks):
{
  "accuracy": <1-5>,
  "completeness": <1-5>,
  "citation_quality": <1-5>,
  "clarity": <1-5>,
  "conciseness": <1-5>,
  "overall": <1-5>,
  "justification": "<2-3 sentence explanation of scores>"
}

The "overall" score is your holistic assessment — not necessarily the average."""

GRADER_USER_TEMPLATE = """\
QUESTION:
{question}

RETRIEVED CONTEXT:
{context}

AI RESPONSE:
{response}"""

SCORE_FIELDS = ["accuracy", "completeness", "citation_quality", "clarity", "conciseness", "overall"]


def _parse_grades(text: str) -> dict | None:
    """Parse JSON grades from grader response. Returns None on failure."""
    # Strip markdown code fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None

    # Validate all required fields are present and in range
    for field in SCORE_FIELDS:
        val = data.get(field)
        if not isinstance(val, (int, float)) or val < 1 or val > 5:
            return None

    return {
        "accuracy": int(data["accuracy"]),
        "completeness": int(data["completeness"]),
        "citation_quality": int(data["citation_quality"]),
        "clarity": int(data["clarity"]),
        "conciseness": int(data["conciseness"]),
        "overall": int(data["overall"]),
        "justification": str(data.get("justification", "")),
    }


def grade_responses(responses_file: Path, grader, max_grades: int | None = None) -> dict:
    """Run Phase 2: grade each model response."""
    with open(responses_file) as f:
        data = json.load(f)

    grades = []
    total = sum(len(qd["responses"]) for qd in data["queries"])
    if max_grades:
        total = min(total, max_grades)

    print(f"Grading {total} responses with {grader.name} ({grader.model_id})")
    print(f"Source: {responses_file.name}")
    print()

    count = 0
    for qd in data["queries"]:
        for resp in qd["responses"]:
            if max_grades and count >= max_grades:
                break

            if resp.get("error"):
                count += 1
                grades.append({
                    "query": qd["query"],
                    "description": qd["description"],
                    "model": resp["model"],
                    "scores": None,
                    "justification": None,
                    "error": "skipped: model returned error",
                    "grader_latency_s": 0,
                })
                print(f"  [{count}/{total}] {resp['model']:<30} | SKIP (error) | {qd['description']}")
                continue

            user_prompt = GRADER_USER_TEMPLATE.format(
                question=qd["query"],
                context=qd["formatted_context"],
                response=resp["answer"],
            )

            # Try up to 2 times to get valid JSON from the grader
            scores = None
            grader_answer = ""
            grader_latency = 0
            for attempt in range(2):
                grader_answer, grader_latency = call_llm(grader, GRADER_SYSTEM_PROMPT, user_prompt)
                scores = _parse_grades(grader_answer)
                if scores:
                    break
                if attempt == 0:
                    print(f"    Grader returned invalid JSON, retrying...")

            count += 1
            if scores:
                grades.append({
                    "query": qd["query"],
                    "description": qd["description"],
                    "model": resp["model"],
                    "scores": {k: scores[k] for k in SCORE_FIELDS},
                    "justification": scores["justification"],
                    "error": None,
                    "grader_latency_s": round(grader_latency, 3),
                })
                print(
                    f"  [{count}/{total}] {resp['model']:<30} | "
                    f"overall={scores['overall']} | "
                    f"{grader_latency:.1f}s | {qd['description']}"
                )
            else:
                grades.append({
                    "query": qd["query"],
                    "description": qd["description"],
                    "model": resp["model"],
                    "scores": None,
                    "justification": None,
                    "error": f"parse_failure: {grader_answer[:200]}",
                    "grader_latency_s": round(grader_latency, 3),
                })
                print(f"  [{count}/{total}] {resp['model']:<30} | PARSE FAIL | {qd['description']}")

        if max_grades and count >= max_grades:
            break

    return {
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "grader_model": grader.model_id,
            "source_file": responses_file.name,
            "total_graded": len(grades),
        },
        "grades": grades,
    }


def save_grades(data: dict, output_dir: Path) -> Path:
    """Save grading results as JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"llm_grades_{timestamp}.json"
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"\nGrades saved: {json_path}")
    return json_path


def _find_latest_responses(results_dir: Path) -> Path | None:
    """Find the most recent llm_responses_*.json file."""
    files = sorted(results_dir.glob("llm_responses_*.json"), reverse=True)
    return files[0] if files else None


def main():
    parser = argparse.ArgumentParser(description="Grade LLM responses (Phase 2)")
    parser.add_argument("responses_file", nargs="?", help="Path to llm_responses_*.json (default: latest)")
    parser.add_argument("--max-grades", type=int, help="Limit number of grades (for testing)")
    parser.add_argument(
        "--grader",
        help="Grader model as provider:model_id (default: anthropic:claude-opus-4-20250514)",
    )
    args = parser.parse_args()

    if args.responses_file:
        responses_file = Path(args.responses_file)
    else:
        responses_file = _find_latest_responses(RESULTS_DIR)
        if not responses_file:
            print("ERROR: No llm_responses_*.json files found in benchmarks/results/")
            sys.exit(1)
        print(f"Using latest responses file: {responses_file.name}")

    if not responses_file.exists():
        print(f"ERROR: File not found: {responses_file}")
        sys.exit(1)

    grader = parse_model_spec(args.grader) if args.grader else DEFAULT_GRADER

    data = grade_responses(responses_file, grader, args.max_grades)
    save_grades(data, RESULTS_DIR)

    # Quick summary
    model_scores: dict[str, list[int]] = {}
    for g in data["grades"]:
        if g["scores"]:
            model_scores.setdefault(g["model"], []).append(g["scores"]["overall"])

    print(f"\n{'Model':<30} {'Avg Overall':>12} {'Graded':>8}")
    print("-" * 52)
    for model, scores in sorted(model_scores.items()):
        avg = sum(scores) / len(scores)
        print(f"{model:<30} {avg:>10.2f} {len(scores):>8}")


if __name__ == "__main__":
    main()
