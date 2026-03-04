# Slide Generation Prompts for LegacyLens

Each prompt below corresponds to one H2 section from the submission docs. Paste any prompt into Gemini to generate a presentation slide.

---

### Slide 0: Title Card

Create a presentation title slide for "LegacyLens". Subtitle: "RAG-Powered Code Explorer for Legacy COBOL Codebases". Below the subtitle, show three key stats in a horizontal row: "206 files / 1,018 chunks / 0.88 relevance". At the bottom, show: "AWS CardDemo — 40K LOC credit card management system" and "Built in 3 days, 73 commits, 100% AI-assisted". Use a dark theme with amber/green phosphor terminal aesthetic — the visual language of a mainframe COBOL terminal designed by a Fallout Pip-Boy artist. Include subtle CRT scanline texture and a faint green glow.

---

## RAG Architecture Doc

### Slide 1: Vector DB Selection

Create a presentation slide titled "Vector DB Selection: Pinecone Serverless". Show three winning factors as a vertical list with icons: (1) Managed infrastructure — zero self-hosting overhead in a one-week sprint, (2) Integrated embedding models — server-side llama-text-embed-v2 eliminates client round-trip, 30-40% latency win (0.365s vs 0.59-0.69s), (3) Integrated reranking — benchmarked 3 reranking models via a single API parameter. Below the list, add a "Tradeoffs Accepted" callout box with three items: vendor lock-in, 20-index free tier limit, no local/offline mode. Use a clean dark theme with amber/green accents.

### Slide 2: Embedding Strategy

Create a presentation slide titled "Embedding Strategy: Benchmark-Driven Selection". Show a 4-row comparison table: llama-text-embed-v2/1024d at 0.365s latency and 0.88 relevance (highlighted as winner), text-embedding-3-small/1536d at 0.634s and 0.77, text-embedding-3-large/1536d at 0.642s and 0.74, multilingual-e5-large/1024d at 0.467s and 0.70. Below the table, add a key insight callout: "Selected via 16-config benchmark sweep (800 query runs). Validated on 209-query suite: 0.89-0.92 relevance. Descriptive preambles (file name, program ID, COPY refs, CALL targets) prepended to each chunk are the key quality driver." Dark theme, amber/green accents.

### Slide 3: Chunking Approach

Create a presentation slide titled "Chunking: Syntax-Aware COBOL Splitting". Show a table with 5 rows for file types: COBOL programs (.cbl/.cob) → header + DATA DIVISION (split at 01-level if >200 lines) + one chunk per paragraph, Copybooks (.cpy) → single chunk per file, BMS maps (.bms) → split on DFHMDI boundaries, JCL (.jcl) → split on EXEC step boundaries, Other mainframe → single chunk. Below, show a "Preamble Example" code block: "File: COCRDUPC.cbl / Program: COCRDUPC / Paragraph: 1000-PROCESS-CREDIT-CARD (lines 150-200) / References: COPY COCOM01Y / Calls: PERFORM 2000-VALIDATE-CARD". Add a key stat: "206 files → 1,018 chunks. Paragraph chunking scored 0.70-0.88 relevance vs 0.47-0.60 for fixed-size." Dark theme.

### Slide 4: Retrieval Pipeline

Create a presentation slide titled "Retrieval Pipeline: 5-Step Query Flow". Show a horizontal flow diagram with 5 steps connected by arrows: (1) Query Embedding — same llama-text-embed-v2 model, (2) Pinecone Search — top-10 cosine similarity with optional file_type filter, (3) Context Assembly — chunks formatted with metadata + semantic summary, (4) LLM Generation — Gemini 2.5 Flash Lite via OpenRouter, grounded answers with [File:Line-Line] citations, (5) WebSocket Streaming — JSONL with early source delivery before LLM text. Below the flow, add a "Rejected" callout: "Reranking: same relevance, 67-137% slower. Hybrid search: 0.10 relevance (COBOL tokenization hostile to keyword models)." Also note: "L1 Cache: 209 pre-computed suggestion queries skip Pinecone entirely (0ms vs 400ms)." Dark theme.

### Slide 5: Failure Modes

Create a presentation slide titled "Failure Modes & Edge Cases". Show 5 numbered items in a vertical list: (1) Abstract queries — "find all file I/O operations" matches many chunks weakly, retrieval favors specificity, (2) Cross-cutting concerns — error handling patterns span entire codebase, no single chunk contains the answer, (3) Copybook underrepresentation — single-chunk copybooks rank below programs with richer preamble metadata, (4) COBOL tokenization — hyphenated names like ACCT-MASTER-FILE-STATUS become 4+ tokens, breaks sparse/keyword retrieval, (5) Large DATA DIVISIONs — even with 200-line split threshold, preamble can be diluted in large chunks. Use amber warning icons. Dark theme.

### Slide 6: Performance Results

Create a presentation slide titled "Performance Results". Show three metric groups. Group 1 "Retrieval": avg latency 0.365s, relevance 0.88 (40 queries) / 0.92 (209 queries), 100% codebase coverage (206 files, 1,018 chunks). Group 2 "End-to-End Latency" as a 3-row table: Succinct 1.51s, Regular 2.06s, Detailed 3.28s — with a checkmark showing <3s target met for succinct and regular. Group 3 "LLM Quality (graded by Claude Opus)" as a table: Accuracy 4.5, Completeness 3.9, Citation Quality 3.5, Clarity 4.8, Overall 4.2 — for Regular verbosity (best balance). Add ingestion stat: "48K LOC ingested in 40.8s (1,184 LOC/s), target was <5 min." Dark theme, green for passing metrics.

---

## AI Cost Analysis

### Slide 7: Development Costs

Create a presentation slide titled "Development & Testing Costs: $9-13 Total". Show a cost breakdown table: Embedding APIs $0.20, LLM APIs (generation + grading) $1.60, Vector database (Pinecone free tier) $0.00, AI coding assistants (Claude Code + Codex CLI) $7-11, Deployment (Railway free trial) $0.00, Total ~$9-13. Add a key insight callout: "The dominant cost was AI coding assistants, not RAG infrastructure. Embedding costs were negligible because COBOL codebases are small (~48K LOC). 75 AI sessions across 3 days, 73 commits." Dark theme, amber/green accents.

### Slide 8: Production Cost Projections

Create a presentation slide titled "Production Cost Projections (Monthly)". Show a comparison table with 4 user scales (100 / 1,000 / 10,000 / 100,000 users) across 3 models: Gemini Flash Lite at $2 / $45 / $255 / $2,045, GPT-4o-mini at $15 / $184 / $1,642 / $15,920, GPT-4.1-nano at $10 / $133 / $1,128 / $10,780. Below, list assumptions: 10 queries/user/day, 22 active days/month, 4K input + 300 output tokens/query, top_k=10, 10% L1 cache hit rate. Add a callout: "LLM is the cost driver (75-97% of total), not the vector DB. Gemini Flash Lite is 10x cheaper than GPT-4o-mini with comparable quality (4.2 vs ~4.5 overall grade)." Dark theme, green for lowest-cost option.

---

## AI Development Log

### Slide 9: Tools & Workflow

Create a presentation slide titled "AI Tools & Workflow". Show three tool cards side by side: (1) Claude Code (Opus 4.6) — 60 sessions, 42 commits (57%), primary implementer: multi-file refactors, test suites, UI, production hardening, (2) Codex CLI (GPT-5.3-codex) — 8 sessions, 31 commits (43%), multi-agent code review + implementation, spawned 3 parallel review agents that found 8 real bugs, (3) Gemini — UI mockup generation, 3 aesthetic direction prompts for Fallout/mainframe theme. Below, show the workflow pattern as a cycle: "I design → AI implements → I review → I commit". Add a key stat: "100% of commits were AI-assisted. Claude handled the majority of implementation; Codex handled review and the remaining implementation. The human contribution was architecture, decisions, and review — not typing." Dark theme.

### Slide 10: Architecture Decisions

Create a presentation slide titled "5 Architecture Decisions, All Data-Driven". Show a vertical timeline with 5 decision points: (1) Mar 2 — Pinecone Serverless with integrated embedding (Pre-Search phase, 75-min guided walkthrough), (2) Mar 2 — Paragraph-level chunking over fixed-size (from insight: "COBOL comments are almost more important than the code"), (3) Mar 3 — Dense-only retrieval, reranking/hybrid rejected (benchmark killed both features), (4) Mar 3 — SSE → WebSocket JSONL migration (structured events before LLM stream), (5) Mar 3 — Gemini Flash Lite as default (10x cheaper, comparable quality). Each point should show the outcome in a sub-line. Dark theme.

### Slide 11: Effective Prompts

Create a presentation slide titled "5 Prompts That Drove Results". Show 5 prompt cards, each with the quoted prompt and a one-line result: (1) "Please walk me through the presearch phase questions, not all at once." → 75-min guided architecture session, every decision held through the sprint. (2) "Sanity check the work... based on the files in docs, the target COBOL repo, and a reference RAG implementation" → Codex spawned 3 parallel review agents, found 8 actionable bugs. (3) "A mainframe COBOL had a baby with a fallout designer" → Became the creative brief for the entire UI identity. (4) "Implement the following plan: [detailed markdown with pseudocode, file paths, verification steps]" → Single implementation pass, 25 tests passing on first run. (5) "Instead of the simplest fix, what is the correct solution here?" → Pushed AI past default-to-easy toward production-grade solutions. Dark theme, use quotation mark styling for prompts.

### Slide 12: What Worked / What Didn't

Create a presentation slide with two columns titled "What Worked" and "What Didn't". Left column (green checkmarks): Benchmark-driven engineering (killed features before production), Multi-model workflow (Claude implements, Codex reviews, Gemini visualizes), Detailed plans before implementation (single-pass execution), Pre-Search architecture phase (75 min that saved days), Iterative caching (add/remove/re-add based on data). Right column (red X marks): Open-ended creative prompts without functional constraints, Hybrid search on COBOL (0.10 relevance, catastrophic), SSE before WebSocket (3-4 hours wasted on wrong transport), AI making unauthorized font changes, Over-engineering L2 cache layer (removed same day). Dark theme.

### Slide 13: Key Learnings

Create a presentation slide titled "Key Learnings". Show 5 insight cards with bold headlines and one-sentence explanations: (1) "AI shifts the bottleneck from typing to decisions" — 73 commits in 3 days (24/day), but the rate limiter was always design, not code generation. (2) "Different models for different tasks" — Claude implements, Codex reviews, Gemini visualizes. No single model was best at everything. (3) "Benchmark data overrides intuition" — Pre-Search defaulted to OpenAI embeddings. Benchmarks showed llama-text-embed-v2 was faster AND more accurate. $0.20 in API costs informed every production default. (4) "100% AI-assisted doesn't mean 0% human" — Every commit was AI-generated (57% Claude, 43% Codex), but the human drove every architecture decision, benchmark plan, and review. AI did the typing; the human did the thinking. (5) "Domain knowledge > tool sophistication" — Paragraph chunking, preamble generation, and hybrid search failure all required understanding COBOL, not RAG techniques. Dark theme.
