# Price DB

Database pencarian harga material untuk proses tender. Memungkinkan pencarian cepat berbasis arti (semantic search) dari nama material yang bervariasi — misalnya query "kabel listrik 4 mm" akan menemukan "Kabel NYY 4x4 mm" meskipun kata "listrik" tidak ada di nama produk.

## Tech Stack

- **Backend**: FastAPI (Python 3.12)
- **Database**: PostgreSQL 16 + [pgvector](https://github.com/pgvector/pgvector) 0.8.2
- **Embeddings**: [Ollama](https://ollama.com) lokal dengan model `nomic-embed-text` (768 dim)
- **Search**: Hybrid scoring — 40% cosine similarity + 60% trigram + 0% tsvector (auto-tuned via eval harness)
- **Deployment**: Docker Compose
- **Admin UI**: Adminer (PostgreSQL web admin)

## Architecture

```
┌──────────────┐      ┌────────────────┐
│   FastAPI    │─────▶│  PostgreSQL    │
│   /search    │      │  + pgvector    │
│   /api/...   │      │  + pg_trgm     │
└──────┬───────┘      └────────────────┘
       │
       │ embed query
       ▼
┌──────────────┐
│    Ollama    │  nomic-embed-text (768 dim)
│  localhost   │  OpenAI-compatible /v1/embeddings
└──────────────┘
```

## Features

### v1 (main branch)
- Upload Excel/CSV ke database dengan parsing harga Indonesia (Rp 42.300/m, dll)
- Trigram similarity search untuk pencocokan fuzzy
- Deduplication via `row_hash`
- Category rules untuk klasifikasi otomatis
- Batch upload dengan tracking error/duplicate
- Export hasil pencarian ke CSV/Excel

### v2 (v2-upgrade branch — current dev)
- **Semantic search via embedding** — query parafrase ditangani benar
- **Hybrid scoring** dengan weights yang di-tune dari eval set
- **Eval harness** untuk grid search optimal weights
- **HNSW index** untuk vector search yang cepat
- **Auto-fallback** ke lexical search jika embedding gagal

## Quick Start

### Prerequisites

- Docker + Docker Compose
- Ollama running di host: `curl -fsSL https://ollama.com/install.sh | sh`
- Model: `ollama pull nomic-embed-text`

### Setup

```bash
# Clone
git clone https://github.com/britamax/price-db.git
cd price-db

# Configure
cp .env.example .env
# Edit .env: set POSTGRES_PASSWORD, APP_ADMIN_USER, APP_ADMIN_PASSWORD

# Start
sudo docker compose up -d

# Install PostgreSQL extensions
sudo docker compose exec postgres psql -U price_admin -d pricedb -f /docker-entrypoint-initdb.d/01-extensions.sql

# Run migrations (v2)
sudo docker compose exec postgres psql -U price_admin -d pricedb -f /docker-entrypoint-initdb.d/../migrations/002_add_embedding_columns.sql
sudo docker compose exec postgres psql -U price_admin -d pricedb -f /docker-entrypoint-initdb.d/../migrations/003_hnsw_index_and_hybrid_search.sql

# Backfill embeddings
sudo docker compose exec web python backfill_embeddings.py
```

App: http://localhost:8080
Adminer: http://localhost:8081

### Eval

```bash
# Run with default weights
sudo docker compose exec web python -m eval.evaluate

# Grid search optimal weights
sudo docker compose exec web python -m eval.evaluate --sweep
```

Current eval metrics (20 test queries on 55-row corpus):
- **Recall@10**: 100%
- **MRR**: 0.854 with weights cosine 0.4 / trigram 0.6 / tsvector 0.0

## API

### Search

```bash
# Hybrid search (default)
curl "http://localhost:8080/api/search?q=kabel+listrik+4+mm&limit=5"

# Force lexical-only (no embedding)
curl "http://localhost:8080/api/search?q=besi+beton&mode=lexical"
```

### Batch search

```bash
curl -X POST http://localhost:8080/api/batch-search \
  -H "Content-Type: application/json" \
  -d '{"queries":["kabel nya 1.5","besi beton ulir 13"],"limit":3}'
```

## Roadmap

- [x] Phase 1: Semantic search foundation (pgvector + Ollama + hybrid scoring)
- [ ] Phase 2: Alias & unit normalization (per-unit price comparison)
- [ ] Phase 3: Admin UI (Search Playground, Alias Manager, Quality Dashboard)
- [ ] Phase 4: Batch tender processing (Redis + ARQ background jobs)
- [ ] Phase 5: Source tracking, regional filter, supplier reliability
- [ ] Phase 6: WhatsApp/Telegram bot integration

See [`.hermes/plans/`](/.hermes/plans/) for detailed phase-by-phase plan.

## License

MIT
