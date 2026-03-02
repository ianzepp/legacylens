# LegacyLens

A RAG-powered system that makes legacy COBOL codebases queryable via natural language. Built for the AWS CardDemo credit card management application (~40K LOC across 206 mainframe source files).

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
| Embedding model | OpenAI text-embedding-3-small (1536d) | Cost-effective, good quality for code |
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
| `PINECONE_API_KEY` | Yes | Pinecone API key |
| `PINECONE_INDEX_NAME` | No | Index name (default: `legacylens`) |
| `CARDDEMO_PATH` | For ingestion | Path to CardDemo `app/` directory |
| `USE_OLLAMA` | No | Set `true` to use Ollama for local embeddings |

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

### API

```bash
# Ask with LLM answer
curl -X POST http://localhost:8000/api/ask \
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

## Testing

```bash
# Unit tests (no API keys needed)
CARDDEMO_PATH=/path/to/carddemo/app pytest tests/ -v

# Include live retrieval tests against Pinecone
CARDDEMO_PATH=/path/to/carddemo/app LEGACYLENS_RUN_LIVE_TESTS=1 pytest tests/ -v
```

123 tests covering parser, chunker, ingestion, vector store, chain formatting, and live retrieval quality.

## Project Structure

```
legacylens/
├── legacylens/
│   ├── config.py          # Pydantic settings
│   ├── models.py          # CodeChunk, QueryResult dataclasses
│   ├── parser.py          # COBOL structure parser (divisions, paragraphs, COPY/CALL)
│   ├── chunker.py         # Syntax-aware chunking (COBOL/BMS/JCL/copybook)
│   ├── embeddings.py      # OpenAI / Ollama embedding generation
│   ├── vectorstore.py     # Pinecone index operations
│   ├── ingest.py          # Orchestrator: discover → chunk → embed → store
│   ├── retriever.py       # Query embedding + Pinecone search
│   ├── chain.py           # LangChain RAG chain (context + LLM)
│   └── cli.py             # Typer CLI (ask, search, ingest)
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
    └── test_retrieval.py  # 13 tests (6 live + 7 chunking)
```

## Deployment

```bash
# Railway / Render
uvicorn web.app:app --host 0.0.0.0 --port $PORT
```

Set `OPENAI_API_KEY` and `PINECONE_API_KEY` as environment variables. The Pinecone index persists in the cloud — ingestion only needs to run once locally.
