"""
Entity Resolution Module for Knowledge Graph Extraction
Handles entity disambiguation, deduplication, and merging with advanced fuzzy matching
"""

import re
import uuid
import logging
import json
import time
from typing import Dict, List, Tuple, Set, Optional
from difflib import SequenceMatcher
from collections import defaultdict
from config import SIMILARITY_THRESHOLDS

logger = logging.getLogger(__name__)

class EntityResolver:
    """
    Advanced entity resolution and disambiguation system
    """
    
    def __init__(self, manual_mappings: Optional[Dict[str, Dict[str, str]]] = None):
        # Manual entity mappings provided by user
        self.manual_mappings = manual_mappings or {}
        
        # Common abbreviations and their expansions
        self.abbreviations = {
            "WHO": "World Health Organization",
            "UN": "United Nations",
            "UNEP": "United Nations Environment Programme",
            "CDC": "Centers for Disease Control and Prevention",
            "EPA": "Environmental Protection Agency",
            "NGO": "Non-Governmental Organization",
            "IPCC": "Intergovernmental Panel on Climate Change",
            "SDG": "Sustainable Development Goals",
            "SDGs": "Sustainable Development Goals",
            "US": "United States",
            "USA": "United States of America",
            "UK": "United Kingdom",
            "EU": "European Union",
            "IUCN": "International Union for Conservation of Nature",
            "WWF": "World Wildlife Fund",
            "WEF": "World Economic Forum",
            "IMF": "International Monetary Fund",
            "WTO": "World Trade Organization",
            "PhD": "Doctor of Philosophy",
            "Dr": "Doctor",
            "Prof": "Professor"
        }
        
        # Entity type specific settings (values defined in config.py)
        self.similarity_thresholds = SIMILARITY_THRESHOLDS
        
        # Context keywords for disambiguation
        self.context_keywords = {
            "actor": ["organization", "institution", "person", "individual", "group", "coalition"],
            "location": ["country", "city", "region", "state", "province", "continent"],
            "concept": ["theory", "framework", "approach", "model", "principle", "concept"],
            "event": ["conference", "summit", "meeting", "publication", "launch", "announcement"],
            "publication": ["journal", "book", "report", "article", "paper", "study"]
        }
    
    def resolve_entities(self, entities: Dict[str, List[Dict]]) -> Dict[str, List[Dict]]:
        """
        Advanced entity resolution with fuzzy matching and context awareness
        
        Args:
            entities: Dictionary of entity types to lists of entities
            
        Returns:
            Resolved and deduplicated entities
        """
        resolved_entities = {}
        self.disambiguation_report = []  # Initialize report for this resolution
        
        for entity_type, entity_list in entities.items():
            logger.info(f"Resolving {len(entity_list)} {entity_type} entities")
            
            # Skip if no entities
            if not entity_list:
                resolved_entities[entity_type] = []
                continue
            
            # Apply manual mappings first
            entity_list = self._apply_manual_mappings(entity_list, entity_type)
            
            # Create clusters of similar entities
            clusters = self._cluster_entities(entity_list, entity_type)
            
            # Merge entities within each cluster
            merged_entities = []
            for cluster in clusters:
                if len(cluster) == 1:
                    # Single entity cluster - just ensure it has an ID
                    entity = cluster[0]
                    if "id" not in entity:
                        entity["id"] = str(uuid.uuid4())
                    merged_entities.append(entity)
                else:
                    # Multiple entities - merge them
                    merged = self._merge_cluster(cluster, entity_type)
                    merged_entities.append(merged)
                    
                    # Add to disambiguation report
                    self._add_to_report(merged, cluster, entity_type)
            
            resolved_entities[entity_type] = merged_entities
            logger.info(f"Resolved to {len(merged_entities)} {entity_type} entities")
        
        return resolved_entities
    
    def _apply_manual_mappings(self, entities: List[Dict], entity_type: str) -> List[Dict]:
        """
        Apply manual entity mappings to normalize known variations
        
        Args:
            entities: List of entities
            entity_type: Type of entity
            
        Returns:
            Entities with manual mappings applied
        """
        if entity_type not in self.manual_mappings:
            return entities
        
        mappings = self.manual_mappings[entity_type]
        
        for entity in entities:
            # Get the entity name/title
            if entity_type == "event":
                name = entity.get("title", "")
            else:
                name = entity.get("name", "")
            
            # Check if we have a manual mapping for this entity
            if name in mappings:
                canonical_name = mappings[name]
                
                # Update the entity name
                if entity_type == "event":
                    entity["original_title"] = name
                    entity["title"] = canonical_name
                else:
                    entity["original_name"] = name
                    entity["name"] = canonical_name
                
                # Add flag for manual mapping
                entity["manual_mapping"] = True
                
                logger.info(f"Applied manual mapping: '{name}' -> '{canonical_name}'")
        
        return entities
    
    def _add_to_report(self, merged_entity: Dict, cluster: List[Dict], entity_type: str):
        """
        Add merge information to disambiguation report
        
        Args:
            merged_entity: The final merged entity
            cluster: Original cluster of entities that were merged
            entity_type: Type of entity
        """
        if len(cluster) <= 1:
            return
        
        # Get canonical name
        if entity_type == "event":
            canonical_name = merged_entity.get("title", "")
        else:
            canonical_name = merged_entity.get("name", "")
        
        # Collect all variations
        variations = []
        manual_mappings = []
        
        for entity in cluster:
            if entity_type == "event":
                name = entity.get("original_title", entity.get("title", ""))
            else:
                name = entity.get("original_name", entity.get("name", ""))
            
            if name and name != canonical_name:
                variations.append(name)
            
            # Check if this was manually mapped
            if entity.get("manual_mapping"):
                manual_mappings.append(name)
        
        # Calculate pairwise similarities for the report
        similarity_scores = []
        for i in range(len(cluster)):
            for j in range(i + 1, len(cluster)):
                sim = self._calculate_similarity(cluster[i], cluster[j], entity_type)
                similarity_scores.append(sim)
        
        avg_similarity = sum(similarity_scores) / len(similarity_scores) if similarity_scores else 1.0
        
        report_entry = {
            "type": entity_type,
            "canonical_name": canonical_name,
            "variations": variations,
            "manual_mappings": manual_mappings,
            "confidence": merged_entity.get("merge_confidence", 1.0),
            "average_similarity": round(avg_similarity, 3),
            "cluster_size": len(cluster),
            "source_chunks": merged_entity.get("source_chunks", []),
            "supporting_evidence": {
                "descriptions": [e.get("description", "")[:100] + "..." for e in cluster if e.get("description")],
                "years": list(set(e.get("year") for e in cluster if e.get("year")))
            }
        }
        
        self.disambiguation_report.append(report_entry)
    
    def export_disambiguation_report(self, output_path: str):
        """
        Export the disambiguation report to a JSON file
        
        Args:
            output_path: Path to save the report
        """
        # Sort report by entity type and confidence
        sorted_report = sorted(
            self.disambiguation_report,
            key=lambda x: (x["type"], -x["confidence"], -x["cluster_size"])
        )
        
        # Add summary statistics
        summary = {
            "total_merges": len(sorted_report),
            "merges_by_type": {},
            "manual_mapping_count": sum(1 for entry in sorted_report if entry["manual_mappings"]),
            "low_confidence_merges": sum(1 for entry in sorted_report if entry["confidence"] < 0.8),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Count merges by type
        for entry in sorted_report:
            entity_type = entry["type"]
            if entity_type not in summary["merges_by_type"]:
                summary["merges_by_type"][entity_type] = 0
            summary["merges_by_type"][entity_type] += 1
        
        report = {
            "summary": summary,
            "merges": sorted_report
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Disambiguation report saved to {output_path}")
        logger.info(f"Total merges: {summary['total_merges']}")
        logger.info(f"Manual mappings applied: {summary['manual_mapping_count']}")
        logger.info(f"Low confidence merges: {summary['low_confidence_merges']}")
    
    def _cluster_entities(self, entities: List[Dict], entity_type: str) -> List[List[Dict]]:
        """
        Cluster similar entities together
        
        Args:
            entities: List of entities
            entity_type: Type of entity
            
        Returns:
            List of entity clusters
        """
        clusters = []
        processed = set()
        
        for i, entity1 in enumerate(entities):
            if i in processed:
                continue
            
            # Start a new cluster with this entity
            cluster = [entity1]
            processed.add(i)
            
            # Find all similar entities
            for j, entity2 in enumerate(entities[i+1:], i+1):
                if j in processed:
                    continue
                
                # Calculate similarity
                similarity = self._calculate_similarity(entity1, entity2, entity_type)
                
                # Check if similar enough to merge
                threshold = self.similarity_thresholds.get(entity_type, 0.80)
                if similarity >= threshold:
                    cluster.append(entity2)
                    processed.add(j)
            
            clusters.append(cluster)
        
        return clusters
    
    def _calculate_similarity(self, entity1: Dict, entity2: Dict, entity_type: str) -> float:
        """
        Calculate similarity between two entities
        
        Args:
            entity1: First entity
            entity2: Second entity
            entity_type: Type of entity
            
        Returns:
            Similarity score (0-1)
        """
        scores = []
        weights = []
        
        # Get names/titles
        if entity_type == "event":
            name1 = entity1.get("title", "")
            name2 = entity2.get("title", "")
        else:
            name1 = entity1.get("name", "")
            name2 = entity2.get("name", "")
        
        # 1. Name similarity
        name_sim = self._string_similarity(name1, name2)
        scores.append(name_sim)
        weights.append(0.4)  # High weight for name
        
        # 2. Check for abbreviations
        if self._is_abbreviation(name1, name2):
            scores.append(1.0)
            weights.append(0.3)
        else:
            scores.append(0.0)
            weights.append(0.1)  # Lower weight if not abbreviation
        
        # 3. Type-specific similarity
        if entity_type == "event":
            # For events, year is crucial
            year1 = entity1.get("year")
            year2 = entity2.get("year")
            if year1 and year2:
                year_sim = 1.0 if year1 == year2 else 0.0
                scores.append(year_sim)
                weights.append(0.3)
            
            # Event type similarity
            type1 = entity1.get("type", "")
            type2 = entity2.get("type", "")
            if type1 and type2:
                type_sim = 1.0 if type1 == type2 else 0.5 if type1.lower() in type2.lower() or type2.lower() in type1.lower() else 0.0
                scores.append(type_sim)
                weights.append(0.1)
        
        elif entity_type == "actor":
            # For actors, check type and country
            type1 = entity1.get("type", "")
            type2 = entity2.get("type", "")
            if type1 and type2:
                type_sim = 1.0 if type1 == type2 else 0.5 if self._compatible_actor_types(type1, type2) else 0.0
                scores.append(type_sim)
                weights.append(0.2)
            
            # Country similarity
            country1 = entity1.get("country", "")
            country2 = entity2.get("country", "")
            if country1 and country2:
                country_sim = 1.0 if country1 == country2 else 0.5 if self._same_country(country1, country2) else 0.0
                scores.append(country_sim)
                weights.append(0.1)
        
        elif entity_type == "publication":
            # For publications, check year and authors
            year1 = entity1.get("year")
            year2 = entity2.get("year")
            if year1 and year2:
                year_sim = 1.0 if abs(year1 - year2) <= 1 else 0.0  # Allow 1 year difference
                scores.append(year_sim)
                weights.append(0.2)
            
            # Author overlap
            authors1 = set(entity1.get("authors", []))
            authors2 = set(entity2.get("authors", []))
            if authors1 and authors2:
                overlap = len(authors1.intersection(authors2))
                total = len(authors1.union(authors2))
                author_sim = overlap / total if total > 0 else 0.0
                scores.append(author_sim)
                weights.append(0.2)
        
        # 4. Context similarity from supporting text
        support1 = entity1.get("supporting_text", "")
        support2 = entity2.get("supporting_text", "")
        if support1 and support2:
            context_sim = self._context_similarity(support1, support2, entity_type)
            scores.append(context_sim)
            weights.append(0.1)
        
        # Calculate weighted average
        if not scores:
            return 0.0
        
        total_weight = sum(weights[:len(scores)])
        if total_weight == 0:
            return 0.0
        
        weighted_sum = sum(s * w for s, w in zip(scores, weights))
        return weighted_sum / total_weight
    
    def _string_similarity(self, str1: str, str2: str) -> float:
        """
        Calculate string similarity using SequenceMatcher
        
        Args:
            str1: First string
            str2: Second string
            
        Returns:
            Similarity score (0-1)
        """
        if not str1 or not str2:
            return 0.0
        
        # Normalize strings
        str1 = str1.lower().strip()
        str2 = str2.lower().strip()
        
        # Exact match
        if str1 == str2:
            return 1.0
        
        # Use SequenceMatcher for fuzzy matching
        return SequenceMatcher(None, str1, str2).ratio()
    
    def _is_abbreviation(self, str1: str, str2: str) -> bool:
        """
        Check if one string is an abbreviation of the other
        
        Args:
            str1: First string
            str2: Second string
            
        Returns:
            True if one is abbreviation of the other
        """
        str1 = str1.strip()
        str2 = str2.strip()
        
        # Check known abbreviations
        if str1 in self.abbreviations and self.abbreviations[str1].lower() == str2.lower():
            return True
        if str2 in self.abbreviations and self.abbreviations[str2].lower() == str1.lower():
            return True
        
        # Check if one is acronym of the other
        if self._is_acronym(str1, str2) or self._is_acronym(str2, str1):
            return True
        
        return False
    
    def _is_acronym(self, short: str, long: str) -> bool:
        """
        Check if short string is an acronym of long string
        
        Args:
            short: Potential acronym
            long: Potential full form
            
        Returns:
            True if short is acronym of long
        """
        # Remove common words
        stop_words = {"of", "the", "and", "for", "in", "on", "at", "to", "a", "an"}
        
        # Get words from long string
        words = [w for w in long.split() if w.lower() not in stop_words]
        
        # Get first letters
        first_letters = "".join(w[0].upper() for w in words if w)
        
        return short.upper() == first_letters
    
    def _compatible_actor_types(self, type1: str, type2: str) -> bool:
        """
        Check if two actor types are compatible for merging
        """
        # Define compatible type groups
        compatible_groups = [
            {"Individual", "Person"},
            {"Institution", "Organization", "NGO", "Government"},
            {"Coalition", "Network", "Alliance"}
        ]
        
        for group in compatible_groups:
            if type1 in group and type2 in group:
                return True
        
        return False
    
    def _same_country(self, country1: str, country2: str) -> bool:
        """
        Check if two country representations refer to the same country
        """
        # Common country variations
        country_variations = {
            "US": ["USA", "United States", "United States of America", "U.S.", "U.S.A."],
            "UK": ["United Kingdom", "Britain", "Great Britain", "U.K."],
            "EU": ["European Union", "E.U."],
            "UAE": ["United Arab Emirates", "U.A.E."],
            "DRC": ["Democratic Republic of Congo", "Congo-Kinshasa"],
            "ROC": ["Republic of Congo", "Congo-Brazzaville"]
        }
        
        # Check variations
        for variations in country_variations.values():
            if country1 in variations and country2 in variations:
                return True
        
        return False
    
    def _context_similarity(self, text1: str, text2: str, entity_type: str) -> float:
        """
        Calculate context similarity based on supporting text
        """
        # Extract relevant keywords based on entity type
        keywords = self.context_keywords.get(entity_type, [])
        
        # Count keyword occurrences
        text1_lower = text1.lower()
        text2_lower = text2.lower()
        
        keywords1 = sum(1 for kw in keywords if kw in text1_lower)
        keywords2 = sum(1 for kw in keywords if kw in text2_lower)
        
        # Check for shared rare words (likely specific to entity)
        words1 = set(w for w in text1_lower.split() if len(w) > 5)
        words2 = set(w for w in text2_lower.split() if len(w) > 5)
        
        if words1 and words2:
            overlap = len(words1.intersection(words2))
            total = len(words1.union(words2))
            word_sim = overlap / total if total > 0 else 0.0
            
            # Combine keyword and word similarity
            keyword_sim = min(keywords1, keywords2) / max(keywords1, keywords2) if max(keywords1, keywords2) > 0 else 0.0
            return 0.7 * word_sim + 0.3 * keyword_sim
        
        return 0.0
    
    def _merge_cluster(self, cluster: List[Dict], entity_type: str) -> Dict:
        """
        Merge a cluster of similar entities into one
        
        Args:
            cluster: List of similar entities
            entity_type: Type of entity
            
        Returns:
            Merged entity
        """
        # Select the best representative
        representative = self._select_representative(cluster, entity_type)
        
        # Start with the representative
        merged = representative.copy()
        
        # Ensure ID
        if "id" not in merged:
            merged["id"] = str(uuid.uuid4())
        
        # Track all variations and sources
        merged["variations"] = []
        merged["source_chunks"] = set()
        merged["confidence"] = 1.0
        
        # Merge information from all entities
        for entity in cluster:
            # Track variations
            if entity_type == "event":
                name = entity.get("title", "")
            else:
                name = entity.get("name", "")
            
            if name and name not in merged["variations"]:
                merged["variations"].append(name)
            
            # Track source chunks
            if "source_chunk" in entity:
                merged["source_chunks"].add(entity["source_chunk"])
            
            # Merge scalar fields
            for key, value in entity.items():
                if key in ["id", "source_chunk", "variations", "source_chunks"]:
                    continue
                
                if key not in merged or not merged[key]:
                    merged[key] = value
                elif key == "description" and value and merged[key] != value:
                    # Merge descriptions intelligently
                    merged[key] = self._merge_descriptions(merged[key], value)
                elif key == "significance" and value:
                    # Average significance scores
                    if isinstance(merged[key], (int, float)) and isinstance(value, (int, float)):
                        merged[key] = (merged[key] + value) / 2
                elif key == "supporting_text" and value:
                    # Collect all supporting text
                    if "all_supporting_text" not in merged:
                        merged["all_supporting_text"] = [merged.get("supporting_text", "")]
                    if value not in merged["all_supporting_text"]:
                        merged["all_supporting_text"].append(value)
                
                # Merge list fields
                elif isinstance(value, list) and isinstance(merged.get(key, []), list):
                    merged[key] = self._merge_lists(merged[key], value)
        
        # Convert source_chunks set to list
        merged["source_chunks"] = list(merged["source_chunks"])
        
        # Calculate merge confidence
        merged["merge_confidence"] = self._calculate_merge_confidence(cluster, entity_type)
        
        return merged
    
    def _select_representative(self, cluster: List[Dict], entity_type: str) -> Dict:
        """
        Select the best representative entity from a cluster
        
        Args:
            cluster: List of similar entities
            entity_type: Type of entity
            
        Returns:
            Best representative entity
        """
        scores = []
        
        for entity in cluster:
            score = 0
            
            # Get name/title
            if entity_type == "event":
                name = entity.get("title", "")
            else:
                name = entity.get("name", "")
            
            # Prefer longer, more complete names
            score += len(name) * 0.1
            
            # Prefer entities with more complete information
            fields_filled = sum(1 for v in entity.values() if v)
            score += fields_filled * 1.0
            
            # Prefer entities with supporting text
            if entity.get("supporting_text"):
                score += 5.0
            
            # Prefer non-abbreviated names
            if name and name.upper() != name:  # Not all caps
                score += 3.0
            
            # For publications, prefer entries with DOI/ISBN
            if entity_type == "publication" and entity.get("identifier"):
                score += 10.0
            
            scores.append((score, entity))
        
        # Return entity with highest score
        scores.sort(key=lambda x: x[0], reverse=True)
        return scores[0][1]
    
    def _merge_descriptions(self, desc1: str, desc2: str) -> str:
        """
        Intelligently merge two descriptions
        """
        if not desc1:
            return desc2
        if not desc2:
            return desc1
        
        # If one is substring of other, return the longer one
        if desc1 in desc2:
            return desc2
        if desc2 in desc1:
            return desc1
        
        # Otherwise, combine with proper formatting
        # Remove duplicate sentences
        sentences1 = set(s.strip() for s in desc1.split('.') if s.strip())
        sentences2 = set(s.strip() for s in desc2.split('.') if s.strip())
        
        all_sentences = sentences1.union(sentences2)
        
        # Sort sentences for consistent order
        sorted_sentences = sorted(all_sentences)
        
        return '. '.join(sorted_sentences) + '.'
    
    def _merge_lists(self, list1: List, list2: List) -> List:
        """
        Merge two lists, removing duplicates while preserving order
        """
        seen = set()
        result = []
        
        for item in list1 + list2:
            # Normalize strings for comparison
            key = item.lower() if isinstance(item, str) else item
            
            if key not in seen:
                seen.add(key)
                result.append(item)
        
        return result
    
    def _calculate_merge_confidence(self, cluster: List[Dict], entity_type: str) -> float:
        """
        Calculate confidence score for the merge
        
        Args:
            cluster: List of merged entities
            entity_type: Type of entity
            
        Returns:
            Confidence score (0-1)
        """
        if len(cluster) == 1:
            return 1.0
        
        # Calculate average pairwise similarity
        total_similarity = 0
        comparisons = 0
        
        for i in range(len(cluster)):
            for j in range(i + 1, len(cluster)):
                similarity = self._calculate_similarity(cluster[i], cluster[j], entity_type)
                total_similarity += similarity
                comparisons += 1
        
        if comparisons == 0:
            return 0.5
        
        return total_similarity / comparisons


# Convenience functions for backward compatibility
def resolve_entities(entities: Dict[str, List[Dict]], manual_mappings: Optional[Dict[str, Dict[str, str]]] = None) -> Dict[str, List[Dict]]:
    """
    Resolve and deduplicate entities using advanced resolution
    
    Args:
        entities: Dictionary of entity types to lists of entities
        manual_mappings: Optional manual entity mappings
        
    Returns:
        Resolved and deduplicated entities
    """
    resolver = EntityResolver(manual_mappings=manual_mappings)
    return resolver.resolve_entities(entities)


def merge_entities(entity1: Dict, entity2: Dict) -> Dict:
    """
    Merge two entities with enhanced logic
    """
    resolver = EntityResolver()
    cluster = [entity1, entity2]
    
    # Determine entity type
    entity_type = "unknown"
    if "title" in entity1 and "year" in entity1:
        entity_type = "event"
    elif "name" in entity1:
        # Try to determine type from other fields
        if "authors" in entity1:
            entity_type = "publication"
        elif "country" in entity1 and "role" in entity1:
            entity_type = "actor"
        elif "definition" in entity1:
            entity_type = "concept"
        elif "country" in entity1 and "significance" in entity1:
            entity_type = "location"
    
    return resolver._merge_cluster(cluster, entity_type)


def create_disambiguation_report(entities: Dict[str, List[Dict]], output_path: str, 
                               manual_mappings: Optional[Dict[str, Dict[str, str]]] = None) -> Dict[str, List[Dict]]:
    """
    Resolve entities and create a disambiguation report
    
    Args:
        entities: Dictionary of entity types to lists of entities
        output_path: Path to save the disambiguation report
        manual_mappings: Optional manual entity mappings
        
    Returns:
        Resolved entities
    """
    resolver = EntityResolver(manual_mappings=manual_mappings)
    resolved_entities = resolver.resolve_entities(entities)
    resolver.export_disambiguation_report(output_path)
    
    return resolved_entities


# Example manual mappings for common variations
EXAMPLE_MANUAL_MAPPINGS = {
    "event": {
        "Rio Summit": "United Nations Conference on Environment and Development",
        "Earth Summit": "United Nations Conference on Environment and Development",
        "Rio Conference": "United Nations Conference on Environment and Development",
        "Rio+20": "United Nations Conference on Sustainable Development",
        "Stockholm Conference": "United Nations Conference on the Human Environment",
        "Paris Agreement": "Paris Agreement on Climate Change",
        "Paris Climate Agreement": "Paris Agreement on Climate Change"
    },
    "actor": {
        "WHO": "World Health Organization",
        "UN": "United Nations",
        "UNEP": "United Nations Environment Programme",
        "IPCC": "Intergovernmental Panel on Climate Change",
        "CDC": "Centers for Disease Control and Prevention",
        "WWF": "World Wildlife Fund",
        "World Wildlife Fund": "World Wide Fund for Nature"
    },
    "concept": {
        "SDG": "Sustainable Development Goals",
        "SDGs": "Sustainable Development Goals",
        "One Health": "One Health Approach",
        "Planetary Health": "Planetary Health Framework",
        "ESG": "Environmental, Social, and Governance"
    },
    "location": {
        "US": "United States",
        "USA": "United States",
        "UK": "United Kingdom",
        "DRC": "Democratic Republic of the Congo",
        "UAE": "United Arab Emirates"
    }
}


def create_manual_mappings_template(output_path: str = "manual_mappings_template.json"):
    """
    Create a template file for manual entity mappings
    
    Args:
        output_path: Path to save the template
    """
    template = {
        "event": {
            "# Example mappings for events": "# Delete this line",
            "Rio Summit": "United Nations Conference on Environment and Development",
            "Earth Summit": "United Nations Conference on Environment and Development"
        },
        "actor": {
            "# Example mappings for actors": "# Delete this line",
            "WHO": "World Health Organization",
            "UN": "United Nations"
        },
        "concept": {
            "# Example mappings for concepts": "# Delete this line",
            "SDGs": "Sustainable Development Goals"
        },
        "publication": {
            "# Example mappings for publications": "# Delete this line"
        },
        "location": {
            "# Example mappings for locations": "# Delete this line",
            "US": "United States",
            "UK": "United Kingdom"
        }
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(template, f, indent=2, ensure_ascii=False)
    
    print(f"Manual mappings template created at: {output_path}")
    print("Edit this file to add your custom entity mappings, then use with --manual-mappings flag")