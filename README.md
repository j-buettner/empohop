# Planetary Health Knowledge Graph

A pipeline for extracting structured knowledge from academic documents about planetary health — specifically mobilisations towards living in harmony with nature through economic activities beyond GDP.

The pipeline identifies **Events**, **Actors**, **Concepts**, **Publications**, and **Locations**, resolves duplicate entities, scores extraction quality, and exposes the result as a browsable knowledge graph.

---

## Quick start

```bash
# 1. Install dependencies
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Configure credentials
cp .env.example .env          # then fill in ANTHROPIC_API_KEY

# 3. Extract a document
python extract_document.py path/to/document.pdf --output-dir data/extracted

# 4. Run entity + relationship extraction
python llm_processor.py data/extracted/document_chunks.json --output-dir data/processed

# 5. Evaluate quality
python run_critic.py data/processed/document_knowledge_graph.json

# 6. Start the human review interface
python main.py --tasks-file data/review/review_tasks.json

# 7. Apply corrections
python consolidate_reviews.py --kg data/processed/document_knowledge_graph.json

# 8. Browse the result
python server.py data/processed/document_knowledge_graph.json
# open http://localhost:8080
```

---

## Pipeline overview

```
PDF / DOCX
    │
    ▼
extract_document.py        →  data/extracted/*_chunks.json
    │
    ▼
llm_processor.py           →  data/processed/*_knowledge_graph.json
    │                         data/processed/*_disambiguation_report.json
    ▼
run_critic.py              →  data/critic_results/*_critic_evaluation.json
    │
    ▼
main.py  (human review UI) →  data/review/corrected/*.json
    │
    ▼
consolidate_reviews.py     →  data/processed/*_reviewed_<timestamp>.json
    │
    ▼
server.py  (visualisation)
```

---

## Installation

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Python 3.8+ required.**

### Environment variables

Copy `.env.example` to `.env` and set your values. The only required variable is:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Optional variables (with defaults shown):

| Variable | Default | Description |
|---|---|---|
| `KG_MODEL` | `claude-sonnet-4-20250514` | Claude model used for extraction and critic |
| `KG_MAX_TOKENS` | `8000` | Max tokens per LLM response |
| `KG_FILE` | *(see `.env.example`)* | Knowledge graph file served by `server.py` |
| `KG_FILE_REVIEW` | *(see `.env.example`)* | Knowledge graph file used by the review UI |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `LOG_FORMAT` | plain text | Set to `json` for structured log output |

---

## Step-by-step usage

### Step 1 — Extract a document

```bash
# Basic extraction (standard PDF parser)
python extract_document.py path/to/document.pdf

# With Docling (better layout and OCR support)
python extract_document.py path/to/document.pdf --use-docling

# Enable OCR for scanned documents
python extract_document.py path/to/document.pdf --use-docling --ocr

# Filter out References and Index sections
python extract_document.py path/to/document.pdf --use-docling --filter-sections

# Control chunk size (tokens per chunk, default 1000)
python extract_document.py path/to/document.pdf --chunk-size 2000

# Export a readable Markdown version with chunk boundaries marked
python extract_document.py path/to/document.pdf --use-docling --export-markdown-with-chunks
```

Output: `data/extracted/<document>_chunks.json`

---

### Step 2 — Extract entities and relationships

```bash
# Full extraction (all entity types + relationships)
python llm_processor.py data/extracted/document_chunks.json --output-dir data/processed

# Limit to specific entity types
python llm_processor.py data/extracted/document_chunks.json \
  --entity-types event actor concept

# Process only a subset of chunks (useful for testing)
python llm_processor.py data/extracted/document_chunks.json --chunk-range 0-10

# Apply manual entity mappings to normalise known variants
python llm_processor.py data/extracted/document_chunks.json \
  --manual-mappings my_mappings.json

# Write intermediate results after each chunk (resumable)
python llm_processor.py data/extracted/document_chunks.json \
  --update-after-each --output-dir data/processed
```

Output: `data/processed/<document>_knowledge_graph.json` and per-entity CSVs.

**Manual mappings** tell the resolver that two names refer to the same entity:

```json
{
  "event": {
    "Rio Summit": "United Nations Conference on Environment and Development"
  },
  "actor": {
    "WWF": "World Wildlife Fund"
  }
}
```

---

### Step 3 — Quality assessment (critic)

```bash
python run_critic.py data/processed/document_knowledge_graph.json
```

Flags:

| Flag | Default | Description |
|---|---|---|
| `--critic-model` | *(from `KG_MODEL`)* | Model used for critic evaluation |
| `--min-confidence` | `3.0` | Flag entities below this score (1–5) |
| `--batch-size` | `50` | Items evaluated per API call batch |
| `--verbose` | off | Enable DEBUG logging |

Output: `data/critic_results/<document>_critic_evaluation.json`

---

### Step 4 — Human review

```bash
# Start the review server
python main.py --tasks-file data/review/review_tasks.json \
               --output-dir data/review/corrected

# Open http://localhost:8000 in your browser
```

The interface shows each flagged entity alongside its confidence score, extracted supporting text, and suggested corrections.

---

### Step 5 — Apply corrections

```bash
python consolidate_reviews.py \
  --kg data/processed/document_knowledge_graph.json \
  --review data/review
```

Output: `data/processed/<document>_reviewed_<timestamp>.json`

---

### Step 6 — Browse the knowledge graph

**Development:**
```bash
python server.py data/processed/document_knowledge_graph.json --port 8080
```

**Production (gunicorn):**
```bash
KG_FILE=data/processed/document_knowledge_graph.json gunicorn -w 1 server:app
```

Then open:
- `http://localhost:8080/` — main dashboard
- `http://localhost:8080/visualization/network/index.html` — entity network
- `http://localhost:8080/visualization/timeline/index.html` — event timeline
- `http://localhost:8080/api/health` — health check

---

## Project structure

```
code_base/
├── config.py                  # Central config: model, paths, thresholds
├── logging_config.py          # Structured logging (plain text or JSON)
│
├── extract_document.py        # Step 1 — chunk a PDF/DOCX into JSON
├── extractor.py               # Standard document extractor
├── extractor_docling.py       # Docling-based extractor (better OCR)
│
├── llm_processor.py           # Step 2 — LLM entity + relationship extraction
├── relationship_processor.py  # Relationship extraction logic
├── entity_resolver.py         # Fuzzy entity deduplication and merging
├── extraction_utils.py        # Shared helpers (retry, schema validation)
│
├── critic.py                  # Quality evaluation logic
├── run_critic.py              # Step 3 — run critic from CLI
│
├── human_review.py            # Review UI server logic
├── main.py                    # Step 4 — start the review interface
├── consolidate_reviews.py     # Step 5 — apply review corrections
│
├── server.py                  # Step 6 — Flask visualisation server
│
├── tests/                     # Pytest test suite (run: pytest tests/ -v)
│   ├── test_entity_resolver.py
│   └── test_extraction_utils.py
│
├── schema/
│   ├── json-schema/           # JSON Schema definitions for each entity type
│   ├── neo4j/                 # Cypher scripts for Neo4j setup
│   └── documentation/         # ER diagrams and schema guides
│
├── visualization/
│   ├── network/               # D3.js network graph
│   └── timeline/              # D3.js event timeline
│
├── data/
│   ├── extracted/             # Output of Step 1
│   ├── processed/             # Output of Steps 2 and 5
│   ├── review/                # Review tasks and corrections (Step 4)
│   └── critic_results/        # Output of Step 3
│
├── .env.example               # Template for environment variables
└── requirements.txt
```

---

## Entity schema

| Entity | Required fields | Key optional fields |
|--------|----------------|---------------------|
| **Event** | `title`, `year`, `description` | `type`, `juridical_significance`, `harmony_significance`, `locations`, `actors` |
| **Actor** | `name`, `type` | `country`, `description`, `role` |
| **Concept** | `name`, `definition` | `key_proponents` |
| **Publication** | `title` | `type`, `year`, `actors` |
| **Location** | `name`, `type` | `country`, `description`, `significance` |

All entities also carry:
- `id` — UUID assigned during resolution
- `supporting_text` — the exact passage from the source document
- `source_chunk` — index of the originating chunk
- `variations` / `merge_confidence` — set when entities were deduplicated

---

## Running tests

```bash
pytest tests/ -v
```

49 tests covering entity resolution logic, retry/backoff behaviour, and schema validation. No API calls are made.

---

## Configuration reference

All tunable values live in `config.py`. The most likely things to change:

- **`DEFAULT_MODEL`** — Claude model for extraction (overridable via `KG_MODEL` env var)
- **`SIMILARITY_THRESHOLDS`** — per-entity-type merge thresholds (0–1); raise to merge more conservatively
- **`CONTEXT_SENTENCE` / `CONTEXT_PHRASE`** — domain framing injected into every LLM prompt
