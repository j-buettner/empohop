import os
import json
import logging
import random
import time
from typing import Any, Callable, Dict, List, Optional
import pandas as pd
from config import SCHEMA_DIR

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema validation helpers
# ---------------------------------------------------------------------------

# Map pipeline entity-type keys to their JSON schema files.
# "expression" is extracted under the key "publications" by the LLM prompts.
_SCHEMA_FILE_MAP = {
    "event": "event.json",
    "actor": "actor.json",
    "concept": "concept.json",
    "publication": "publication.json",
    "location": "location.json",
    "relationship": "relationship.json",
}

_schema_cache: Dict[str, Dict] = {}


def _load_schema(entity_type: str) -> Optional[Dict]:
    """Load and cache a JSON schema for the given entity type."""
    if entity_type in _schema_cache:
        return _schema_cache[entity_type]
    filename = _SCHEMA_FILE_MAP.get(entity_type)
    if not filename:
        return None
    path = os.path.join(SCHEMA_DIR, filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            schema = json.load(f)
        _schema_cache[entity_type] = schema
        return schema
    except Exception as e:
        logger.warning(f"Could not load schema for '{entity_type}' from {path}: {e}")
        return None


def validate_extracted_entities(
    entity_type: str,
    entities: List[Dict],
) -> List[Dict]:
    """
    Soft-validate a list of extracted entities against the JSON schema's
    *required* fields only.  Invalid entities are logged as warnings and
    returned unchanged so they stay in the pipeline for human review.

    Args:
        entity_type: One of "event", "actor", "concept", "publication", "location".
        entities: The list of entity dicts returned by the LLM.

    Returns:
        The original list (unmodified — validation is advisory only).
    """
    schema = _load_schema(entity_type)
    if schema is None:
        return entities  # No schema available — skip silently

    required_fields = schema.get("required", [])
    if not required_fields:
        return entities

    # "id" is always assigned by the pipeline after extraction; skip it here.
    check_fields = [f for f in required_fields if f != "id"]

    invalid_count = 0
    for i, entity in enumerate(entities):
        missing = [f for f in check_fields if f not in entity or entity[f] is None]
        if missing:
            name = entity.get("title") or entity.get("name") or f"index {i}"
            logger.warning(
                f"[schema] {entity_type} '{name}' is missing required fields: {missing}"
            )
            invalid_count += 1

    if invalid_count:
        logger.warning(
            f"[schema] {invalid_count}/{len(entities)} extracted {entity_type}(s) "
            f"are missing required fields — check warnings above."
        )

    return entities


# ---------------------------------------------------------------------------
# API retry helper
# ---------------------------------------------------------------------------

# Error patterns that indicate a transient (retryable) failure.
_RETRYABLE_PATTERNS = (
    "429", "529",                    # Rate limit / overloaded
    "500", "502", "503", "504",      # Server errors
    "rate_limit", "overloaded",      # Anthropic-specific strings
    "connection", "timeout",         # Network transients
)


def retry_api_call(
    func: Callable,
    *args: Any,
    max_retries: int = 3,
    base_delay: float = 2.0,
    **kwargs: Any,
) -> Any:
    """
    Call ``func(*args, **kwargs)`` with exponential backoff on transient errors.

    Retries on rate-limit (429/529) and server errors (5xx/connection).
    Raises immediately for any other exception type (permanent errors).

    Args:
        func: Callable to invoke.
        *args: Positional arguments forwarded to *func*.
        max_retries: Maximum number of retry attempts after the first call.
        base_delay: Initial delay in seconds; doubles each attempt (plus jitter).
        **kwargs: Keyword arguments forwarded to *func*.

    Returns:
        Whatever *func* returns on success.

    Raises:
        The last exception raised by *func* after all retries are exhausted.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt == max_retries:
                break

            error_str = str(exc).lower()
            type_name = type(exc).__name__.lower()
            is_retryable = any(
                p in error_str or p in type_name for p in _RETRYABLE_PATTERNS
            )

            if not is_retryable:
                raise  # Permanent error — propagate immediately

            delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
            logger.warning(
                "[retry] API call failed (attempt %d/%d), retrying in %.1fs: %s: %s",
                attempt + 1,
                max_retries + 1,
                delay,
                type(exc).__name__,
                exc,
            )
            time.sleep(delay)

    raise last_exc  # type: ignore[misc]


def analyze_chunks(chunks: List[Dict]) -> Dict[str, Any]:
    """
    Analyze chunks to provide statistics and insights
    
    Args:
        chunks: List of chunk dictionaries
        
    Returns:
        Dictionary with analysis results
    """
    # Calculate basic statistics
    chunk_lengths = [len(chunk["text"]) for chunk in chunks]
    
    analysis = {
        "total_chunks": len(chunks),
        "total_characters": sum(chunk_lengths),
        "avg_chunk_length": sum(chunk_lengths) / len(chunks) if chunks else 0,
        "min_chunk_length": min(chunk_lengths) if chunks else 0,
        "max_chunk_length": max(chunk_lengths) if chunks else 0,
        "section_distribution": {}
    }
    
    # Analyze section distribution
    for chunk in chunks:
        section = chunk["metadata"].get("section_title", "Unknown")
        if section in analysis["section_distribution"]:
            analysis["section_distribution"][section] += 1
        else:
            analysis["section_distribution"][section] = 1
    
    return analysis

def create_chunk_dataframe(chunks: List[Dict]) -> pd.DataFrame:
    """
    Convert chunks to a pandas DataFrame for easier analysis
    
    Args:
        chunks: List of chunk dictionaries
        
    Returns:
        DataFrame with chunk data
    """
    # Extract relevant fields for the DataFrame
    data = []
    for i, chunk in enumerate(chunks):
        row = {
            "chunk_id": i,
            "text_length": len(chunk["text"]),
            "section": chunk["metadata"].get("section_title", "Unknown"),
            "page": chunk["metadata"].get("page", None),
            "text_preview": chunk["text"][:100] + "..." if len(chunk["text"]) > 100 else chunk["text"]
        }
        data.append(row)
    
    return pd.DataFrame(data)

def visualize_chunk_distribution(chunks: List[Dict], output_path: Optional[str] = None):
    """
    Create a visualization of chunk distribution
    
    Args:
        chunks: List of chunk dictionaries
        output_path: Path to save the visualization (optional)
        
    Returns:
        Path to the saved visualization or None
    """
    try:
        import matplotlib.pyplot as plt
        import seaborn as sns
        
        # Create DataFrame
        df = create_chunk_dataframe(chunks)
        
        # Set up the figure
        plt.figure(figsize=(12, 8))
        
        # Plot chunk length distribution
        plt.subplot(2, 1, 1)
        sns.histplot(df["text_length"], bins=20, kde=True)
        plt.title("Chunk Length Distribution")
        plt.xlabel("Text Length (characters)")
        plt.ylabel("Count")
        
        # Plot section distribution
        plt.subplot(2, 1, 2)
        section_counts = df["section"].value_counts()
        section_counts.plot(kind="bar")
        plt.title("Section Distribution")
        plt.xlabel("Section")
        plt.ylabel("Number of Chunks")
        plt.xticks(rotation=45, ha="right")
        
        plt.tight_layout()
        
        # Save or show the figure
        if output_path:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            plt.savefig(output_path)
            logger.info(f"Visualization saved to: {output_path}")
            return output_path
        else:
            plt.show()
            return None
            
    except ImportError:
        logger.warning("Matplotlib and/or seaborn not available. Skipping visualization.")
        return None

def find_potential_entities(chunks: List[Dict], entity_types: List[str]) -> Dict[str, List[str]]:
    """
    Simple heuristic-based entity extraction to identify potential entities
    
    Args:
        chunks: List of chunk dictionaries
        entity_types: List of entity types to look for (e.g., ["event", "actor", "concept"])
        
    Returns:
        Dictionary with potential entities by type
    """
    import re
    from collections import Counter
    
    # Simple patterns for different entity types
    patterns = {
        "event": r'(?:in|at|during|the)\s+([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*){1,5}(?:\s+of\s+\d{4})?)',
        "actor": r'(?:[A-Z][a-zA-Z]*\s+){1,2}(?:University|Organization|Association|Foundation|Institute|Agency)',
        "person": r'(?:[A-Z][a-zA-Z]*\s+){1,2}(?:[A-Z][a-zA-Z]*)',
        "concept": r'(?:concept of|framework of|theory of|approach to)\s+([a-zA-Z]*(?:\s+[a-zA-Z]*){1,3})',
        "publication": r'(?:titled|entitled|publication|book|article|report)\s+"([^"]*)"',
        "location": r'(?:in|at|from)\s+([A-Z][a-zA-Z]*(?:,\s+[A-Z][a-zA-Z]*)?)'
    }
    
    # Filter to requested entity types
    patterns = {k: v for k, v in patterns.items() if k in entity_types}
    
    # Extract potential entities
    potential_entities = {entity_type: [] for entity_type in patterns.keys()}
    
    for chunk in chunks:
        text = chunk["text"]
        
        for entity_type, pattern in patterns.items():
            matches = re.findall(pattern, text)
            potential_entities[entity_type].extend(matches)
    
    # Count occurrences and keep the most frequent
    for entity_type in potential_entities:
        counter = Counter(potential_entities[entity_type])
        # Keep entities that appear at least twice
        frequent_entities = [entity for entity, count in counter.items() if count >= 2]
        potential_entities[entity_type] = frequent_entities
    
    return potential_entities

def extract_key_phrases(chunks: List[Dict], num_phrases: int = 20) -> List[str]:
    """
    Extract key phrases from chunks using simple TF-IDF
    
    Args:
        chunks: List of chunk dictionaries
        num_phrases: Number of key phrases to extract
        
    Returns:
        List of key phrases
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        import numpy as np
        
        # Extract text from chunks
        texts = [chunk["text"] for chunk in chunks]
        
        # Create TF-IDF vectorizer
        vectorizer = TfidfVectorizer(
            max_df=0.7,
            min_df=2,
            max_features=1000,
            ngram_range=(1, 3),
            stop_words='english'
        )
        
        # Fit and transform texts
        tfidf_matrix = vectorizer.fit_transform(texts)
        
        # Get feature names
        feature_names = vectorizer.get_feature_names_out()
        
        # Calculate average TF-IDF score for each feature
        avg_scores = np.mean(tfidf_matrix.toarray(), axis=0)
        
        # Get top features
        top_indices = avg_scores.argsort()[-num_phrases:][::-1]
        top_phrases = [feature_names[i] for i in top_indices]
        
        return top_phrases
        
    except ImportError:
        logger.warning("scikit-learn not available. Skipping key phrase extraction.")
        return []
