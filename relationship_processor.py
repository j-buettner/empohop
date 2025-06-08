import json
import logging
import re
import uuid
from typing import Dict, List, Optional, Any
import time

# Configure logging
logger = logging.getLogger(__name__)

# Relationship extraction prompt
RELATIONSHIP_EXTRACTION_PROMPT = """
Analyze the following text and identify relationships between entities in the planetary health domain.
Focus on these relationship types:
- Event influences Event
- Actor participates in Event
- Event introduces Concept
- Publication cites Publication
- Actor develops Concept
- Actor collaborates with Actor
- Concept relates to Concept
- Event takes place at Location

Text to analyze:
{text}

Respond in the following JSON format:
{{
  "relationships": [
    {{
      "source": "Source entity name",
      "source_type": "Event|Actor|Concept|Publication|Location",
      "target": "Target entity name",
      "target_type": "Event|Actor|Concept|Publication|Location",
      "relationship_type": "Influences|Participates|Develops|etc.",
      "description": "Description of the relationship",
      "strength": 1-5
    }}
  ]
}}
"""

class RelationshipProcessor:
    """
    Handles extraction, resolution, and processing of relationships between entities
    """
    
    def __init__(self, llm_client, critic_llm_client=None):
        """
        Initialize the relationship processor
        
        Args:
            llm_client: Client for the primary LLM
            critic_llm_client: Client for the critic LLM (optional)
        """
        self.llm_client = llm_client
        self.critic_llm_client = critic_llm_client or llm_client
        logger.info("Initialized RelationshipProcessor")
    
    def extract_relationships_from_chunk(self, chunk: Dict) -> List[Dict]:
        """
        Extract relationships from a single document chunk
        
        Args:
            chunk: Document chunk with text and metadata
            
        Returns:
            List of extracted relationships
        """
        try:
            # Format prompt with chunk text
            prompt = RELATIONSHIP_EXTRACTION_PROMPT.format(text=chunk["text"])
            
            # Call LLM API
            response = self.llm_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=8000,
                system="You are an expert in extracting relationships between entities in planetary health texts.",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )

            # Get the raw response content
            content = response.content[0].text.strip()
            
            # Parse response
            try:
                # Try to extract JSON from the response if it's wrapped in markdown code blocks
                if "```json" in content:
                    json_start = content.find("```json") + 7
                    json_end = content.find("```", json_start)
                    if json_end != -1:
                        json_content = content[json_start:json_end].strip()
                        content = json_content
                elif "```" in content:
                    json_start = content.find("```") + 3
                    json_end = content.find("```", json_start)
                    if json_end != -1:
                        json_content = content[json_start:json_end].strip()
                        content = json_content
                
                # Try to find JSON object in the content
                json_start = content.find("{")
                json_end = content.rfind("}")
                if json_start != -1 and json_end != -1 and json_end > json_start:
                    json_content = content[json_start:json_end+1].strip()
                    content = json_content
                
                # Parse the JSON
                result = json.loads(content)
                relationships = result.get("relationships", [])
                
                # Add chunk info to relationships for tracking
                for rel in relationships:
                    if isinstance(rel, dict):
                        rel["source_chunk"] = chunk.get("chunk_id", "unknown")
                
                return relationships
                
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse relationship extraction response as JSON: {str(e)}")
                return []
                
        except Exception as e:
            logger.error(f"Error extracting relationships from chunk: {str(e)}")
            return []
    
    def extract_relationships_from_chunks(self, chunks: List[Dict]) -> List[Dict]:
        """
        Extract relationships from multiple document chunks
        
        Args:
            chunks: List of document chunks
            
        Returns:
            List of all extracted relationships
        """
        all_relationships = []
        
        logger.info(f"Extracting relationships from {len(chunks)} chunks")
        
        for i, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {i+1}/{len(chunks)} for relationships")
            
            chunk_relationships = self.extract_relationships_from_chunk(chunk)
            all_relationships.extend(chunk_relationships)
            
            # Add a short delay to avoid rate limiting
            time.sleep(0.5)
        
        logger.info(f"Extracted {len(all_relationships)} relationships from all chunks")
        return all_relationships
    
    def evaluate_relationship(self, relationship: Dict, original_text: str) -> Dict:
        """
        Evaluate a single relationship using the critic LLM
        
        Args:
            relationship: The relationship to evaluate
            original_text: The original text chunk
            
        Returns:
            Evaluation results for this specific relationship
        """
        # Create relationship-specific critic prompt
        critic_prompt = f"""
        You are an expert reviewer of relationship extraction for a planetary health knowledge graph.
        
        Below is an original text excerpt, followed by a single RELATIONSHIP that was extracted from it.
        Your job is to critically evaluate this specific relationship extraction.
        
        ORIGINAL TEXT:
        {original_text}
        
        EXTRACTED RELATIONSHIP:
        {json.dumps(relationship, indent=2)}
        
        Please evaluate the following aspects for this specific relationship:
        1. Evidence: Is there clear evidence for this relationship in the text?
        2. Accuracy: Are the source and target entities correctly identified?
        3. Type: Is the relationship type appropriate and accurate?
        4. Direction: Is the relationship direction correct (if applicable)?
        5. Strength: Is the relationship strength rating appropriate?
        6. Relevance: Is this relationship relevant to planetary health?
        
        Respond in the following JSON format:
        {{
          "relationship_id": "{relationship.get('id', 'unknown')}",
          "evaluation": {{
            "evidence_score": 1-5,
            "accuracy_score": 1-5,
            "type_score": 1-5,
            "direction_score": 1-5,
            "strength_score": 1-5,
            "relevance_score": 1-5,
            "confidence_score": 1-5,
            "issues_identified": [
              {{
                "issue_type": "evidence|accuracy|type|direction|strength|relevance",
                "description": "Specific description of the issue",
                "severity": 1-5,
                "suggested_correction": "suggested fix (if applicable)"
              }}
            ],
            "human_review_recommended": true|false,
            "human_review_reason": "Explanation (if applicable)",
            "extraction_quality": "excellent|good|fair|poor"
          }}
        }}
        """
        
        try:
            # Call the critic LLM
            response = self.critic_llm_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4000,
                system="You are a critical evaluator of relationship extractions for knowledge graph construction.",
                messages=[
                    {"role": "user", "content": critic_prompt}
                ],
                temperature=0.2
            )

            try:
                evaluation = json.loads(response.content[0].text)
                return evaluation.get("evaluation", {})
            except json.JSONDecodeError:
                logger.warning("Failed to parse critic LLM response for relationship")
                return {
                    "human_review_recommended": True,
                    "human_review_reason": "Failed to parse critic LLM response",
                    "confidence_score": 1,
                    "extraction_quality": "poor"
                }
                
        except Exception as e:
            logger.error(f"Error calling critic LLM for relationship: {str(e)}")
            return {
                "human_review_recommended": True,
                "human_review_reason": f"Error calling critic LLM: {str(e)}",
                "confidence_score": 1,
                "extraction_quality": "poor"
            }
    
    def resolve_relationships_with_entities(self, relationships: List[Dict], entities_by_type: Dict[str, List[Dict]]) -> List[Dict]:
        """
        Resolve relationships by mapping entity names to IDs using fuzzy matching
        
        Args:
            relationships: List of relationships to resolve
            entities_by_type: Dictionary of entities organized by type
            
        Returns:
            List of resolved relationships with entity IDs
        """
        # Build entity map for fuzzy matching
        entity_map = self._build_entity_map_with_fuzzy_keys(entities_by_type)
        
        resolved_relationships = []
        
        logger.info(f"Resolving {len(relationships)} relationships with fuzzy matching")
        logger.info(f"Entity map keys: {list(entity_map.keys())}")
        for entity_type, entities in entity_map.items():
            logger.info(f"  {entity_type}: {len(set(entities.values()))} unique entities")
        
        for i, rel in enumerate(relationships):
            logger.debug(f"Processing relationship {i+1}: {rel}")
            
            source_type = rel.get("source_type", "").lower()
            target_type = rel.get("target_type", "").lower()
            source_name = rel.get("source", "")
            target_name = rel.get("target", "")
            
            # Skip if missing required fields
            if not source_type or not target_type or not source_name or not target_name:
                logger.debug(f"Skipping relationship - missing required fields")
                continue
            
            # Look up source and target IDs with fuzzy matching
            source_id = self._find_entity_id(source_name, source_type, entity_map, entities_by_type)
            target_id = self._find_entity_id(target_name, target_type, entity_map, entities_by_type)
            
            # Skip if either ID is missing
            if not source_id or not target_id:
                logger.debug(f"Skipping relationship - missing IDs (source: {source_id}, target: {target_id})")
                continue
            
            # Create resolved relationship
            resolved_rel = {
                "id": str(uuid.uuid4()),
                "source_id": source_id,
                "source_type": source_type,
                "target_id": target_id,
                "target_type": target_type,
                "relationship_type": rel.get("relationship_type"),
                "description": rel.get("description", ""),
                "strength": rel.get("strength", 3),
                "source_chunk": rel.get("source_chunk")
            }
            
            # Preserve review flags if they exist
            if rel.get("needs_review"):
                resolved_rel["needs_review"] = True
                resolved_rel["review_task_id"] = rel.get("review_task_id")
            
            resolved_relationships.append(resolved_rel)
        
        logger.info(f"Successfully resolved: {len(resolved_relationships)}/{len(relationships)} relationships")
        return resolved_relationships
    
    def _build_entity_map_with_fuzzy_keys(self, entities: Dict[str, List[Dict]]) -> Dict[str, Dict[str, str]]:
        """
        Build a map of entity names to IDs by type, including normalized names for fuzzy matching
        """
        entity_map = {entity_type: {} for entity_type in entities.keys()}
        
        for entity_type, entity_list in entities.items():
            for entity in entity_list:
                if entity_type == "event":
                    original_name = entity.get("title", "")
                else:
                    original_name = entity.get("name", "")
                
                # Skip empty names
                if not original_name:
                    continue
                
                entity_id = entity["id"]
                
                # Store both original and normalized versions
                entity_map[entity_type][original_name.lower()] = entity_id
                
                normalized = self._normalize_name(original_name)
                if normalized and normalized != original_name.lower():
                    entity_map[entity_type][normalized] = entity_id
        
        return entity_map
    
    def _find_entity_id(self, entity_name: str, entity_type: str, entity_map: Dict[str, Dict[str, str]], entities_by_type: Dict[str, List[Dict]]) -> Optional[str]:
        """
        Find entity ID using exact match first, then fuzzy matching
        """
        # Try exact match first
        if entity_type in entity_map and entity_name.lower() in entity_map[entity_type]:
            return entity_map[entity_type][entity_name.lower()]
        
        # Try fuzzy matching
        return self._find_best_entity_match(entity_name, entity_type, entities_by_type)
    
    def _find_best_entity_match(self, target_name: str, target_type: str, entities_by_type: Dict[str, List[Dict]], threshold: float = 0.6) -> Optional[str]:
        """
        Find the best matching entity using fuzzy matching
        """
        if target_type not in entities_by_type:
            return None
        
        best_match = None
        best_score = threshold
        
        for entity in entities_by_type[target_type]:
            if target_type == "event":
                entity_name = entity.get("title", "")
            else:
                entity_name = entity.get("name", "")
            
            if not entity_name:
                continue
            
            score = self._calculate_similarity(target_name, entity_name)
            
            if score > best_score:
                best_score = score
                best_match = entity.get("id")
        
        return best_match
    
    def _normalize_name(self, name: str) -> str:
        """
        Normalize entity names for fuzzy matching
        """
        if not name:
            return ""
        
        # Convert to lowercase
        normalized = name.lower()
        
        # Remove common parenthetical qualifiers
        normalized = re.sub(r'\s*\([^)]*\)', '', normalized)
        
        # Remove common prefixes/suffixes
        normalized = re.sub(r'^(the|a|an)\s+', '', normalized)
        normalized = re.sub(r'\s+(movement|laws?|concept|theory|model)s?$', '', normalized)
        
        # Replace common abbreviations
        abbreviation_map = {
            'ron': 'rights of nature',
            'us': 'united states',
            'uk': 'united kingdom'
        }
        
        for abbrev, full in abbreviation_map.items():
            normalized = re.sub(r'\b' + abbrev + r'\b', full, normalized)
        
        # Remove extra whitespace and punctuation
        normalized = re.sub(r'[^\w\s]', '', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized
    
    def _calculate_similarity(self, name1: str, name2: str) -> float:
        """
        Calculate similarity between two entity names
        """
        # Normalize both names
        norm1 = self._normalize_name(name1)
        norm2 = self._normalize_name(name2)
        
        if not norm1 or not norm2:
            return 0.0
        
        # Exact match after normalization
        if norm1 == norm2:
            return 1.0
        
        # Check if one is contained in the other
        if norm1 in norm2 or norm2 in norm1:
            return 0.8
        
        # Calculate word overlap
        words1 = set(norm1.split())
        words2 = set(norm2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        # Jaccard similarity
        jaccard = len(intersection) / len(union)
        
        # Boost score if key words match
        key_word_bonus = 0.0
        key_words = {'rights', 'nature', 'environmental', 'indigenous', 'constitutional', 'treaty', 'development'}
        
        if intersection.intersection(key_words):
            key_word_bonus = 0.2
        
        return min(1.0, jaccard + key_word_bonus)
    
    def deduplicate_relationships(self, relationships: List[Dict]) -> List[Dict]:
        """
        Remove duplicate relationships based on source, target, and type
        """
        seen_relationships = set()
        deduplicated = []
        
        for rel in relationships:
            # Create a key for deduplication
            key = (
                rel.get("source_id", ""),
                rel.get("target_id", ""),
                rel.get("relationship_type", "")
            )
            
            if key not in seen_relationships:
                seen_relationships.add(key)
                deduplicated.append(rel)
            else:
                logger.debug(f"Skipping duplicate relationship: {key}")
        
        logger.info(f"Deduplicated relationships: {len(deduplicated)}/{len(relationships)} kept")
        return deduplicated
    
    def filter_relationships_by_confidence(self, relationships: List[Dict], min_confidence: float = 0.5) -> List[Dict]:
        """
        Filter relationships based on confidence scores
        """
        filtered = []
        
        for rel in relationships:
            confidence = rel.get("confidence_score", 1.0)
            if confidence >= min_confidence:
                filtered.append(rel)
            else:
                logger.debug(f"Filtering out low-confidence relationship: {confidence}")
        
        logger.info(f"Filtered relationships by confidence: {len(filtered)}/{len(relationships)} kept")
        return filtered
    
    def enrich_relationships_with_context(self, relationships: List[Dict], entities_by_type: Dict[str, List[Dict]]) -> List[Dict]:
        """
        Enrich relationships with additional context from the entities they connect
        """
        # Create entity lookup for quick access
        entity_lookup = {}
        for entity_type, entity_list in entities_by_type.items():
            for entity in entity_list:
                entity_lookup[entity["id"]] = entity
        
        enriched_relationships = []
        
        for rel in relationships:
            enriched_rel = rel.copy()
            
            # Add source entity context
            source_entity = entity_lookup.get(rel.get("source_id"))
            if source_entity:
                if rel.get("source_type") == "event":
                    enriched_rel["source_name"] = source_entity.get("title", "")
                else:
                    enriched_rel["source_name"] = source_entity.get("name", "")
                enriched_rel["source_description"] = source_entity.get("description", "")
            
            # Add target entity context
            target_entity = entity_lookup.get(rel.get("target_id"))
            if target_entity:
                if rel.get("target_type") == "event":
                    enriched_rel["target_name"] = target_entity.get("title", "")
                else:
                    enriched_rel["target_name"] = target_entity.get("name", "")
                enriched_rel["target_description"] = target_entity.get("description", "")
            
            enriched_relationships.append(enriched_rel)
        
        return enriched_relationships