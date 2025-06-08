import argparse
import json
import logging
import os
import sys
import uuid
from typing import Dict, List, Optional, Any, Union
import time
import re
from relationship_processor import RelationshipProcessor

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define entity extraction prompts with supporting text
EVENT_EXTRACTION_PROMPT = """
Analyze the following text from a document about planetary health and identify any EVENTS mentioned.
For each event, extract:
1. Title (required)
2. Year (required)
3. Description (required)
4. Type (Publication, Conference, Policy, Research, Movement, Organization, Other)
5. Significance (1-5 scale)
6. Start/end dates (if mentioned)
7. Associated locations
8. Key actors involved
9. Related concepts
10. Supporting text (required) - the exact excerpt from the text that supports this event extraction

Text to analyze:
{text}

Respond in the following JSON format:
{{
  "events": [
    {{
      "title": "Event title",
      "year": YYYY,
      "description": "Detailed description",
      "type": "Event type",
      "significance": N,
      "dates": {{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}},
      "locations": ["Location names"],
      "actors": ["Actor names"],
      "concepts": ["Concept names"],
      "supporting_text": "The exact text excerpt that mentions and supports this event extraction"
    }}
  ]
}}
"""

ACTOR_EXTRACTION_PROMPT = """
Analyze the following text from a document about planetary health and identify any ACTORS mentioned.
Actors can be individuals, organizations, institutions, or other entities that participate in the planetary health movement.
For each actor, extract:
1. Name (required)
2. Type (Individual, Institution, Government, NGO, Coalition, Other)
3. Description
4. Role in planetary health
5. Country/location
6. Expertise/fields
7. Affiliations
8. Supporting text (required) - the exact excerpt from the text that mentions this actor

Text to analyze:
{text}

Respond in the following JSON format:
{{
  "actors": [
    {{
      "name": "Actor name",
      "type": "Actor type",
      "description": "Description of the actor",
      "role": "Role in planetary health",
      "country": "Country code or name",
      "expertise": ["Field 1", "Field 2"],
      "affiliations": ["Affiliated organization 1", "Affiliated organization 2"],
      "supporting_text": "The exact text excerpt that mentions this actor"
    }}
  ]
}}
"""

CONCEPT_EXTRACTION_PROMPT = """
Analyze the following text from a document about planetary health and identify any CONCEPTS mentioned.
Concepts can be theories, ideas, frameworks, or terms relevant to planetary health.
For each concept, extract:
1. Name (required)
2. Definition/explanation (required)
3. Alternative names/synonyms
4. Related domains/fields
5. Significance (1-5 scale)
6. Related concepts
7. Key proponents
8. Supporting text (required) - the exact excerpt from the text that mentions this concept

Text to analyze:
{text}

Respond in the following JSON format:
{{
  "concepts": [
    {{
      "name": "Concept name",
      "definition": "Definition or explanation",
      "alternative_names": ["Synonym 1", "Synonym 2"],
      "domain": ["Field 1", "Field 2"],
      "significance": N,
      "related_concepts": ["Related concept 1", "Related concept 2"],
      "key_proponents": ["Proponent 1", "Proponent 2"],
      "supporting_text": "The exact text excerpt that mentions this concept"
    }}
  ]
}}
"""

PUBLICATION_EXTRACTION_PROMPT = """
Analyze the following text from a document about planetary health and identify any PUBLICATIONS mentioned.
Publications can be books, articles, reports, or other published materials.
For each publication, extract:
1. Title (required)
2. Type (Journal Article, Book, Report, Policy Document, Other)
3. Year (required if mentioned)
4. Authors
5. Publisher/journal
6. DOI/ISBN (if mentioned)
7. Abstract/summary
8. Significance (1-5 scale)
9. Supporting text (required) - the exact excerpt from the text that mentions this publication

Text to analyze:
{text}

Respond in the following JSON format:
{{
  "publications": [
    {{
      "title": "Publication title",
      "type": "Publication type",
      "year": YYYY,
      "authors": ["Author 1", "Author 2"],
      "publisher": "Publisher or journal name",
      "identifier": "DOI or ISBN",
      "abstract": "Brief summary",
      "significance": N,
      "supporting_text": "The exact text excerpt that mentions this publication"
    }}
  ]
}}
"""

LOCATION_EXTRACTION_PROMPT = """
Analyze the following text from a document about planetary health and identify any LOCATIONS mentioned.
Locations can be countries, cities, regions, or specific places relevant to planetary health events.
For each location, extract:
1. Name (required)
2. Type (Country, City, Region, Institution, Other)
3. Country (if not a country itself)
4. Description/context
5. Significance to planetary health
6. Supporting text (required) - the exact excerpt from the text that mentions this location

Text to analyze:
{text}

Respond in the following JSON format:
{{
  "locations": [
    {{
      "name": "Location name",
      "type": "Location type",
      "country": "Country name or code",
      "description": "Description or context",
      "significance": "Why this location is significant to planetary health",
      "supporting_text": "The exact text excerpt that mentions this location"
    }}
  ]
}}
"""

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

For each relationship, include the supporting text that evidences this relationship.

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
      "strength": 1-5,
      "supporting_text": "The exact text excerpt that supports this relationship"
    }}
  ]
}}
"""

# Define entity types and their corresponding prompts
ENTITY_PROMPTS = {
    "event": EVENT_EXTRACTION_PROMPT,
    "actor": ACTOR_EXTRACTION_PROMPT,
    "concept": CONCEPT_EXTRACTION_PROMPT,
    "publication": PUBLICATION_EXTRACTION_PROMPT,
    "location": LOCATION_EXTRACTION_PROMPT
}

class LLMProcessor:
    """
    Process document chunks with an LLM to extract entities with supporting text
    """
    
    def __init__(self, llm_client, critic_llm_client=None):
        """
        Initialize the LLM processor
        
        Args:
            llm_client: Client for the primary LLM
            critic_llm_client: Client for the critic LLM (optional)
        """
        self.llm_client = llm_client
        self.critic_llm_client = critic_llm_client or llm_client
        self.relationship_processor = RelationshipProcessor(llm_client, critic_llm_client)
        logger.info("Initialized LLMProcessor with supporting text extraction and relationship processing")
    
    def process_chunk(self, chunk: Dict, prompt_template: str) -> Dict:
        """
        Process a document chunk with the LLM using the specified prompt template
        
        Args:
            chunk: Document chunk with text and metadata
            prompt_template: Prompt template to use
            
        Returns:
            LLM response parsed as a dictionary
        """
        # Format prompt with chunk text
        try:
            prompt = prompt_template.format(text=chunk["text"])
        except KeyError as e:
            logger.error(f"Error formatting prompt: {str(e)}")
            return {"error": f"Error formatting prompt: {str(e)}"}
        
        try:
            # Call LLM API
            response = self.llm_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=8000,
                system="You are an expert in extracting structured information about planetary health from academic texts. Always include supporting text that justifies each extraction.",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1  # Low temperature for more deterministic extraction
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
                
                # Add fallback supporting text for any entities missing it
                for entity_type, entities in result.items():
                    if isinstance(entities, list):
                        for entity in entities:
                            if isinstance(entity, dict) and not entity.get("supporting_text"):
                                entity["supporting_text"] = self._find_supporting_text(entity, entity_type, chunk["text"])
                
                return result
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse LLM response as JSON: {str(e)}")
                
                # Try to extract any JSON-like structure from the response
                content = response.content[0].text
                
                # Look for entity type keys in the response
                entity_types = ["events", "actors", "concepts", "publications", "locations", "relationships"]
                extracted_data = {}
                
                for entity_type in entity_types:
                    if f'"{entity_type}"' in content or f"'{entity_type}'" in content:
                        extracted_data[entity_type] = []
                        logger.info(f"Found entity type '{entity_type}' in response")
                
                if extracted_data:
                    logger.info(f"Extracted entity types from response: {list(extracted_data.keys())}")
                    return extracted_data
                else:
                    logger.error(f"Could not extract any entity types from response")
                    return {"error": "Failed to parse LLM response", "raw_response": content[:500] + "..." if len(content) > 500 else content}
                
        except Exception as e:
            logger.error(f"Error calling LLM API: {str(e)}")
            return {"error": str(e)}
    
    def _find_supporting_text(self, entity: Dict, entity_type: str, chunk_text: str) -> str:
        """
        Find supporting text for an entity if not provided by LLM
        
        Args:
            entity: The extracted entity
            entity_type: Type of entity (event, actor, concept, etc.)
            chunk_text: The original chunk text
            
        Returns:
            Supporting text excerpt
        """
        # Get entity name/title for searching
        if entity_type == "event":
            name = entity.get("title", "").lower()
        else:
            name = entity.get("name", "").lower()
        
        year = str(entity.get("year", ""))
        
        # Split text into sentences
        sentences = chunk_text.split('. ')
        
        # Look for sentences containing key terms from the entity
        supporting_sentences = []
        
        for sentence in sentences:
            sentence_lower = sentence.lower()
            
            # Check if sentence contains entity name keywords or year
            name_words = name.split()
            if len(name_words) > 1:
                # Check if sentence contains multiple words from name
                matches = sum(1 for word in name_words if len(word) > 3 and word in sentence_lower)
                if matches >= 2 or (year and year in sentence):
                    supporting_sentences.append(sentence.strip())
            elif name_words and len(name_words[0]) > 3 and name_words[0] in sentence_lower:
                if year and year in sentence:
                    supporting_sentences.append(sentence.strip())
        
        # If we found supporting sentences, return the best ones
        if supporting_sentences:
            # Return up to 2 most relevant sentences, joined together
            return '. '.join(supporting_sentences[:2]) + '.'
        
        # Fallback: return first 200 characters of chunk as context
        return chunk_text[:200] + "..."
    
    def process_chunks(self, chunks: List[Dict], entity_types: List[str] = None, extract_relationships: bool = True, 
                      use_critic: bool = True, update_after_each: bool = False, output_dir: str = None, 
                      base_filename: str = None) -> Dict:
        """
        Process a list of document chunks to extract entities and relationships using a 3-phase approach
        
        Args:
            chunks: List of document chunks
            entity_types: List of entity types to extract (default: all)
            extract_relationships: Whether to extract relationships
            use_critic: Whether to use the critic LLM for evaluation
            update_after_each: Whether to write/update output files after each chunk
            output_dir: Output directory for intermediate results
            base_filename: Base filename for intermediate results
            
        Returns:
            Dictionary with extracted entities, relationships, and review tasks
        """
        # Check if update_after_each is enabled but required parameters are missing
        if update_after_each and (not output_dir or not base_filename):
            logger.error("Output directory and base filename are required when update_after_each is enabled")
            raise ValueError("Output directory and base filename are required when update_after_each is enabled")
        
        # Use all entity types if none specified
        if entity_types is None:
            entity_types = list(ENTITY_PROMPTS.keys())
        
        # Filter prompts to requested entity types
        prompts = {k: v for k, v in ENTITY_PROMPTS.items() if k in entity_types}
        
        # Initialize results
        all_entities = {entity_type: [] for entity_type in entity_types}
        all_relationships = []
        human_review_tasks = []
        
        logger.info("=== PHASE 1: EXTRACTING ENTITIES FROM ALL CHUNKS ===")
        
        # PHASE 1: Extract all entities from all chunks
        for i, chunk in enumerate(chunks):
            logger.info(f"Phase 1 - Processing chunk {i+1}/{len(chunks)} for entities")
            
            chunk_entities = {entity_type: [] for entity_type in entity_types}
            
            # Extract entities from the chunk
            for entity_type, prompt in prompts.items():
                logger.info(f"Extracting {entity_type}s from chunk {i+1}")
                result = self.process_chunk(chunk, prompt)
                
                # Get the plural form of the entity type (e.g., "event" -> "events")
                entity_type_plural = f"{entity_type}s"
                
                # Extract entities from the result
                extracted_entities = result.get(entity_type_plural, [])
                
                # Add chunk info and IDs to entities for tracking
                for entity in extracted_entities:
                    if isinstance(entity, dict):
                        entity["source_chunk"] = i
                        if "id" not in entity:
                            entity["id"] = str(uuid.uuid4())
                
                # Add to chunk entities
                chunk_entities[entity_type].extend(extracted_entities)
                
                # Add a short delay to avoid rate limiting
                time.sleep(0.5)
            
            # Add to our overall collection
            for entity_type, entities in chunk_entities.items():
                all_entities[entity_type].extend(entities)
            
            # Save intermediate entity results if requested
            if update_after_each:
                intermediate_results = {
                    "entities": all_entities,
                    "relationships": [],
                    "human_review_tasks": [],
                    "stats": {
                        "total_chunks": len(chunks),
                        "chunks_processed": i + 1,
                        "phase": "entities_only",
                        "entity_counts": {entity_type: len(entities) for entity_type, entities in all_entities.items()},
                        "relationship_count": 0
                    }
                }
                
                # Resolve and deduplicate entities so far
                resolved_entities = resolve_entities(intermediate_results["entities"])
                intermediate_results["entities"] = resolved_entities
                
                logger.info(f"Saving intermediate entity results after chunk {i+1}/{len(chunks)}")
                save_results(intermediate_results, output_dir, f"{base_filename}_entities_phase1_{i+1}")
        
        logger.info("=== PHASE 2: EXTRACTING RELATIONSHIPS FROM ALL CHUNKS ===")
        
        # PHASE 2: Extract relationships if requested
        if extract_relationships:
            for i, chunk in enumerate(chunks):
                logger.info(f"Phase 2 - Processing chunk {i+1}/{len(chunks)} for relationships")
                
                rel_result = self.process_chunk(chunk, RELATIONSHIP_EXTRACTION_PROMPT)
                chunk_relationships = rel_result.get("relationships", [])
                
                # Add chunk info and IDs to relationships for tracking
                for rel in chunk_relationships:
                    if isinstance(rel, dict):
                        rel["source_chunk"] = i
                        if "id" not in rel:
                            rel["id"] = str(uuid.uuid4())
                
                all_relationships.extend(chunk_relationships)
                
                # Add a short delay to avoid rate limiting
                time.sleep(0.5)
        
        logger.info("=== PHASE 3: ENTITY RESOLUTION AND FINAL PROCESSING ===")
        
        # Resolve and deduplicate entities
        logger.info("Resolving and deduplicating entities")
        resolved_entities = resolve_entities(all_entities)
        
        # Process relationships using RelationshipProcessor
        resolved_relationships = []
        if extract_relationships and all_relationships:
            logger.info("Processing relationships with RelationshipProcessor")
            resolved_relationships = self.relationship_processor.resolve_relationships_with_entities(all_relationships, resolved_entities)
            
            # Deduplicate relationships
            if resolved_relationships:
                logger.info("Deduplicating relationships")
                resolved_relationships = self.relationship_processor.deduplicate_relationships(resolved_relationships)
        
        # Return the results
        return {
            "entities": resolved_entities,
            "relationships": resolved_relationships,
            "human_review_tasks": human_review_tasks,
            "stats": {
                "total_chunks": len(chunks),
                "chunks_processed": len(chunks),
                "chunks_needing_review": len(human_review_tasks),
                "entity_counts": {entity_type: len(entities) for entity_type, entities in resolved_entities.items()},
                "relationship_count": len(resolved_relationships)
            }
        }


def resolve_entities(entities: Dict[str, List[Dict]]) -> Dict[str, List[Dict]]:
    """
    Resolve and deduplicate entities based on name and attributes
    """
    resolved_entities = {entity_type: [] for entity_type in entities.keys()}
    
    for entity_type, entity_list in entities.items():
        # Create a map to track entities by name
        entity_map = {}
        
        for entity in entity_list:
            # Generate a normalized key for comparison
            if entity_type == "event":
                name = entity.get("title", "").lower()
                year = entity.get("year")
                key = f"{name}_{year}" if year else name
            else:
                key = entity.get("name", "").lower()
            
            # Skip empty keys
            if not key:
                continue
            
            # If entity already exists, merge attributes
            if key in entity_map:
                entity_map[key] = merge_entities(entity_map[key], entity)
            else:
                # Add ID if not present
                if "id" not in entity:
                    entity["id"] = str(uuid.uuid4())
                entity_map[key] = entity
        
        # Convert map back to list
        resolved_entities[entity_type] = list(entity_map.values())
    
    return resolved_entities

def merge_entities(entity1: Dict, entity2: Dict) -> Dict:
    """
    Merge two entities, combining their attributes
    """
    # Start with the first entity
    merged = entity1.copy()
    
    # Merge scalar fields (take non-empty values from entity2)
    for key, value in entity2.items():
        if key not in merged or not merged[key]:
            merged[key] = value
        elif key == "description" and value and merged[key] != value:
            # For descriptions, concatenate if different
            merged[key] = f"{merged[key]} {value}"
        elif key == "significance" and value:
            # For significance, take the max
            merged[key] = max(merged[key], value) if merged[key] else value
        elif key == "supporting_text" and value and merged.get("supporting_text") != value:
            # For supporting text, concatenate if different
            merged[key] = f"{merged.get('supporting_text', '')} | {value}"
    
    # Merge list fields
    for key in ["locations", "actors", "concepts", "expertise", "domain", "alternative_names", "authors"]:
        if key in entity2 and entity2[key]:
            if key not in merged:
                merged[key] = entity2[key]
            else:
                # Combine lists and remove duplicates
                merged[key] = list(set(merged[key] + entity2[key]))
    
    return merged

def save_results(results: Dict, output_dir: str, base_filename: str) -> Dict[str, str]:
    """
    Save extraction results to files
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # Save entities by type
    entity_paths = {}
    for entity_type, entities in results["entities"].items():
        entity_path = os.path.join(output_dir, f"{base_filename}_{entity_type}s.json")
        with open(entity_path, 'w', encoding='utf-8') as f:
            json.dump({f"{entity_type}s": entities}, f, indent=2, ensure_ascii=False)
        entity_paths[entity_type] = entity_path
        
        # Also create CSV for each entity type
        csv_path = os.path.join(output_dir, f"{base_filename}_{entity_type}s.csv")
        create_entity_csv(entities, entity_type, csv_path)
        entity_paths[f"{entity_type}_csv"] = csv_path
    
    # Save relationships
    relationships_path = os.path.join(output_dir, f"{base_filename}_relationships.json")
    with open(relationships_path, 'w', encoding='utf-8') as f:
        json.dump({"relationships": results["relationships"]}, f, indent=2, ensure_ascii=False)
    
    # Save combined knowledge graph
    kg_path = os.path.join(output_dir, f"{base_filename}_knowledge_graph.json")
    kg_entities = {f"{entity_type}s": entities for entity_type, entities in results["entities"].items()}
    kg_entities["relationships"] = results["relationships"]
    
    with open(kg_path, 'w', encoding='utf-8') as f:
        json.dump(kg_entities, f, indent=2, ensure_ascii=False)
    
    # Save stats
    stats_path = os.path.join(output_dir, f"{base_filename}_extraction_stats.json")
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(results["stats"], f, indent=2, ensure_ascii=False)
    
    return {
        "entities": entity_paths,
        "relationships": relationships_path,
        "knowledge_graph": kg_path,
        "stats": stats_path
    }

def create_entity_csv(entities: List[Dict], entity_type: str, csv_path: str):
    """
    Create a CSV file for a specific entity type
    """
    if not entities:
        return
    
    with open(csv_path, 'w', encoding='utf-8') as f:
        if entity_type == "event":
            f.write("Title,Year,Type,Significance,Description,Supporting_Text\n")
            for entity in entities:
                title = entity.get("title", "").replace('"', '""')
                year = entity.get("year", "")
                event_type = entity.get("type", "")
                significance = entity.get("significance", "")
                description = entity.get("description", "").replace('"', '""')[:200] + "..." if len(entity.get("description", "")) > 200 else entity.get("description", "")
                supporting_text = entity.get("supporting_text", "").replace('"', '""')[:300] + "..." if len(entity.get("supporting_text", "")) > 300 else entity.get("supporting_text", "")
                f.write(f'"{title}",{year},"{event_type}",{significance},"{description}","{supporting_text}"\n')
        
        elif entity_type == "actor":
            f.write("Name,Type,Role,Country,Description,Supporting_Text\n")
            for entity in entities:
                name = entity.get("name", "").replace('"', '""')
                actor_type = entity.get("type", "")
                role = entity.get("role", "").replace('"', '""')
                country = entity.get("country", "")
                description = entity.get("description", "").replace('"', '""')[:200] + "..." if len(entity.get("description", "")) > 200 else entity.get("description", "")
                supporting_text = entity.get("supporting_text", "").replace('"', '""')[:300] + "..." if len(entity.get("supporting_text", "")) > 300 else entity.get("supporting_text", "")
                f.write(f'"{name}","{actor_type}","{role}","{country}","{description}","{supporting_text}"\n')
        
        elif entity_type == "concept":
            f.write("Name,Definition,Significance,Domain,Supporting_Text\n")
            for entity in entities:
                name = entity.get("name", "").replace('"', '""')
                definition = entity.get("definition", "").replace('"', '""')[:200] + "..." if len(entity.get("definition", "")) > 200 else entity.get("definition", "")
                significance = entity.get("significance", "")
                domain = ", ".join(entity.get("domain", [])) if entity.get("domain") else ""
                supporting_text = entity.get("supporting_text", "").replace('"', '""')[:300] + "..." if len(entity.get("supporting_text", "")) > 300 else entity.get("supporting_text", "")
                f.write(f'"{name}","{definition}",{significance},"{domain}","{supporting_text}"\n')
        
        elif entity_type == "publication":
            f.write("Title,Year,Type,Authors,Publisher,Supporting_Text\n")
            for entity in entities:
                title = entity.get("title", "").replace('"', '""')
                year = entity.get("year", "")
                pub_type = entity.get("type", "")
                authors = ", ".join(entity.get("authors", [])) if entity.get("authors") else ""
                publisher = entity.get("publisher", "").replace('"', '""')
                supporting_text = entity.get("supporting_text", "").replace('"', '""')[:300] + "..." if len(entity.get("supporting_text", "")) > 300 else entity.get("supporting_text", "")
                f.write(f'"{title}",{year},"{pub_type}","{authors}","{publisher}","{supporting_text}"\n')
        
        elif entity_type == "location":
            f.write("Name,Type,Country,Description,Supporting_Text\n")
            for entity in entities:
                name = entity.get("name", "").replace('"', '""')
                location_type = entity.get("type", "")
                country = entity.get("country", "")
                description = entity.get("description", "").replace('"', '""')[:200] + "..." if len(entity.get("description", "")) > 200 else entity.get("description", "")
                supporting_text = entity.get("supporting_text", "").replace('"', '""')[:300] + "..." if len(entity.get("supporting_text", "")) > 300 else entity.get("supporting_text", "")
                f.write(f'"{name}","{location_type}","{country}","{description}","{supporting_text}"\n')

def main():
    """Main function to process document chunks with an LLM"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Process document chunks with an LLM to extract entities with supporting text")
    parser.add_argument("chunks_file", help="Path to JSON file with document chunks")
    parser.add_argument("--output-dir", default="data/processed", help="Directory to save output files")
    parser.add_argument("--entity-types", nargs="+", default=["event", "actor", "concept", "publication", "location"], 
                        help="Entity types to extract")
    parser.add_argument("--no-relationships", action="store_true", help="Skip relationship extraction")
    parser.add_argument("--no-critic", action="store_true", help="Skip critic evaluation")
    parser.add_argument("--max-chunks", type=int, default=None, help="Maximum number of chunks to process")
    parser.add_argument("--chunk-index", type=int, default=None, help="Process only the chunk at this index (0-based)")
    parser.add_argument("--chunk-range", type=str, default=None, help="Process chunks in this range (e.g., '0-5')")
    parser.add_argument("--update-after-each", action="store_true", help="Write/update output files after each chunk is processed")
    args = parser.parse_args()
    
    try:
        # Load document chunks
        with open(args.chunks_file, 'r', encoding='utf-8') as f:
            chunks_data = json.load(f)
        
        # Extract chunks from the loaded data
        if isinstance(chunks_data, list):
            chunks = chunks_data
        else:
            chunks = chunks_data.get("chunks", [])
        
        logger.info(f"Loaded {len(chunks)} chunks from {args.chunks_file}")
        
        # Process only a specific chunk if requested
        if args.chunk_index is not None:
            if 0 <= args.chunk_index < len(chunks):
                logger.info(f"Processing only chunk at index {args.chunk_index}")
                chunks = [chunks[args.chunk_index]]
            else:
                logger.error(f"Chunk index {args.chunk_index} is out of range (0-{len(chunks)-1})")
                sys.exit(1)
        # Process a range of chunks if requested
        elif args.chunk_range is not None:
            try:
                start, end = map(int, args.chunk_range.split('-'))
                if 0 <= start <= end < len(chunks):
                    logger.info(f"Processing chunks in range {start}-{end}")
                    chunks = chunks[start:end+1]
                else:
                    logger.error(f"Chunk range {args.chunk_range} is out of range (0-{len(chunks)-1})")
                    sys.exit(1)
            except ValueError:
                logger.error(f"Invalid chunk range format: {args.chunk_range}. Use 'start-end' format (e.g., '0-5')")
                sys.exit(1)
        # Limit chunks if requested
        elif args.max_chunks and args.max_chunks < len(chunks):
            logger.info(f"Limiting to {args.max_chunks} chunks")
            chunks = chunks[:args.max_chunks]
        
        try:
            import anthropic
            import os
            
            # Initialize Anthropic client using environment variable
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                logger.error("ANTHROPIC_API_KEY environment variable not set")
                sys.exit(1)
                
            client = anthropic.Anthropic(api_key=api_key)
            
            # Initialize LLM processor with supporting text
            processor = LLMProcessor(
                llm_client=client,
                critic_llm_client=client if not args.no_critic else None
            )
            
            # Get base filename for outputs
            base_filename = os.path.splitext(os.path.basename(args.chunks_file))[0]
            if base_filename.endswith("_chunks"):
                base_filename = base_filename[:-7]  # Remove "_chunks" suffix
            
            # Process chunks with supporting text extraction
            results = processor.process_chunks(
                chunks=chunks,
                entity_types=args.entity_types,
                extract_relationships=not args.no_relationships,
                use_critic=not args.no_critic,
                update_after_each=args.update_after_each,
                output_dir=args.output_dir,
                base_filename=base_filename
            )
            
            # Save results
            output_paths = save_results(results, args.output_dir, base_filename)
            
            # Log results
            logger.info(f"Extraction complete. Files saved to {args.output_dir}")
            for entity_type, path in output_paths["entities"].items():
                if not entity_type.endswith("_csv"):
                    logger.info(f"  - {entity_type.capitalize()}s JSON: {path}")
                else:
                    logger.info(f"  - {entity_type.replace('_csv', '').capitalize()}s CSV: {path}")
            
            logger.info(f"  - Relationships: {output_paths['relationships']}")
            logger.info(f"  - Knowledge Graph: {output_paths['knowledge_graph']}")
            logger.info(f"  - Stats: {output_paths['stats']}")
            
            # Print summary statistics
            logger.info("Extraction Summary:")
            for entity_type, count in results["stats"]["entity_counts"].items():
                logger.info(f"  - {entity_type.capitalize()}s: {count}")
            
            logger.info(f"  - Relationships: {results['stats']['relationship_count']}")
            logger.info(f"  - Chunks Processed: {results['stats']['chunks_processed']}/{results['stats']['total_chunks']}")
            
        except ImportError:
            logger.error("Anthropic package not installed. Please install it with 'pip install anthropic'")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Error processing chunks: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
