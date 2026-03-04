# RAG Architecture Documentation — LegacyLens

## Vector DB Selection

I chose **Pinecone Serverless** for LegacyLens after evaluating Pinecone, Weaviate, Qdrant, ChromaDB, pgvector, and Milvus during the Pre-Search phase. The deciding factors were:

1. **Managed infrastructure.** With a one-week sprint and no prior vector database experience, I could not afford to spend time on self-hosting, schema design, or scaling configuration. Pinecone's free tier gave me a working index in under a minute.

2. **Integrated embedding models.** Pinecone offers server-side embedding via `llama-text-embed-v2` and `multilingual-e5-large`, eliminating a client-side API round-trip. This turned out to be a 30-40% latency win over OpenAI's embedding API (0.365s vs 0.59-0.69s average retrieval latency across 40 queries).

3. **Integrated reranking.** Pinecone's `search_records()` API accepts an inline `rerank` parameter, allowing me to benchmark three reranking models (`pinecone-rerank-v0`, `bge-reranker-v2-m3`, `cohere-rerank-3.5`) without adding any new infrastructure.

**Tradeoffs accepted:**

- **Vendor lock-in.** The integrated embedding/reranking APIs are Pinecone-specific. Moving to Qdrant or pgvector would require re-implementing embedding and search at the application layer.
- **Limited free tier.** 20 indexes maximum, which I hit during benchmarking (16 dense configs + 1 sparse + 3 rerank variants). I deleted unused indexes to stay within limits.
- **No local development.** Unlike ChromaDB or pgvector, Pinecone has no local mode. Every test query hits the cloud, which adds latency during development and makes offline testing impossible for retrieval-dependent tests.

## Embedding Strategy

**Model:** Pinecone integrated `llama-text-embed-v2` at 1024 dimensions.

This was selected through a systematic 16-configuration benchmark sweep covering 4 models, 3 dimension sizes, and 2 chunking strategies (800 total query runs on a 10-query suite, then validated on 40-query and 209-query suites):

| Config | Avg Latency | Avg Relevance |
|---|--:|--:|
| **llama-text-embed-v2 / 1024d / paragraph** | **0.365s** | **0.88** |
| text-embedding-3-small / 1536d / paragraph | 0.634s | 0.77 |
| text-embedding-3-large / 1536d / paragraph | 0.642s | 0.74 |
| multilingual-e5-large / 1024d / paragraph | 0.467s | 0.70 |

The Pre-Search decision defaulted to OpenAI `text-embedding-3-small` (1536d) because I was already using OpenAI for the LLM and wanted a single provider. The benchmark data forced a pivot: `llama-text-embed-v2` was both faster (server-side embedding) and more accurate (0.88 vs 0.77 relevance) than any OpenAI configuration. The 209-query generalization test confirmed this was not an artifact of the curated query set (0.89-0.92 relevance on auto-generated queries).

**Why it fits code understanding:** Each chunk includes a descriptive preamble (file name, program ID, paragraph name, COPY references, CALL targets) prepended to the raw COBOL source. The embedding model captures both the natural-language preamble and the code syntax. This combined signal is what drives the 0.88 relevance — stripping the preamble degrades relevance significantly. `llama-text-embed-v2` appears to handle this mixed-content format better than OpenAI's models, which were trained primarily on natural language.

## Chunking Approach

Legacy COBOL requires syntax-aware chunking because the language has rigid structural conventions that define semantic boundaries.

**Strategy by file type:**

| Type | Boundary Detection | Approach |
|---|---|---|
| COBOL programs (.cbl/.cob) | IDENTIFICATION/DATA/PROCEDURE DIVISIONs, 01-level records, PARAGRAPHs | Header chunk + DATA DIVISION (split at 01-level if >200 lines) + one chunk per paragraph. Short paragraphs (<5 lines) merged with predecessor. |
| Copybooks (.cpy) | File boundary | Single chunk per file (typically 30-100 lines). |
| BMS screen maps (.bms) | DFHMSD/DFHMDI macros | Split on map definition boundaries. |
| JCL job control (.jcl) | `//STEP EXEC` statements | Split on step boundaries with job card as header chunk. |
| Other mainframe (.dcl, .ddl, .ctl, etc.) | File boundary | Single chunk per file. |

**Paragraph-level chunking won decisively.** Every paragraph-chunked configuration outperformed its fixed-size counterpart in the benchmark (0.70-0.88 vs 0.47-0.60 relevance). COBOL paragraphs are natural semantic units — they correspond to business operations — and preserving these boundaries gives the embedding model meaningful code segments rather than arbitrary 500-token windows.

**Preamble generation** was critical. Each chunk gets a structured text preamble prepended before embedding:

```
File: COCRDUPC.cbl
Program: COCRDUPC
Layer: procedure
Paragraph: 1000-PROCESS-CREDIT-CARD (lines 150-200)
References: COPY COCOM01Y, COPY COTTL01Y
Calls: PERFORM 2000-VALIDATE-CARD, CALL 'COBRDVAL'
```

This preamble bridges the gap between natural language queries ("What does the credit card update program do?") and COBOL identifiers (`COCRDUPC`, `1000-PROCESS-CREDIT-CARD`).

**Production result:** 206 files across the AWS CardDemo codebase produced 1,018 chunks.

## Retrieval Pipeline

The query flow from user input to LLM answer:

1. **Query embedding.** The user's natural language question is embedded using the same `llama-text-embed-v2` model via Pinecone's integrated search API.

2. **Similarity search.** Pinecone returns the top-k most similar chunks (default k=10) by cosine similarity. An optional `file_type` filter narrows results to specific file extensions (e.g., only `.cbl` or only `.jcl`).

3. **Context assembly.** Retrieved chunks are formatted with their metadata (file name, line numbers, chunk type, relevance score) and concatenated into a context block. A semantic summary of each chunk is generated and included.

4. **LLM generation.** The context block and user question are sent to the LLM (default: Gemini 2.5 Flash Lite via OpenRouter) with a system prompt that instructs the model to ground answers in the provided context and cite sources using `[File:Line-Line]` format. A verbosity parameter (succinct/regular/detailed) controls answer length.

5. **Streaming delivery.** Responses stream via WebSocket JSONL. Source references are sent as discrete events before the LLM generation begins, so the user sees relevant files immediately while the answer generates.

**Re-ranking was evaluated but not shipped.** Three reranking models were benchmarked against the baseline:

| Config | Avg Latency | Avg Relevance |
|---|--:|--:|
| Baseline (dense only) | 0.365s | 0.88 |
| + pinecone-rerank-v0 | 0.867s | 0.88 |
| + cohere-rerank-3.5 | 0.609s | 0.86 |
| + bge-reranker-v2-m3 | 0.811s | 0.86 |
| + hybrid (dense+sparse+rerank) | 0.967s | 0.10 |

The baseline was already so accurate that reranking could not improve relevance — it only added latency (67-137% slower). Hybrid search (combining dense and sparse retrieval) was catastrophic: COBOL's verbose hyphenated identifiers (`WS-RESP-CD`, `9910-DISPLAY-IO-STATUS`) tokenize at ~2 chars/token, producing a flood of spurious keyword matches that overwhelmed the reranker.

**Caching.** A pre-computed on-disk L1 cache stores search results for 209 suggestion queries (one JSON file per query, sharded in `web/cache/`). Cached queries skip the Pinecone round-trip entirely (0ms vs ~400ms). The cache is toggleable per-request via the web UI and regenerated with `scripts/warmup_cache.py` after index changes.

## Failure Modes

1. **Abstract queries perform worst.** Queries like "find all file I/O operations" and "CICS screen navigation" consistently scored lowest across all configurations. These queries match many chunks weakly rather than a few chunks strongly. The retrieval model favors specificity.

2. **Cross-cutting concerns are hard to retrieve.** Questions about error handling patterns, logging conventions, or coding standards span the entire codebase. No single chunk contains "the answer" — the model must synthesize across many partial matches.

3. **Copybook content is underrepresented.** Copybooks define data structures used by many programs, but each copybook is a single chunk. When a user asks about a specific data field, the relevant copybook may rank below the programs that use it because the programs have richer preamble metadata.

4. **COBOL tokenization is hostile to keyword models.** Hyphenated names like `ACCT-MASTER-FILE-STATUS` become 4+ tokens each. Sparse/keyword retrieval models treat each token independently, producing false matches that degrade hybrid search (0.10 relevance vs 0.88 for dense-only).

5. **Large DATA DIVISIONs can dilute context.** Even with the 200-line split threshold, some DATA DIVISION chunks are large enough that the preamble represents a small fraction of the embedded text, weakening semantic signal.

## Performance Results

### Retrieval Performance

| Metric | Result |
|---|---|
| Average retrieval latency (40-query suite) | 0.365s |
| Average relevance (40-query suite, top-10) | 0.88 |
| Average relevance (209-query suite, top-10) | 0.92 |
| Relevance at top-5 (209-query suite) | 0.89 |
| Codebase coverage | 100% (206/206 files, 1,018 chunks) |

### End-to-End Latency (with LLM generation)

| Verbosity | Mean Latency | p50 | p95 |
|---|--:|--:|--:|
| Succinct | 1.51s | 1.54s | 1.78s |
| Regular | 2.06s | 2.10s | 2.49s |
| Detailed | 3.28s | 3.47s | 4.42s |

Measured with Gemini 2.5 Flash Lite via OpenRouter on a 10-query spot check (March 4, 2026). The <3 second target is met for succinct and regular verbosity.

### Ingestion Throughput

| Config | Pipeline Total | LOC/s | Target |
|---|--:|--:|---|
| llama-text-embed-v2 (production) | 40.8s | 1,184 | PASS (10K+ LOC in <5 min) |
| multilingual-e5-large | 17.1s | 2,819 | PASS |
| text-embedding-3-small | 52.4s | 922 | PASS |

48,327 LOC across 206 files. Discovery (<1ms) and chunking (0.1s) are negligible; embed+upsert dominates.

### LLM Answer Quality (graded by Claude Opus)

| Dimension | Succinct | Regular | Detailed |
|---|--:|--:|--:|
| Accuracy | 4.30 | 4.50 | 4.30 |
| Completeness | 3.10 | 3.90 | 4.00 |
| Citation Quality | 3.40 | 3.50 | 4.20 |
| Clarity | 4.40 | 4.80 | 4.90 |
| Overall | 3.40 | **4.20** | 4.10 |

Regular verbosity provides the best quality-to-latency balance.
