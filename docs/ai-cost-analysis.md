# AI Cost Analysis — LegacyLens

## Part A: Development & Testing Costs

### Development Activity

- **Duration:** 3 days (March 2-4, 2026), approximately 20 active coding hours
- **AI sessions:** 75 transcripts across Claude Code (Opus 4.6) and OpenAI Codex CLI (GPT-5.3-codex)
- **Commits:** 73 total, 42 co-authored with Claude Opus 4.6

### Embedding API Costs

**Production index (Pinecone integrated `llama-text-embed-v2`):**
- 1,018 chunks embedded server-side via Pinecone — **$0.00** (included in Pinecone plan)

**Benchmark campaign (16 index configurations):**
- 8 OpenAI indexes (text-embedding-3-small and text-embedding-3-large at 3 dimension sizes each, 2 chunking strategies)
- 1,018 chunks per index = 8,144 total OpenAI embedding calls
- Average chunk size: ~300 tokens (COBOL paragraphs are short; preamble adds ~80 tokens)
- Total tokens embedded: ~2.4M tokens
- OpenAI text-embedding-3-small: $0.02/1M tokens → ~$0.03
- OpenAI text-embedding-3-large: $0.13/1M tokens → ~$0.16
- **Subtotal embedding costs: ~$0.19**

**Query embedding during benchmarks:**
- 800 queries (16-config sweep) + 640 queries (40-query suite) + 418 queries (209-query suite) + 320 queries (reranking suite) = ~2,178 query embeddings
- Average query: ~20 tokens
- Total: ~44K tokens → **~$0.01**

**Total embedding API spend: ~$0.20**

### LLM API Costs (Answer Generation)

**During development and testing:**
- Manual testing of the web UI and CLI: estimated 100-150 queries across GPT-4o-mini, GPT-4o, GPT-4.1-nano, Gemini 2.5 Flash Lite
- LLM benchmark runs: 5-10 queries each across 8 models (GPT-4o-mini, GPT-4o, GPT-4.1-nano, GPT-4.1-mini, GPT-4.1, GPT-5-nano, GPT-5-mini, GPT-5)
- LLM quality grading: 30 response evaluations by Claude Opus (via OpenRouter)

Estimated token consumption:
- Input (context + system prompt per query): ~4,000 tokens (10 chunks at ~300 tokens + system prompt + query)
- Output per query: ~200-500 tokens (depending on verbosity)
- Total queries: ~250
- Total input tokens: ~1M
- Total output tokens: ~100K

Cost estimates by model:
- GPT-4o-mini ($0.15/$0.60 per 1M in/out): ~$0.15 + $0.06 = ~$0.21
- GPT-4o ($2.50/$10 per 1M): ~$0.25 + $0.10 = ~$0.35
- GPT-4.1-nano ($0.10/$0.40): ~$0.01
- Gemini 2.5 Flash Lite (via OpenRouter, ~$0.015/$0.06): ~$0.02
- Claude Opus grading (via OpenRouter, ~$15/$75 per 1M): 30 grades at ~2K input + ~500 output each → ~$1.00

**Total LLM API spend: ~$1.60**

### Vector Database Costs

- **Pinecone Serverless:** Free tier for MVP development, upgraded to Starter plan ($0/month with 20 index limit)
- During benchmarking, I used all 20 index slots (16 dense + 1 sparse + rerank variants). No additional charges.
- Storage: 1,018 vectors × 16 indexes × 1024 dimensions = ~16.6M dimensions → well within free tier limits
- **Total Pinecone spend: $0.00**

### AI Coding Assistant Costs

- **Claude Code (Opus 4.6):** ~60 sessions across the 3-day sprint. Estimated at $0.08-0.15 per session (Anthropic API pricing for Opus). Approximately **$6-9** total.
- **OpenAI Codex CLI (GPT-5.3-codex):** ~8 sessions. Estimated at $0.10-0.20 per session. Approximately **$1-2** total.

### Railway Deployment

- **Railway hosting:** Free trial tier for the web application. **$0.00** during development.

### Total Development & Testing Spend

| Category | Cost |
|---|--:|
| Embedding APIs | $0.20 |
| LLM APIs (answer generation + grading) | $1.60 |
| Vector database (Pinecone) | $0.00 |
| AI coding assistants (Claude + Codex) | $7-11 |
| Deployment (Railway) | $0.00 |
| **Total** | **~$9-13** |

The development cost was remarkably low. Embedding costs were negligible because COBOL codebases are small by modern standards (~48K LOC). The dominant cost was the AI coding assistants, not the RAG infrastructure.

---

## Part B: Production Cost Projections

### Assumptions

- **Query pattern:** Each user query triggers one embedding call + one Pinecone search + one LLM generation
- **Queries per user per day:** 10 (developer actively exploring a codebase)
- **Active days per month:** 22 (weekdays)
- **Average input tokens per query:** 4,000 (10 chunks at ~300 tokens + system prompt + query text)
- **Average output tokens per query:** 300 (regular verbosity)
- **Retrieval latency:** ~0.4s (Pinecone integrated embedding + search)
- **LLM latency:** ~1.5-3.3s depending on verbosity
- **Default model:** Gemini 2.5 Flash Lite via OpenRouter
- **top_k:** 10
- **Embedding model:** Pinecone integrated `llama-text-embed-v2` (no per-query embedding cost)
- **L1 cache hit rate:** 30% for suggestion queries, 0% for novel queries → blended 10% hit rate
- **Codebase re-ingestion:** Once per month (incremental updates)

### LLM Model Pricing (via OpenRouter)

| Model | Input ($/1M tokens) | Output ($/1M tokens) |
|---|--:|--:|
| Gemini 2.5 Flash Lite (default) | $0.015 | $0.06 |
| GPT-4o-mini | $0.15 | $0.60 |
| GPT-4.1-nano | $0.10 | $0.40 |

### Cost Projections

#### With Gemini 2.5 Flash Lite (Default)

| Component | 100 Users | 1,000 Users | 10,000 Users | 100,000 Users |
|---|--:|--:|--:|--:|
| Queries/month | 19,800 | 198,000 | 1,980,000 | 19,800,000 |
| LLM input tokens/month | 79.2M | 792M | 7.92B | 79.2B |
| LLM output tokens/month | 5.9M | 59.4M | 594M | 5.94B |
| **LLM cost** | **$1.54** | **$15.45** | **$154.50** | **$1,545** |
| Pinecone (Serverless) | $0 (free) | $30 | $100 | $500 |
| OpenRouter overhead | ~$0 | ~$0 | ~$0 | ~$0 |
| Embedding (Pinecone integrated) | $0 | $0 | $0 | $0 |
| Re-ingestion (monthly) | $0 | $0 | $0 | $0 |
| **Total/month** | **~$2** | **~$45** | **~$255** | **~$2,045** |

#### With GPT-4o-mini

| Component | 100 Users | 1,000 Users | 10,000 Users | 100,000 Users |
|---|--:|--:|--:|--:|
| **LLM cost** | **$15.42** | **$154.20** | **$1,542** | **$15,420** |
| Pinecone (Serverless) | $0 | $30 | $100 | $500 |
| **Total/month** | **~$15** | **~$184** | **~$1,642** | **~$15,920** |

#### With GPT-4.1-nano

| Component | 100 Users | 1,000 Users | 10,000 Users | 100,000 Users |
|---|--:|--:|--:|--:|
| **LLM cost** | **$10.28** | **$102.80** | **$1,028** | **$10,280** |
| Pinecone (Serverless) | $0 | $30 | $100 | $500 |
| **Total/month** | **~$10** | **~$133** | **~$1,128** | **~$10,780** |

### Key Observations

1. **The LLM is the cost driver, not the vector database.** Pinecone Serverless with integrated embedding eliminates per-query embedding costs entirely. At 100K users, the LLM accounts for 75-97% of total cost depending on model choice.

2. **Gemini Flash Lite is 10x cheaper than GPT-4o-mini** with comparable quality (4.20 vs ~4.5 overall grade on our benchmark). This was the primary reason for switching the default model.

3. **The L1 cache provides cost reduction for repeated queries.** The 209 pre-computed suggestion queries represent common exploration patterns. A 10% cache hit rate at 100K users saves ~$150/month on LLM costs.

4. **OpenRouter prompt caching** (`cache_control` hints on the system message) can reduce input token costs by 50-90% for repeated system prompts. This is implemented but not reflected in the projections above. At 100K users with Gemini, this could save ~$500-700/month.

5. **Scaling to multiple codebases** would add vector storage costs (Pinecone charges per vector stored) but not significantly increase per-query LLM costs. Each additional 50K-LOC codebase adds roughly 1,000 vectors.

### Cost Optimization Levers (Not Yet Implemented)

| Optimization | Estimated Savings |
|---|---|
| Aggressive L1 caching (pre-compute top 1,000 queries) | 20-40% LLM cost reduction |
| Response length capping (succinct default) | 30% output token reduction |
| Tiered model selection (nano for simple queries, full for complex) | 40-60% LLM cost reduction |
| Pinecone prompt caching at scale | 50-90% input token reduction |
| Client-side answer caching (browser localStorage) | Varies by repeat query rate |
