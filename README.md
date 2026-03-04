# LegacyLens

A RAG-powered system that makes legacy COBOL codebases queryable via natural language. Built for the AWS CardDemo credit card management application (~40K LOC across 206 mainframe source files).

**Live demo:** https://web-production-3455.up.railway.app/

## MVP Requirements

| # | Requirement | Status | Evidence |
|--:|---|---|---|
| 1 | Ingest at least one legacy codebase | Done | AWS CardDemo: 206 files, ~40K LOC (COBOL, copybooks, BMS, JCL) |
| 2 | Chunk code files with syntax-aware splitting | Done | Paragraph-level COBOL, DFHMDI for BMS, EXEC steps for JCL, 01-level splits for large DATA DIVISIONs (`chunker.py`) |
| 3 | Generate embeddings for all chunks | Done | 1,018 chunks embedded via Pinecone integrated `llama-text-embed-v2` (1024d) |
| 4 | Store embeddings in a vector database | Done | Pinecone Serverless with rich metadata (file path, line numbers, COPY refs, CALL targets) |
| 5 | Implement semantic search across the codebase | Done | Cosine similarity search with file type filtering; 0.88 relevance on 40 curated queries |
| 6 | Natural language query interface (CLI or web) | Done | Typer CLI (`legacylens ask/search`) + FastAPI web UI with 209 suggestion queries |
| 7 | Return relevant code snippets with file/line references | Done | Every result includes file name, start/end line, chunk type, relevance score |
| 8 | Basic answer generation using retrieved context | Done | LangChain RAG chain with GPT-4o-mini; grounded answers with `[File:Line-Line]` citations |
| 9 | Deployed and publicly accessible | Done | https://web-production-3455.up.railway.app/ |

## Final Submission Requirements Status (as of 2026-03-04)

Source of truth: `docs/LegacyLens.md` (Final deliverables + required feature/quality targets).

### Final Deliverables Checklist (Final Scope Only)

| Deliverable | Required | Current Status | Evidence in Repo | Gap to Close |
|---|---|---|---|---|
| GitHub Repository | Setup guide, architecture overview, deployed link | Done | This README includes setup, architecture, and deployed URL | None |
| Demo Video (3-5 min) | Show queries, retrieval, answer generation | Done (content), runtime not re-validated here | [LegacyLens Demo — RAG-Powered COBOL Code Explorer](https://youtu.be/wxKjCIaJizY) | Optionally verify final runtime is 3-5 minutes |
| RAG Architecture Doc (1-2 pages) | Vector DB choice, embedding strategy, chunking, retrieval flow, failure modes, performance results | Partial | Architecture + benchmarks are documented in this README | Create a dedicated 1-2 page final artifact in `docs/` that follows the template directly |
| AI Cost Analysis | Dev spend + projections for 100/1K/10K/100K users | Missing | No quantified spend/projection section yet | Add measured dev costs + monthly projection table with assumptions |
| Deployed Application | Publicly accessible query interface | Done | Live URL + `web/` FastAPI app | None |
| Social Post | X/LinkedIn post with demo/screenshots and `@GauntletAI` tag | Missing (no repo evidence) | None in repo | Publish post and add link in README |

### Product/Technical Requirement Snapshot

| Requirement Area | LegacyLens Requirement | Current Status | Evidence |
|---|---|---|---|
| Query Interface | NL queries, snippets with file/line, relevance scores, generated answer, full-file drilldown | Mostly Done | `web/app.py`, `web/templates/index.html`, CLI in `legacylens/cli.py` |
| Syntax Highlighting | Retrieved snippets shown with syntax highlighting | Gap | Source chunks are rendered as plain text in UI | Add client-side highlighting (or server-side rendered highlighting) |
| Code Understanding Features (4+) | Implement at least four (explanation, dependency mapping, pattern detection, impact analysis, etc.) | Likely Done | Explanation via RAG answer generation, dependency metadata (`copy_references`, `calls_to`), pattern-style querying, business-logic Q&A |
| Retrieval Precision Target | >70% relevant chunks in top-5 | Done | Benchmark sections report ~0.88 top-k relevance |
| Ingestion Throughput Target | 10,000+ LOC in <5 minutes | Done | Ingestion benchmark section reports passing configs |
| Codebase Scale/Coverage | 10,000+ LOC, 50+ files, full indexing | Done | 206 files, ~40K+ LOC, ingestion/vector counts documented |
| End-to-End Latency Target | <3s query latency | Partial | Retrieval latency is sub-second; full ask path documented around ~3-5s in README |

### Remaining Work for Fully Aligned Final Submission

1. Add a dedicated `docs/final-rag-architecture.md` (1-2 pages) using the assignment template headings.
2. Add a quantified AI cost analysis section (actual dev spend + 100/1K/10K/100K monthly projections).
3. Complete and update Phase 3 items in `docs/pre-search-decisions.md` so the checklist is fully closed.
4. Add syntax highlighting for retrieved code snippets in the web UI.
5. Publish social post and add the link to README.

## Video Demos

- [LegacyLens Demo — RAG-Powered COBOL Code Explorer](https://youtu.be/wxKjCIaJizY)

## Architecture

```
Source Files ──> Parser ──> Chunker ──> Embeddings ──> Pinecone
                                                         │
User Query ──> Embed Query ──> Similarity Search ────────┘
                                       │
                              Retrieved Chunks ──> LLM ──> Answer + Citations
```

**Ingestion pipeline:** Files are discovered by extension, parsed with a COBOL-aware parser that detects sequence number formats and extracts divisions/paragraphs/COPY references/CALL targets, then chunked at syntactic boundaries (paragraphs for COBOL, DFHMDI for BMS, EXEC steps for JCL). Each chunk gets a descriptive preamble prepended before embedding.

**Retrieval pipeline:** User queries are embedded with the same model, matched against Pinecone via cosine similarity, and the top-k chunks are assembled into context for GPT-4o-mini, which generates answers with `[File:Line-Line]` citations.

### Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Vector DB | Pinecone Serverless | Free tier, managed, no infrastructure |
| Embedding model | Pinecone llama-text-embed-v2 (1024d) | Fastest + highest relevance in benchmarks |
| Chunking | Paragraph-level (COBOL), boundary-aware | Preserves semantic units; short paragraphs merged |
| LLM | GPT-4o-mini | Fast, cheap, sufficient for code Q&A |
| Framework | LangChain (core only) | Minimal abstraction, just prompt + LLM + parser |

### File Types Handled

| Type | Extension | Chunking Strategy |
|---|---|---|
| COBOL programs | `.cbl`, `.cob` | Header + DATA DIVISION (split at 01-level if >200 lines) + one chunk per paragraph |
| Copybooks | `.cpy` | Single chunk per file |
| BMS screen maps | `.bms` | Split on DFHMSD/DFHMDI boundaries |
| JCL job control | `.jcl` | Split on `//STEP EXEC` boundaries |
| Other mainframe | `.dcl`, `.ddl`, `.ctl`, `.csd`, `.dbd`, `.psb`, `.asm`, `.mac` | Single chunk per file |

## Setup

```bash
# Clone and install
git clone <repo-url>
cd legacylens
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Configure
cp .env.example .env
# Edit .env with your API keys and CardDemo path
```

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | OpenAI API key for embeddings and chat |
| `OPENROUTER_API_KEY` | No | OpenRouter API key for non-OpenAI models (Claude, Gemini, Llama, etc.) |
| `PINECONE_API_KEY` | Yes | Pinecone API key |
| `PINECONE_INDEX_NAME` | No | Index name (default: `legacylens-bench-llama-1024-paragraph`) |
| `CARDDEMO_PATH` | For ingestion | Path to CardDemo `app/` directory |
| `USE_OLLAMA` | No | Set `true` to use Ollama for local embeddings |
| `LAYER_1_CACHE` | No | Enable search result cache (default: `true`) |

## Usage

### Ingest the codebase

```bash
python scripts/ingest_carddemo.py        # first run
python scripts/ingest_carddemo.py --clean # re-ingest from scratch
```

Output: 206 files parsed into ~1018 chunks, embedded and stored in Pinecone.

### CLI

```bash
# Ask a question (retrieval + LLM answer)
legacylens ask "What does the COCRDUPC program do?"

# Search only (no LLM, shows raw chunks)
legacylens search "credit card validation"

# Filter by file type
legacylens ask "How are VSAM files defined?" --type jcl
```

### Web UI

```bash
uvicorn web.app:app --port 8000
# Open http://localhost:8000
```

Single-page interface with query input, file type filter, LLM-generated answers, and collapsible source citations with relevance scores. Supports loading full file context from source links.
Streaming uses WebSockets (`/ws/ask`) with JSONL events. In production (for example Railway), ensure `websockets` is installed in the runtime environment.

### API

```bash
# Ask with LLM answer (blocks until complete, returns JSON)
curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What does COCRDUPC do?", "top_k": 10}'

# Ask with streaming (Server-Sent Events, token-by-token)
curl -N -X POST http://localhost:8000/api/ask/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "What does COCRDUPC do?", "top_k": 10}'

# Search only (no LLM)
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "credit card validation", "file_type": "cbl"}'

# Load full file context
curl -X POST http://localhost:8000/api/file \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/path/to/COCRDUPC.cbl"}'
```

Both `/api/ask` and `/api/ask/stream` accept the same request body (`question`, `top_k`, `file_type`, `model`). The non-streaming endpoint returns JSON `{"answer": "...", "sources": [...]}`. The streaming endpoint returns SSE with `data:` lines for answer tokens, an `event: sources` with the sources JSON, and `event: done` to signal completion. The web UI uses the streaming endpoint by default.

## Testing

```bash
# Unit tests (no API keys needed)
CARDDEMO_PATH=/path/to/carddemo/app pytest tests/ -v

# Include live retrieval tests against Pinecone
CARDDEMO_PATH=/path/to/carddemo/app LEGACYLENS_RUN_LIVE_TESTS=1 pytest tests/ -v
```

Tests cover parser, chunker, ingestion, vector store, chain formatting, live retrieval quality, and benchmark infrastructure.

## Caching

Caching eliminates redundant API calls for the 209 pre-defined suggestion queries that users can click in the UI.

### Layer 1: Search Results (pre-computed, persistent)

All 209 suggestion queries are pre-run against Pinecone and saved as `web/cache/search_cache.json` (6.2 MB). This file ships with the repo and is loaded at startup — cached suggestion queries skip the Pinecone vector search entirely (0ms vs ~400ms).

```bash
# Regenerate after index changes
python scripts/warmup_cache.py
```

### Cache Controls

Layer 1 can be disabled at the server level:

```bash
LAYER_1_CACHE=false uvicorn web.app:app  # skip search cache, always hit Pinecone
```

### Cache Behavior by Request Type

| Request | Layer 1 (search) | Latency |
|---|---|---|
| Suggestion click (search only) | Hit | ~0ms |
| Any ask query | Hit or Miss (depends on suggestion match) | ~3-5s |
| Any query with file_type filter | Bypass | ~3-5s (full pipeline) |

## Benchmarking

A performance benchmark suite compares retrieval latency and relevance across different embedding models, vector dimensions, chunking strategies, and top-k values.

### Test Matrix (16 index configurations)

| Model | Provider | Dimensions | Indexes |
|---|---|---|---|
| `text-embedding-3-small` | OpenAI | 512, 1024, 1536 | 6 (× 2 chunking strategies) |
| `text-embedding-3-large` | OpenAI | 512, 1024, 1536 | 6 (× 2 chunking strategies) |
| `multilingual-e5-large` | Pinecone integrated | 1024 | 2 (× 2 chunking strategies) |
| `llama-text-embed-v2` | Pinecone integrated | 1024 | 2 (× 2 chunking strategies) |

**Chunking strategies:** `paragraph` (syntax-aware, current default) and `fixed` (~500-token chunks with overlap).

**Top-k values:** 3, 5, 10, 20, 50.

Each configuration creates a separate Pinecone index named `legacylens-bench-{model}-{dims}-{chunking}`.

### Query Suites

Two query sets are available, selectable via `--queries`:

| Set | Queries | Description |
|---|--:|---|
| `curated` (default) | 40 | Hand-curated queries with manually verified expected files/chunks |
| `suggestions` | 209 | Auto-extracted from the "Suggest" feature across 20 categories |

Each query is run 3 times per configuration for timing stability. Metrics collected:

- **Latency:** mean, p50, p95, min, max (seconds)
- **Relevance:** fraction of expected files/chunks found in results (0.0 - 1.0)

### Results (2026-03-03)

Benchmark run: 16 configs, 10 queries, 5 top-k values (3/5/10/20/50), 3 repetitions per query (800 total query runs).

#### Overall Summary (ranked by relevance, then latency)

| Config | Avg Latency | Avg Relevance |
|---|--:|--:|
| **llama-1024-paragraph** | **0.459s** | **0.78** |
| small-1536-paragraph | 0.634s | 0.77 |
| small-1024-paragraph | 0.634s | 0.76 |
| small-512-paragraph | 0.633s | 0.76 |
| large-1024-paragraph | 0.666s | 0.74 |
| large-1536-paragraph | 0.642s | 0.74 |
| e5-1024-paragraph | 0.467s | 0.70 |
| large-512-paragraph | 0.607s | 0.70 |
| small-1536-fixed | 0.628s | 0.60 |
| small-1024-fixed | 0.648s | 0.59 |
| small-512-fixed | 0.598s | 0.58 |
| llama-1024-fixed | 0.427s | 0.57 |
| e5-1024-fixed | 0.436s | 0.53 |
| large-1536-fixed | 0.605s | 0.51 |
| large-1024-fixed | 0.651s | 0.49 |
| large-512-fixed | 0.595s | 0.47 |

#### Key Findings

1. **Paragraph chunking wins decisively.** Every paragraph config outperforms its fixed-size counterpart in relevance (0.70-0.78 vs 0.47-0.60). The COBOL-aware syntax chunking preserves meaningful code boundaries that matter for retrieval.

2. **Pinecone integrated models are ~30% faster.** Llama/E5 at 0.43-0.47s vs OpenAI at 0.60-0.67s. Server-side embedding eliminates the client-side API round-trip.

3. **`llama-text-embed-v2` is the best overall.** Fastest paragraph config (0.459s) with the highest relevance (0.78). Both fastest and most accurate.

4. **Dimension size barely matters for OpenAI `small`.** 512, 1024, and 1536 dimensions all score 0.76-0.77 relevance. Extra dimensions add latency without improving retrieval quality for this codebase.

5. **`text-embedding-3-large` offers no advantage.** Slower than `small` with equal or worse relevance. The COBOL-specific preambles and chunking strategy contribute more to retrieval quality than embedding model size.

6. **Hardest queries across all configs:** "File I/O operations" and "CICS screen navigation" consistently score low, suggesting the expected result patterns for these queries may need refinement.

### Expanded Results: 40-Query Suite (2026-03-03)

After the initial 10-query benchmark identified paragraph chunking as the clear winner, the 8 fixed-chunking indexes were deleted. A broader 40-query benchmark suite was then built from 209 curated suggestion queries spanning 20 categories (user management, account processing, card processing, transactions, export/import, admin, date/utility, copybooks, BMS maps, JCL jobs, CICS operations, DB2, VSAM, paragraph patterns, data elements, cross-cutting concerns, business domain, architecture, specific operations, file definitions).

Benchmark run: 8 configs (paragraph only), 40 queries, 2 top-k values (5/10), 1 repetition (640 total query runs).

#### Overall Summary (ranked by relevance, then latency)

| Rank | Config | Avg Latency | Avg Relevance |
|---:|---|--:|--:|
| 1 | **llama-1024-paragraph** | **0.365s** | **0.88** |
| 2 | large-1536-paragraph | 0.686s | 0.82 |
| 3 | large-1024-paragraph | 0.591s | 0.80 |
| 4 | large-512-paragraph | 0.528s | 0.77 |
| 5 | small-1536-paragraph | 0.616s | 0.73 |
| 6 | e5-1024-paragraph | 0.439s | 0.71 |
| 7 | small-1024-paragraph | 0.593s | 0.71 |
| 8 | small-512-paragraph | 0.568s | 0.68 |

#### Key Findings (40-query update)

1. **`llama-text-embed-v2` dominance confirmed at scale.** The relevance gap widened from +1pt (10 queries) to +6pts (40 queries) over the runner-up, while remaining the fastest config. Best relevance (0.88) and best latency (0.365s).

2. **`text-embedding-3-large` overtakes `small` with broader queries.** With 40 queries spanning more categories, `large` models now clearly outperform `small` (0.77-0.82 vs 0.68-0.73). The original 10-query suite was too narrow to surface this difference.

3. **Dimension size matters more for `large`.** The 1536d large config scores 0.82 vs 0.77 for 512d — a meaningful 5-point gap. For `small`, the spread is tighter (0.68-0.73).

4. **Pinecone integrated models remain ~40% faster.** Llama at 0.365s and E5 at 0.439s vs OpenAI configs at 0.53-0.69s.

### Reranking & Hybrid Search Results (2026-03-03)

With `llama-1024-paragraph` confirmed as the best dense index, the next tuning level tested reranking (re-scoring results with a cross-encoder) and hybrid search (combining dense semantic + sparse keyword retrieval). Three reranker models were benchmarked, plus a hybrid config using a separate sparse index (`pinecone-sparse-english-v0`).

Benchmark run: 4 configs, 40 queries, 2 top-k values (5/10), 1 repetition (320 total query runs).

#### Overall Summary (vs baseline)

| Rank | Config | Strategy | Avg Latency | Avg Relevance | vs Baseline |
|---:|---|---|--:|--:|---|
| 1 | **llama-1024-paragraph** (baseline) | Dense only | **0.365s** | **0.88** | — |
| 2 | llama-rerank-pinecone | Two-step, truncated to 900 chars | 0.867s | 0.88 | Same relevance, +137% latency |
| 3 | llama-rerank-cohere | Inline (4K token context) | 0.609s | 0.86 | -2pt relevance, +67% latency |
| 4 | llama-rerank-bge | Two-step, truncated to 900 chars | 0.811s | 0.86 | -2pt relevance, +122% latency |
| 5 | llama-hybrid-rerank | Dense + Sparse + Rerank | 0.967s | 0.10 | -78pt relevance |

#### Key Findings (reranking update)

1. **The baseline wins.** `llama-text-embed-v2` at 0.88 relevance is already so good that reranking cannot improve it — it only adds latency (2-2.5x slower).

2. **Cohere inline reranking is the fastest reranker** (0.609s) thanks to a single API call with 4K token context, but still 67% slower than no reranking.

3. **Pinecone-rerank-v0 ties on relevance** (0.88) but requires two-step fetch-then-rerank with truncation due to its 512-token limit. COBOL tokenizes poorly (~2 chars/token due to hyphenated identifiers like `WS-RESP-CD`, `9910-DISPLAY-IO-STATUS`), so documents must be truncated to ~900 chars.

4. **Hybrid search is catastrophic** (0.10 relevance). The sparse keyword model generates irrelevant matches on COBOL's verbose naming conventions, overwhelming the reranker. COBOL's domain-specific tokens (paragraph names, copybook prefixes, level numbers) are a poor fit for general-purpose sparse/keyword retrieval.

5. **Conclusion: ship the baseline.** Dense retrieval with `llama-text-embed-v2` and paragraph chunking is the optimal configuration. Reranking and hybrid search add complexity and latency without improving relevance for this domain.

### Expanded Results: 209-Query Suite (2026-03-03)

To validate generalization beyond hand-curated queries, the full 209-query suggestion set was run against the top model (`llama-1024-paragraph`). These queries were auto-extracted from the "Suggest" feature, spanning all 20 categories with expected file patterns derived from program names in the query text.

Benchmark run: 1 config, 209 queries, 2 top-k values (5/10), 1 repetition (418 total query runs).

| Query Set | top_k | Avg Latency | Avg Relevance | Queries |
|---|--:|--:|--:|--:|
| Curated | 5 | 0.365s | 0.88 | 40 |
| Suggestions | 5 | 0.404s | 0.89 | 209 |
| Suggestions | 10 | 0.416s | 0.92 | 209 |

#### Key Findings (209-query update)

1. **The model generalizes well.** Relevance on 209 auto-generated queries (0.89-0.92) matches or exceeds the hand-curated 40-query score (0.88), confirming the benchmark results are not overfit to the curated set.

2. **top_k=10 provides a meaningful lift.** Going from k=5 to k=10 improves relevance by 3 points (0.89 → 0.92) with only 12ms additional latency — a worthwhile trade-off for production use.

3. **Latency is consistent.** Average latency of 0.41s across 209 queries matches the 40-query benchmark (0.365s), with no degradation at scale.

### LLM Answer Quality Benchmark

A separate benchmark suite compares how well different LLMs answer questions given the same retrieved context. This runs in two phases:

**Phase 1 — Generate responses:** Retrieves chunks once per query, then sends the same context to each model. Records full answers and response latency.

```bash
# Run with specific models (provider:model_id syntax)
python benchmarks/run_llm_benchmark.py --models openai:gpt-4o-mini,anthropic:claude-sonnet-4-20250514

# Quick test (5 queries only)
python benchmarks/run_llm_benchmark.py --models openai:gpt-4o-mini --max-queries 5
```

**Phase 2 — Grade responses:** Sends each (question, context, response) triple to a grader LLM (default: Claude Opus) which scores on 6 dimensions:

| Dimension | What it measures |
|---|---|
| Accuracy | Factual correctness vs provided context; no hallucination |
| Completeness | Addresses all parts of the question; covers key code paths |
| Citation Quality | Uses `[File:Line-Line]` format; citations match context |
| Clarity | Well-organized; COBOL concepts explained in plain English |
| Conciseness | Appropriately brief without omitting important details |
| Overall | Holistic assessment (not a mechanical average) |

```bash
# Grade latest responses (default grader: Claude Opus)
python benchmarks/grade_responses.py

# Use a specific grader model
python benchmarks/grade_responses.py --grader anthropic:claude-opus-4-20250514

# Quick test
python benchmarks/grade_responses.py --max-grades 10
```

**Report:** Generates model ranking tables, per-category breakdowns, score distributions, and worst-performing pairs.

```bash
python benchmarks/llm_report.py
```

#### Latest Spot Check: Gemini Flash Lite on Suggestions (10 queries, 2026-03-04)

To validate the current default model path and verbosity tradeoffs, three 10-query runs were executed on the `suggestions` set and graded with OpenRouter Claude Opus.

- **Response model:** `openrouter:google/gemini-2.5-flash-lite`
- **Grader model:** `openrouter:anthropic/claude-opus-4-6`
- **Query set:** `suggestions`
- **Query count:** `10`
- **Top-k:** `10`

| Verbosity | Mean Latency | p50 | p95 | Accuracy | Completeness | Citation Quality | Clarity | Conciseness | Overall |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Succinct | 1.51s | 1.544s | 1.784s | 4.30 | 3.10 | 3.40 | 4.40 | 4.50 | 3.40 |
| Regular | 2.06s | 2.104s | 2.494s | 4.50 | 3.90 | 3.50 | 4.80 | 4.60 | **4.20** |
| Detailed | 3.28s | 3.465s | 4.416s | 4.30 | 4.00 | 4.20 | 4.90 | 4.10 | 4.10 |

Interpretation: more detail generally improves answer quality dimensions like completeness and citation quality, but increases latency. `Regular` currently gives the best quality/speed balance in this spot check.

### Ingestion Throughput Benchmark

Measures the full ingestion pipeline (discover → chunk → embed → upsert) using temporary Pinecone indexes. Validates the **10,000+ LOC in <5 minutes** throughput target.

```bash
# Run for specific configs (substring match)
python benchmarks/run_ingest_benchmark.py --configs llama,e5,small-1024-paragraph

# Filter by chunking strategy
python benchmarks/run_ingest_benchmark.py --strategies paragraph

# Run all unique configs (deduplicates rerank/hybrid variants)
python benchmarks/run_ingest_benchmark.py

# Keep temp indexes after run (for inspection)
python benchmarks/run_ingest_benchmark.py --configs llama --keep-indexes
```

Configs are deduplicated by `(provider, model, dims, strategy)` — rerank and hybrid configs share the same ingestion path as their base and are excluded automatically.

#### Results (2026-03-03)

Benchmark run: 3 configs, 206 files, 48,327 LOC, 1,018 chunks (paragraph strategy).

| Config | Provider | Embed+Upsert | Pipeline Total | LOC/s | Result |
|---|---|--:|--:|--:|---|
| **e5-1024-paragraph** | Pinecone | 17.0s | 17.1s | **2,819** | PASS |
| **llama-1024-paragraph** (default) | Pinecone | 40.7s | 40.8s | **1,184** | PASS |
| **small-1024-paragraph** | OpenAI | 52.3s | 52.4s | **922** | PASS |

All configs pass the target with significant margin. Discovery (<1ms) and chunking (0.1s) are negligible — embed+upsert dominates. Index creation (~6s) is excluded from throughput as infrastructure overhead. Pinecone integrated models (e5, llama) are 1.3-3x faster than OpenAI due to server-side embedding.

### Running Retrieval Benchmarks

```bash
# 1. Ingest into all 16 indexes (or a subset)
python benchmarks/ingest_all.py
python benchmarks/ingest_all.py --configs small-512-paragraph,large-1024-fixed
python benchmarks/ingest_all.py --clean  # delete and re-create indexes

# 2. Run benchmark suite
python benchmarks/run_benchmark.py
python benchmarks/run_benchmark.py --configs small-512-paragraph --top-k 5,10
python benchmarks/run_benchmark.py --queries suggestions --configs llama-1024-paragraph

# 3. Analyze results
python benchmarks/report.py                               # latest results
python benchmarks/report.py benchmarks/results/file.json  # specific file
```

Results are saved to `benchmarks/results/` as JSON (full detail) and CSV (summary). The report produces:
- Overall summary table ranked by relevance then latency
- Per-top-k breakdown
- Model comparison (averaged across chunking strategies)
- Chunking strategy comparison (paragraph vs fixed)

## Project Structure

```
legacylens/
├── legacylens/
│   ├── config.py          # Pydantic settings
│   ├── models.py          # CodeChunk, QueryResult dataclasses
│   ├── parser.py          # COBOL structure parser (divisions, paragraphs, COPY/CALL)
│   ├── chunker.py         # Syntax-aware + fixed-size chunking (COBOL/BMS/JCL/copybook)
│   ├── embeddings.py      # OpenAI / Ollama embedding generation
│   ├── vectorstore.py     # Pinecone index operations
│   ├── ingest.py          # Orchestrator: discover → chunk → embed → store
│   ├── retriever.py       # Query embedding + Pinecone search
│   ├── chain.py           # LangChain RAG chain (context + LLM)
│   └── cli.py             # Typer CLI (ask, search, ingest)
├── benchmarks/
│   ├── config.py              # Test matrix (20 configs), query loading, relevance scoring
│   ├── queries_curated.py     # 40 hand-curated benchmark queries
│   ├── queries_suggestions.py # 209 auto-extracted suggestion queries
│   ├── ingest_all.py          # Multi-index ingestion (OpenAI + Pinecone + sparse)
│   ├── run_benchmark.py       # Retrieval benchmark runner (latency + relevance)
│   ├── run_ingest_benchmark.py # Ingestion throughput benchmark (LOC/s target)
│   ├── report.py              # Retrieval results analysis and summary tables
│   ├── llm_config.py          # LLM model registry + multi-provider call abstraction
│   ├── run_llm_benchmark.py   # Phase 1: LLM response generation + latency
│   ├── grade_responses.py     # Phase 2: Grade responses with Claude Opus
│   ├── llm_report.py          # LLM quality report (ranking, categories, distribution)
│   └── results/               # JSON + CSV output
├── web/
│   ├── app.py             # FastAPI endpoints
│   └── templates/
│       └── index.html     # Single-page query UI
├── scripts/
│   └── ingest_carddemo.py # One-shot ingestion runner
└── tests/
    ├── test_parser.py     # 30 tests
    ├── test_chunker.py    # 29 tests
    ├── test_ingest.py     # 14 tests
    ├── test_vectorstore.py# 8 tests
    ├── test_chain.py      # 9 tests
    ├── test_retrieval.py  # 13 tests (6 live + 7 chunking)
    └── test_benchmark.py  # 27 tests (configs, queries, relevance scoring, fixed chunker)
```

## Development History (2026-03-02 to 2026-03-04)

Full analysis: [`docs/commit-history-2026-03-02-to-2026-03-04.md`](docs/commit-history-2026-03-02-to-2026-03-04.md)

LegacyLens went from skeleton to fully deployed, benchmarked RAG application in a 3-day sprint. 73 commits, ~8,400 source lines added (excluding benchmark data artifacts), 57% co-authored with Claude Opus 4.6.

### Timeline

| Day | Commits | Focus |
|---|---|---|
| Mon 03-02 | 11 | Foundation — test suite, benchmark harness, Fallout-mainframe UI, Railway deploy |
| Tue 03-03 | 46 | Intensity — 16-config benchmark campaign, SSE→WebSocket streaming, testability refactor, LLM quality eval |
| Wed 03-04 | 16 | Polish — latency telemetry, L1 sharded cache, syntax highlighting, submission checklist |

### Themes

1. **Benchmark-driven engineering** — 16-config embedding sweep → 40-query → 209-query validation. Every default backed by measured data.
2. **Iterative caching** — L1+L2 → remove L2 → on-disk sharded L1 with prompt caching. Designs were added, measured, and removed based on observed behavior.
3. **SSE→WebSocket migration** — Streaming transport upgraded to WebSocket JSONL with early source delivery and done/ack shutdown handshake.
4. **Test coverage from Day 1** — 9+ test files, testability refactor touching all 6 core modules mid-sprint.

### Velocity

| Metric | Value |
|---|---|
| Commits/day | 24.3 (3-8x solo developer norm) |
| Source lines/day | ~2,800 (5-14x solo developer norm) |
| Code churn ratio | 15% (low end of healthy — code stuck on first pass) |
| Peak day | Tue 03-03: 46 commits across ~14 hours |
| AI co-authored | 42/73 commits (57%), clustered on infrastructure and refactors |

### Code Survival

Core pipeline modules: ~55-65% survival (early architecture held, implementation details iterated). UI layer: ~35% (multiple streaming/styling passes). Test suite: ~80% (primarily additive).

## Deployment

```bash
# Railway / Render
uvicorn web.app:app --host 0.0.0.0 --port $PORT
```

Set `OPENAI_API_KEY` and `PINECONE_API_KEY` as environment variables. The Pinecone index persists in the cloud — ingestion only needs to run once locally.
