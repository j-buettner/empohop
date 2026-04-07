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
from entity_resolver import resolve_entities, merge_entities, create_disambiguation_report, EXAMPLE_MANUAL_MAPPINGS
from config import DEFAULT_MODEL, MAX_TOKENS, CONTEXT_SENTENCE, CONTEXT_PHRASE
from extraction_utils import validate_extracted_entities

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define entity extraction prompts with supporting text
EVENT_EXTRACTION_PROMPT = f"""

{CONTEXT_SENTENCE} Identify any EVENTS and PROCESSES mentioned.
For each event, extract:
1. Title (required)
2. Year or period
3. Description
4. Type (Publication, Conference, Meeting, Policy, Research, Movement, Organization, Court decision, Other)
5. Juridical significance, I.e. significance concerning recognizing the rights of nature (1-5 scale)
6. Harmony significance, I.e. significance concerning living in harmony with nature (1-5 scale)
7. Start/end dates (if mentioned)
8. Associated locations
9. Key actors involved
10. Related concepts
11. Supporting text (required) - the exact excerpt from the text that supports this event extraction

Text to analyze:
{{text}}

Respond in the following JSON format:
{{{{
  "events": [
    {{{{
      "title": "Event title",
      "year": YYYY,
      "description": "Detailed description",
      "type": "Event type",
      "juridical significance": N,
      "harmony significance": N,
      "dates": {{{{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}}}},
      "locations": ["Location names"],
      "actors": ["Actor names"],
      "concepts": ["Concept names"],
      "supporting_text": "The exact text excerpt that mentions and supports this event extraction"
    }}}}
  ]
}}}}
"""

ACTOR_EXTRACTION_PROMPT = f"""
{CONTEXT_SENTENCE} Actors can be individuals, organizations, institutions, or other entities that participate in the planetary health movement.

For each actor, extract:
1. Name (required)
2. Type (Individual, Organizations, Government, NGO, Coalition, Indigenous and local communities, Other)
3. Description
4. Role in {CONTEXT_PHRASE} 
5. Country/location
6. Supporting text (required) - the exact excerpt from the text that mentions this actor

Text to analyze:
{{text}}

Respond in the following JSON format:
{{{{
  "actors": [
    {{{{
      "name": "Actor name",
      "type": "Actor type",
      "description": "Description of the actor",
      "role": "Role in eco-jurisprudence and living in harmony with nature",
      "country": "Country code or name",
      "supporting_text": "The exact text excerpt that mentions this actor"
    }}}}
  ]
}}}}
"""

CONCEPT_EXTRACTION_PROMPT = f"""
{CONTEXT_SENTENCE} Identify any CONCEPTS mentioned.
Concepts can be theories, ideas, frameworks, or terms relevant to {CONTEXT_PHRASE}.
For each concept, extract:
1. Name (required)
2. Definition/explanation (required)
3. Proponents
4. Supporting text (required) - the exact excerpt from the text that mentions this concept

Text to analyze:
{{text}}

Respond in the following JSON format:
{{{{
  "concepts": [
    {{{{
      "name": "Concept name",
      "definition": "Definition or explanation",
      "key_proponents": ["Proponent 1", "Proponent 2"],
      "supporting_text": "The exact text excerpt that mentions this concept"
    }}}}
  ]
}}}}
"""

EXPRESSION_EXTRACTION_PROMPT = f"""
{CONTEXT_SENTENCE} Identify any EXPRESSION mentioned. Such expression can for instance be important publications, speeches, material symbols, cultural practices, legal documents, rules, regulations.

For each publication, extract:
1. Title (required)
2. Type
3. Year (required if mentioned)
4. Related actors
5. Supporting text (required) - the exact excerpt from the text that mentions this publication

Text to analyze:
{{text}}

Respond in the following JSON format:
{{{{
  "publications": [
    {{{{
      "title": "Expression title",
      "type": "Expression type",
      "year": YYYY,
      "actors": ["Actor 1", "Actor 2"],
      "supporting_text": "The exact text excerpt that mentions this publication"
    }}}}
  ]
}}}}
"""

LOCATION_EXTRACTION_PROMPT = f"""
{CONTEXT_SENTENCE} Identify any LOCATIONS mentioned.
Locations can be countries, cities, regions, or specific places relevant to planetary health events.
For each location, extract:
1. Name (required)
2. Type (Country, City, Region, Institution, Other)
3. Country (if not a country itself)
4. Description/context
5. Significance to planetary health
6. Supporting text (required) - the exact excerpt from the text that mentions this location

Text to analyze:
{{text}}

Respond in the following JSON format:
{{{{
  "locations": [
    {{{{
      "name": "Location name",
      "type": "Location type",
      "country": "Country name or code",
      "description": "Description or context",
      "significance": "Why this location is significant to planetary health",
      "supporting_text": "The exact text excerpt that mentions this location"
    }}}}
  ]
}}}}
"""

# Define entity types and their corresponding prompts
ENTITY_PROMPTS = {
    "event": EVENT_EXTRACTION_PROMPT,
    "actor": ACTOR_EXTRACTION_PROMPT,
    "concept": CONCEPT_EXTRACTION_PROMPT,
    "expression": EXPRESSION_EXTRACTION_PROMPT,
    "location": LOCATION_EXTRACTION_PROMPT
}

class LLMProcessor:
    """
    Process document chunks with an LLM to extract entities with supporting text
    """
    
    def __init__(self, llm_client, manual_mappings=None):
        """
        Initialize the LLM processor
        
        Args:
            llm_client: Client for the primary LLM
            manual_mappings: Optional dictionary of manual entity mappings
        """
        self.llm_client = llm_client
        self.relationship_processor = RelationshipProcessor(llm_client)
        self.manual_mappings = manual_mappings or {}
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
        # Format prompt with chunk text, ensuring proper Unicode handling
        try:
            # Normalise typographic Unicode to their plain equivalents so the
            # LLM prompt is clean, but preserve all other Unicode (accented
            # characters, CJK, etc.) — the Claude API handles UTF-8 natively.
            chunk_text = chunk["text"]
            if isinstance(chunk_text, str):
                chunk_text = chunk_text.replace('\u201c', '"').replace('\u201d', '"')
                chunk_text = chunk_text.replace('\u2018', "'").replace('\u2019', "'")
                chunk_text = chunk_text.replace('\u2013', '-').replace('\u2014', '--')
                chunk_text = chunk_text.replace('\u00a0', ' ')   # Non-breaking space
                chunk_text = chunk_text.replace('\u2026', '...')  # Ellipsis
                chunk_text = chunk_text.replace('\u00ad', '')     # Soft hyphen
                chunk_text = chunk_text.replace('\u200b', '')     # Zero-width space

            prompt = prompt_template.format(text=chunk_text)
        except KeyError as e:
            logger.error(f"Error formatting prompt: {str(e)}")
            return {"error": f"Error formatting prompt: {str(e)}"}
        except UnicodeEncodeError as e:
            logger.error(f"Unicode encoding error: {str(e)}")
            return {"error": f"Unicode encoding error: {str(e)}"}
        
        try:
            # Call LLM API
            response = self.llm_client.messages.create(
                model=DEFAULT_MODEL,
                max_tokens=MAX_TOKENS,
                system="You are an expert in extracting structured information about eco-jurisprudence and living in harmony with nature from academic texts. Always include supporting text that justifies each extraction.",
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
                
                # Add fallback supporting text and soft-validate against schemas
                for entity_type, entities in result.items():
                    if isinstance(entities, list):
                        for entity in entities:
                            if isinstance(entity, dict) and not entity.get("supporting_text"):
                                entity["supporting_text"] = self._find_supporting_text(entity, entity_type, chunk["text"])
                        # Strip trailing 's' to get the singular type key used in schemas
                        singular = entity_type.rstrip("s")
                        validate_extracted_entities(singular, entities)

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
            error_msg = str(e)
            logger.error(f"Error calling LLM API: {error_msg}")
            return {"error": error_msg}
    
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
                      update_after_each: bool = False, output_dir: str = None, 
                      base_filename: str = None, create_report: bool = True) -> Dict:
        """
        Process a list of document chunks to extract entities and relationships using a 3-phase approach
        
        Args:
            chunks: List of document chunks
            entity_types: List of entity types to extract (default: all)
            extract_relationships: Whether to extract relationships
            update_after_each: Whether to write/update output files after each chunk
            output_dir: Output directory for intermediate results
            base_filename: Base filename for intermediate results
            create_report: Whether to create a disambiguation report
            
        Returns:
            Dictionary with extracted entities, relationships, and statistics
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
                    "stats": {
                        "total_chunks": len(chunks),
                        "chunks_processed": i + 1,
                        "phase": "entities_only",
                        "entity_counts": {entity_type: len(entities) for entity_type, entities in all_entities.items()},
                        "relationship_count": 0
                    }
                }
                
                # Resolve and deduplicate entities so far
                resolved_entities = resolve_entities(intermediate_results["entities"], manual_mappings=self.manual_mappings)
                intermediate_results["entities"] = resolved_entities
                
                logger.info(f"Saving intermediate entity results after chunk {i+1}/{len(chunks)}")
                save_results(intermediate_results, output_dir, f"{base_filename}_entities_phase1_{i+1}")
        
        logger.info("=== PHASE 2: EXTRACTING RELATIONSHIPS FROM ALL CHUNKS ===")
        
        # PHASE 2: Extract relationships if requested
        if extract_relationships:
            all_relationships = self.relationship_processor.extract_relationships_from_chunks(chunks)
        
        logger.info("=== PHASE 3: ENTITY RESOLUTION AND FINAL PROCESSING ===")
        
        # Resolve and deduplicate entities
        logger.info("Resolving and deduplicating entities")
        resolved_entities = resolve_entities(all_entities, manual_mappings=self.manual_mappings)
        
        # Create disambiguation report if requested
        if create_report and output_dir and base_filename:
            report_path = os.path.join(output_dir, f"{base_filename}_disambiguation_report.json")
            # Re-run resolution with report generation
            resolved_entities = create_disambiguation_report(
                all_entities, 
                report_path, 
                manual_mappings=self.manual_mappings
            )
        
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
            "stats": {
                "total_chunks": len(chunks),
                "chunks_processed": len(chunks),
                "entity_counts": {entity_type: len(entities) for entity_type, entities in resolved_entities.items()},
                "relationship_count": len(resolved_relationships)
            }
        }


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
    parser.add_argument("--max-chunks", type=int, default=None, help="Maximum number of chunks to process")
    parser.add_argument("--chunk-index", type=int, default=None, help="Process only the chunk at this index (0-based)")
    parser.add_argument("--chunk-range", type=str, default=None, help="Process chunks in this range (e.g., '0-5')")
    parser.add_argument("--update-after-each", action="store_true", help="Write/update output files after each chunk is processed")
    parser.add_argument("--manual-mappings", type=str, default=None, help="Path to JSON file with manual entity mappings")
    parser.add_argument("--use-example-mappings", action="store_true", help="Use built-in example manual mappings")
    parser.add_argument("--no-disambiguation-report", action="store_true", help="Skip creating disambiguation report")
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
        
        # Load manual mappings if provided
        manual_mappings = {}
        if args.manual_mappings:
            with open(args.manual_mappings, 'r', encoding='utf-8') as f:
                manual_mappings = json.load(f)
            logger.info(f"Loaded manual mappings from {args.manual_mappings}")
        elif args.use_example_mappings:
            manual_mappings = EXAMPLE_MANUAL_MAPPINGS
            logger.info("Using built-in example manual mappings")
        
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
            
            # Initialize LLM processor with manual mappings
            processor = LLMProcessor(llm_client=client, manual_mappings=manual_mappings)
            
            # Get base filename for outputs
            base_filename = os.path.splitext(os.path.basename(args.chunks_file))[0]
            if base_filename.endswith("_chunks"):
                base_filename = base_filename[:-7]  # Remove "_chunks" suffix
            
            # Process chunks
            results = processor.process_chunks(
                chunks=chunks,
                entity_types=args.entity_types,
                extract_relationships=not args.no_relationships,
                update_after_each=args.update_after_each,
                output_dir=args.output_dir,
                base_filename=base_filename,
                create_report=not args.no_disambiguation_report
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
            
            if not args.no_disambiguation_report:
                report_path = os.path.join(args.output_dir, f"{base_filename}_disambiguation_report.json")
                logger.info(f"  - Disambiguation Report: {report_path}")
            
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
