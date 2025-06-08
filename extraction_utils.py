import os
import json
import logging
from typing import Dict, List, Optional, Any
import pandas as pd

logger = logging.getLogger(__name__)

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
