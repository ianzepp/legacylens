# AI Development Log — LegacyLens

## Tools & Workflow

### AI Coding Assistants

I used two AI coding assistants throughout the 3-day sprint (March 2-4, 2026):

**Claude Code (Opus 4.6)** — Primary assistant. ~60 sessions across the sprint. Claude handled the majority of implementation work: parser logic, chunker logic, benchmark infrastructure, WebSocket streaming, test suites, UI theming, and production hardening. Claude's strength was executing multi-file refactors cleanly — the testability refactor commit (`76e19a5`, 1,028 insertions / 200 deletions across 6 core modules + 3 new test files) landed in a single pass without manual intervention.

**OpenAI Codex CLI (GPT-5.3-codex)** — Secondary assistant. ~8 sessions, primarily for code review and sanity checking. Codex's multi-agent spawning capability was useful for parallel audits: in one session it launched three concurrent review agents (implementation quality, CardDemo alignment, rag-cookbook pattern comparison) and consolidated their findings into a severity-ordered report. This caught real issues — vector ID collisions, missing file extensions in discovery, incomplete metadata passthrough — that were subsequently fixed.

**Google Gemini** — Used for UI mockup generation, not code. I crafted three image generation prompts (terminal-forward, graphic-design-forward, weathered-hardware-forward) to explore the Fallout/mainframe aesthetic before committing to implementation. The generated mockups served as visual references for Claude's CSS implementation.

### Workflow Pattern

The dominant workflow was: **I design, AI implements.** I wrote benchmark plans, architecture decisions, and UI specs in natural language, then handed them to Claude or Codex for execution. The critical distinction: I made every architectural decision. The AI never chose an embedding model, a chunking strategy, or a caching approach — it implemented the ones I selected based on benchmark data.

Typical session flow:
1. I write a detailed plan (often in markdown with pseudocode)
2. Claude reads the plan and relevant existing files
3. Claude implements across all affected files
4. I review the diff and test manually
5. I commit (often with `Co-Authored-By: Claude Opus 4.6`)

For code review, the pattern inverted: Codex read the full codebase and docs, spawned parallel review agents, and delivered prioritized findings. I then decided which findings to address.

---

## Architecture Decisions

### Decision 1: Pinecone Serverless with Integrated Embedding

**When:** March 2, during the Pre-Search walkthrough session (55 user messages, 64 assistant messages, ~75 minutes).

**How it was made:** Claude walked me through the 16-item Pre-Search checklist one question at a time. I explicitly asked for this pacing: "Please walk me through the presearch phase questions, not all at once." When we reached vector database selection, I described my constraints ($100/month budget, no prior vector DB experience, one-week sprint), and Claude presented tradeoffs across Pinecone, Weaviate, Qdrant, ChromaDB, pgvector, and Milvus. I chose Pinecone for managed infrastructure and free tier, accepting vendor lock-in as a tradeoff.

**Outcome:** The integrated embedding API (`llama-text-embed-v2`) turned out to be a 30-40% latency win over client-side OpenAI embedding (0.365s vs 0.59-0.69s). This was not predicted during the Pre-Search phase — it was discovered during benchmarking.

### Decision 2: Paragraph-Level Chunking over Fixed-Size

**When:** March 2, Pre-Search session.

**How it was made:** I told Claude: "I would imagine that for a legacy language, the comments are almost more important than the code." This observation about COBOL's nature led to a chunking strategy that preserved paragraph boundaries (COBOL's natural semantic units) rather than using arbitrary 500-token windows. Claude implemented syntax-aware boundary detection for COBOL divisions, paragraphs, copybooks, BMS maps, and JCL steps.

**Outcome:** Paragraph chunking won decisively in every benchmark configuration (0.70-0.88 relevance vs 0.47-0.60 for fixed-size). This was the single largest driver of retrieval quality.

### Decision 3: Dense-Only Retrieval (Reranking and Hybrid Rejected)

**When:** March 3, after implementing and running the reranking/hybrid benchmark suite.

**How it was made:** I wrote a detailed benchmark plan specifying 3 reranking models and 1 hybrid configuration, then handed it to Claude for implementation. The results were unambiguous: the dense baseline (0.88 relevance, 0.365s) could not be improved by reranking (same relevance, 67-137% slower) and hybrid search was catastrophic (0.10 relevance). COBOL's hyphenated identifiers produce a flood of spurious keyword matches that overwhelm sparse retrieval.

**Outcome:** Shipping dense-only retrieval. The benchmark data killed the reranking and hybrid features before they reached production.

### Decision 4: SSE to WebSocket JSONL Migration

**When:** March 3, evening session.

**How it was made:** SSE streaming was implemented midday on March 3 but had reliability issues — the StopIteration bug, false error states on connection close, and inability to send structured events before the LLM stream started. I decided to migrate to WebSocket JSONL, which allowed source references to stream as discrete events before the LLM generation began. Claude implemented the migration across server, client, and test suite in a single coherent refactor (`3d808b1`).

**Outcome:** Users see relevant source files immediately while the answer generates. The done/ack shutdown handshake (`11e662b`, March 4) eliminated false error states.

### Decision 5: Gemini 2.5 Flash Lite as Default Model

**When:** March 3, evening session, after running the LLM quality benchmark.

**How it was made:** After benchmarking 8 models (GPT-4o-mini through GPT-5, plus Gemini via OpenRouter), Gemini 2.5 Flash Lite scored 4.20 overall quality at 10x lower cost than GPT-4o-mini. I switched the default in commit `53b37fd`.

**Outcome:** Default query cost dropped from ~$0.002/query (GPT-4o-mini) to ~$0.0002/query (Gemini Flash Lite) with comparable quality.

---

## Effective Prompts

### Prompt 1: Guided Architecture Walkthrough

> "Please walk me through the presearch phase questions, not all at once."

**Context:** Start of the Pre-Search session (March 2, 17:50 UTC). I had a 16-item architecture checklist covering scale, budget, embedding models, chunking strategies, and framework selection.

**Why it worked:** Instead of dumping all 16 questions at once, Claude presented them one at a time with contextual analysis. This created a conversational decision process where each answer informed the next question. The session lasted 75 minutes and produced a complete architecture document. Forcing sequential pacing prevented me from making premature decisions and let Claude provide relevant tradeoff analysis for each item.

### Prompt 2: Multi-Agent Sanity Check

> "I'd like you to sanity check the work that has been implemented in @gauntlet-week-3/ , based on the files in @gauntlet-week-3/docs/ , the target COBOL and related source repo in aws-mainframe-modernization-carddemo/ and a reference RAG implementation (teaching purposes) in rag-cookbook/"

**Context:** Sent to Codex CLI (GPT-5.3-codex) on March 2, 20:54 UTC, after the first day's implementation sprint. I wanted an independent review of the entire codebase against the project spec and target data.

**Why it worked:** Codex spawned three parallel review agents — one for implementation quality, one for CardDemo alignment, one for rag-cookbook pattern comparison. The consolidated report surfaced 8 findings at High/Medium severity, including vector ID collisions, missing file extensions (`.dcl`, `.ddl`, `.ctl`, `.csd`, `.dbd`, `.psb`, `.asm`, `.mac`), and incomplete metadata passthrough. All findings were actionable and specific (with file:line references). Using a different AI model for review created genuine adversarial tension — Codex had no loyalty to Claude's implementation choices.

### Prompt 3: Creative Design Brief

> "I don't want a fallout clone, I want something where a mainframe COBOL had a baby with a fallout designer."

**Context:** March 2, 22:15 UTC, during the UI design session. I had just told Claude about wanting a Fallout theme for the web UI, and Claude was asking clarifying questions about aesthetic direction.

**Why it worked:** This single sentence became the creative brief for the entire visual identity. Claude immediately translated it into specific design principles: amber/green phosphor terminals with Vault-Tec graphic design sensibility, CRT glow effects as texture not gimmick, typography that feels like a terminal but designed by someone who cares about layout. This brief also produced three Gemini image generation prompts that I used for visual exploration. The resulting UI (Monofonto + Fixedsys Excelsior fonts, greenbar paper effect, sprocket holes, green-screen chunk viewer) shipped in commit `ceb43b7` and remained consistent through the end of the sprint.

### Prompt 4: Detailed Implementation Plan

> "Implement the following plan: # Plan: Add Reranking and Hybrid Search Benchmarks [followed by a detailed markdown plan with context, approach, code snippets, file list, and verification steps]"

**Context:** March 3, 17:47 UTC. I had spent time designing the benchmark plan myself, then handed the full plan to Claude for execution.

**Why it worked:** Providing a complete plan with pseudocode, file paths, API signatures, and verification criteria eliminated ambiguity. Claude implemented across 4 files (`config.py`, `run_benchmark.py`, `ingest_all.py`, `test_benchmark.py`), created its own task list to track progress, and delivered all 25 tests passing on the first run. The key insight: the more precise the plan, the less back-and-forth required. This pattern — human architects, AI implements — was the most efficient workflow I found.

### Prompt 5: Pushing for the Right Solution

> "instead of the simplest fix, what is the correct solution here? we are going for performance"

**Context:** March 3, during a debugging session where Claude proposed a quick fix for a latency issue.

**Why it worked:** AI assistants default to the simplest fix, which is often correct. But when you know you need the performant solution, explicitly asking for it changes the solution space. This prompt pattern — rejecting the easy answer and asking for the proper one — was something I used repeatedly when Claude's initial suggestion was technically correct but suboptimal for a production system.

---

## Code Analysis

### AI Authorship

| Metric | Value |
|---|---|
| Total commits | 73 |
| Co-authored with Claude Opus 4.6 | 42 (57%) |
| Human-only commits | 31 (43%) |
| Source code insertions (total) | 8,357 |
| Source code deletions (total) | 1,250 |
| Code churn ratio | 15.0% |

### What the AI Wrote

The 42 co-authored commits cluster around:

- **Infrastructure code:** Benchmark harness (`config.py`, `run_benchmark.py`, `ingest_all.py`), ingestion pipeline (`ingest.py`, `parser.py`, `chunker.py`), vector store abstraction (`vectorstore.py`, `embeddings.py`)
- **Test suites:** 9 test files totalling ~1,500+ lines. The testability refactor (`76e19a5`) added 531 test lines in a single commit.
- **UI implementation:** Fallout-themed CSS, WebSocket JSONL client, markdown rendering, syntax highlighting
- **Production plumbing:** SSE-to-WebSocket migration, OpenRouter integration, cache layer implementations, latency telemetry

### What I Wrote

The 31 human-only commits include:

- **Architecture documents:** Pre-Search decisions, benchmark plans, README sections
- **Configuration:** Railway deployment config, environment variables, model selection
- **Data artifacts:** Benchmark results (JSON/CSV), L1 cache files, suggestion query sets
- **Quick fixes:** One-line production bug fixes, UI spacing tweaks, default value changes

### Estimated AI Code Contribution

By line count, AI-assisted commits account for roughly 60-65% of source code insertions. However, this overstates the AI's independent contribution — every co-authored commit was directed by a specific plan or prompt from me. The AI wrote the code; I designed the architecture, chose the algorithms, and decided what to build. A more accurate framing: **the AI was responsible for ~60% of the typing and ~0% of the decisions.**

---

## What Worked

### 1. Benchmark-Driven Engineering

Rather than picking defaults by intuition, every configuration decision was backed by measured data. The pipeline: design benchmark harness, run 16-config sweep, pick winner, run expanded 40-query and 209-query validation suites, confirm. This produced a documented evidence trail for why `llama-text-embed-v2` at 1024 dimensions with paragraph chunking became the production default. It also killed features (reranking, hybrid search) before they reached production — saving implementation time that would have been wasted.

### 2. Multi-Model AI Workflow

Using Claude Code for implementation and Codex CLI for review created genuine adversarial tension. Codex had no knowledge of or loyalty to Claude's implementation, so its review was unbiased. The three parallel review agents (implementation quality, CardDemo alignment, pattern comparison) found real bugs that I would have missed in manual review. This "AI implements, different AI reviews" pattern is the closest thing to a code review process available to a solo developer.

### 3. Detailed Plans Before Implementation

The most efficient sessions were the ones where I wrote a complete implementation plan (with pseudocode, file paths, and verification steps) before asking Claude to build anything. The reranking benchmark plan, for example, resulted in a single implementation pass with all 25 tests passing. Compare this to open-ended prompts like "add caching" which required multiple rounds of back-and-forth to converge on a design.

### 4. Pre-Search Architecture Phase

Spending 75 minutes on architecture decisions before writing any code was the highest-leverage activity of the sprint. Every decision made in that session (Pinecone, paragraph chunking, LangChain, k=10 default) held through the entire project without revision. The only pivot was the embedding model (from OpenAI text-embedding-3-small to llama-text-embed-v2), which was forced by benchmark data, not a failure of the Pre-Search reasoning.

### 5. Iterative Caching Architecture

The caching strategy evolved through four distinct iterations: in-memory L1/L2 with env flags, L1 JSON cache removed, L2 removed entirely (over-engineering detected), L1 reinstated as pre-sharded on-disk cache. The willingness to add, remove, and re-add cache layers based on observed behavior — rather than defending initial design choices — kept the architecture clean.

## What Didn't Work

### 1. Open-Ended Creative Prompts Without Constraints

Early in the UI design session, I asked Claude for Gemini prompts to generate UI mockups. The generated mockups showed COBOL code snippets prominently — but the actual app displays LLM-generated text with code as secondary context. I had to correct this: "the web UI is returning LLM text, that is using the underlying vector DB to prefill cobol code into context sent to the LLM." Lesson: creative AI works best with accurate functional constraints, not just aesthetic direction.

### 2. Hybrid Search on COBOL

Hybrid search (dense + sparse retrieval with reranking) scored 0.10 relevance versus 0.88 for dense-only. This was not a small miss — it was catastrophic. COBOL's hyphenated identifiers (`WS-RESP-CD`, `9910-DISPLAY-IO-STATUS`) tokenize at ~2 characters per token, producing a flood of spurious keyword matches that overwhelmed the reranker. I should have anticipated this from COBOL's syntax, but I invested a full benchmark cycle before discovering it. The benchmark investment was still worthwhile (it definitively killed the feature), but domain-specific tokenization analysis could have predicted the failure.

### 3. SSE as Initial Streaming Transport

SSE was implemented, debugged (StopIteration bug, false error states, JSON parse issues), and then replaced with WebSocket JSONL within the same day. In hindsight, I should have started with WebSocket from the beginning — the requirement for structured events (source references before LLM text) was obvious from the UI design. The SSE detour cost 3-4 hours and 6 commits that were functionally discarded.

### 4. AI Font Changes Without Permission

During the UI theming session, Claude changed typography choices without being asked. I had to push back explicitly: "Not acceptable." AI assistants will sometimes make aesthetic changes they consider improvements during implementation. Establishing clear boundaries ("do not change fonts unless I ask") would have prevented this friction.

### 5. Over-Engineering Cache Layers

The L2 answer cache was implemented, then removed the same day when I realized it added complexity without meaningful benefit for the query patterns in this application. Pre-computing search results (L1) made sense because the suggestion queries are known in advance. Caching LLM answers (L2) did not, because users rarely repeat exact queries. The AI implemented both because I asked — the over-engineering was my fault, not the AI's.

---

## Key Learnings

### 1. AI Velocity is Real but the Bottleneck Shifts

With AI coding assistants, the bottleneck shifts from "how fast can I type code" to "how fast can I make decisions." The 73 commits in 3 days (~24 per day, ~3.7 per active hour) represent 5-8x above typical solo developer velocity. But the rate-limiting step was never code generation — it was deciding what to build, reviewing the output, and running benchmarks. **AI makes implementation cheap; it does not make design cheap.**

### 2. Different AI Models for Different Tasks

Claude Code excelled at multi-file implementation from detailed plans. Codex CLI excelled at multi-agent code review with parallel analysis. Gemini excelled at visual mockup generation. No single model was best at everything. The multi-model workflow (Claude implements, Codex reviews, Gemini visualizes) was strictly better than using any single model for all tasks.

### 3. Benchmark Data Overrides Intuition

My Pre-Search decision defaulted to OpenAI `text-embedding-3-small` because I was already using OpenAI for the LLM. Benchmark data showed `llama-text-embed-v2` was both faster (0.365s vs 0.634s) and more accurate (0.88 vs 0.77 relevance). Similarly, I expected reranking to improve relevance — it did not. The development cost of the benchmark suite (~$0.20 in API calls, ~4 hours of implementation) was negligible compared to the value of the decisions it informed.

### 4. The 57% Co-Authorship Number is Misleading

42 of 73 commits carry the `Co-Authored-By: Claude Opus 4.6` trailer. This does not mean Claude wrote 57% of the project. It means Claude typed 57% of the commits — under my direction, from my plans, with my review. The AI's contribution was mechanical (converting plans to code), not intellectual (choosing what to build). The most important commits (Pre-Search decisions, benchmark result analysis, default selection) were human-only. **AI co-authorship measures typing, not thinking.**

### 5. Domain Knowledge Matters More Than Tool Sophistication

The paragraph chunking strategy — the single largest quality driver — came from understanding that COBOL paragraphs are semantic units corresponding to business operations. The preamble generation strategy came from understanding that COBOL identifiers (`COCRDUPC`, `1000-PROCESS-CREDIT-CARD`) are meaningless without context. The hybrid search failure came from COBOL's hostile tokenization properties. None of these insights came from the AI. They came from reading about COBOL's conventions and thinking about how they interact with embedding models. **The RAG techniques were generic; the domain application required human judgment.**
