"""
Central configuration for the Planetary Health Knowledge Graph pipeline.
All hardcoded values (model names, file paths, thresholds) live here.
Override any value via environment variable where noted.
"""

import os

# ---------------------------------------------------------------------------
# LLM backend defaults
# ---------------------------------------------------------------------------

ANTHROPIC_DEFAULT_MODEL = "claude-sonnet-4-20250514"

EXTERNAL_API_URL = "https://chat-ai.academiccloud.de/v1"
EXTERNAL_API_MODELS = [
    "openai-gpt-oss-120b",
    "qwen3-235b-a22b",
    "glm-4.7",
]
EXTERNAL_DEFAULT_MODEL = "openai-gpt-oss-120b"

# DEFAULT_MODEL is kept as a module-level fallback (used if no client is
# available, e.g. in tests).  The active model is resolved per-client by
# create_llm_client() and stored on UnifiedLLMClient.model.
DEFAULT_MODEL: str = os.environ.get("KG_MODEL", ANTHROPIC_DEFAULT_MODEL)

MAX_TOKENS = int(os.environ.get("KG_MAX_TOKENS", "8000"))

# ---------------------------------------------------------------------------
# Domain context (used in all extraction prompts)
# ---------------------------------------------------------------------------

# Available research contexts. Select one via ACTIVE_CONTEXT or the
# KG_CONTEXT environment variable.
CONTEXT_OPTIONS = {
    "generic": {
        "sentence": "Analyze the following text about collective efforts to live in harmony with nature.",
        "phrase": "collective efforts to live in harmony with nature.",
    },
    "environmental_movement": {
        "sentence": (
            "Analyze the following text about collective efforts to live in harmony with nature, "
            "specifically through social movements and governance activities to account for "
            "nature's wellbeing and its interdependence with human lives."
        ),
        "phrase": (
            "social movements and governance activities to account for nature's wellbeing "
            "and its interdependence with human lives."
        ),
    },
    "beyond_gdp": {
        "sentence": (
            "Analyze the following text about collective efforts to live in harmony with nature, "
            "specifically through the incorporation of the value of nature and its importance "
            "to the wellbeing of all lives in economic decision-making, such as replacing "
            "Gross Domestic Products (GDP) as metrics."
        ),
        "phrase": (
            "the incorporation of the value of nature and its importance to the wellbeing of "
            "all lives in economic decision-making, such as replacing Gross Domestic Products "
            "(GDP) as metrics."
        ),
    },
    "protected_areas": {
        "sentence": (
            "Analyze the following text about collective efforts to live in harmony with nature, "
            "specifically through allocating and designing space in the biosphere for nature "
            "to thrive, such as protected areas."
        ),
        "phrase": "allocating and designing space in the biosphere for nature to thrive, such as protected areas.",
    },
    "ecovillages": {
        "sentence": (
            "Analyze the following text about collective efforts to live in harmony with nature, "
            "specifically through building intentional communities for ecological regeneration "
            "and environmental sustainability."
        ),
        "phrase": "building intentional communities for ecological regeneration and environmental sustainability.",
    },
    "community_based_forestry": {
        "sentence": (
            "Analyze the following text about collective efforts to live in harmony with nature, "
            "specifically through reorienting production and consumption activities to consider "
            "nature's capacity for regeneration, such as through community-based forestry."
        ),
        "phrase": (
            "reorienting production and consumption activities to consider nature's capacity "
            "for regeneration, such as through community-based forestry."
        ),
    },
}

# Set via KG_CONTEXT env variable or change this default directly.
ACTIVE_CONTEXT: str = os.environ.get("KG_CONTEXT", "beyond_gdp")

# These module-level names are imported by llm_processor.py and other modules.
CONTEXT_SENTENCE: str = CONTEXT_OPTIONS[ACTIVE_CONTEXT]["sentence"]
CONTEXT_PHRASE: str = CONTEXT_OPTIONS[ACTIVE_CONTEXT]["phrase"]

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
    "data/processed_v2/book_9780262366601-compressed_core_knowledge_graph.json",
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
    "expression": 0.85, # High threshold for expressions
    "location": 0.75,    # Lower threshold — handle name variations
}
