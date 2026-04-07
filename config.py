"""
Central configuration for the Planetary Health Knowledge Graph pipeline.
All hardcoded values (model names, file paths, thresholds) live here.
Override any value via environment variable where noted.
"""

import os

# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

DEFAULT_MODEL = os.environ.get("KG_MODEL", "claude-sonnet-4-20250514")
MAX_TOKENS = int(os.environ.get("KG_MAX_TOKENS", "8000"))

# ---------------------------------------------------------------------------
# Domain context (used in all extraction prompts)
# ---------------------------------------------------------------------------

CONTEXT_SENTENCE = (
    "Analyze the following text from a book about mobilizations towards living "
    "in harmony with nature, specifically through economic activities beyond GDP."
)
CONTEXT_PHRASE = "beyond GDP and living in harmony with nature"

# ---------------------------------------------------------------------------
# Default file paths
# ---------------------------------------------------------------------------

# Used by server.py as the fallback knowledge-graph file
DEFAULT_KG_FILE = os.environ.get(
    "KG_FILE",
    "data/processed/politics_of_ron_core_chunks_clean_knowledge_graph.json",
)

# Used by human_review.py when loading entity data for review tasks
DEFAULT_KG_FILE_REVIEW = os.environ.get(
    "KG_FILE_REVIEW",
    "data/processed/book_9780262366601-compressed_knowledge_graph.json",
)

# Directory that contains the JSON schema files
SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "schema", "json-schema")

# ---------------------------------------------------------------------------
# Entity resolution thresholds
# ---------------------------------------------------------------------------

SIMILARITY_THRESHOLDS = {
    "event": 0.85,       # Higher threshold for events (title + year matching)
    "actor": 0.80,       # Medium threshold for actors
    "concept": 0.90,     # High threshold — avoid merging similar but distinct concepts
    "publication": 0.85, # High threshold for publications
    "location": 0.75,    # Lower threshold — handle name variations
}
