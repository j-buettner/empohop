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
from config import MAX_TOKENS, CONTEXT_SENTENCE, CONTEXT_PHRASE
from extraction_utils import validate_extracted_entities, retry_api_call
from logging_config import configure_logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared knowledge-graph context preamble
# ---------------------------------------------------------------------------

_KG_PREAMBLE = """\
You are contributing to a structured knowledge graph about the planetary health \
movement — specifically mobilisations towards living in harmony with nature and \
economic activities beyond GDP.

The source text is processed in FIVE separate, focused extraction passes:
  Pass 1 — EVENTS & PROCESSES (conferences, policy adoptions, court decisions, …)
  Pass 2 — ACTORS (individuals, organisations, governments, NGOs, coalitions, …)
  Pass 3 — CONCEPTS (theories, frameworks, ideas, terms, …)
  Pass 4 — EXPRESSIONS (publications, speeches, legal documents, regulations, \
cultural practices, symbols, …)
  Pass 5 — LOCATIONS (countries, cities, regions, institutions, …)

A separate relationship extraction pass will then link entities across all categories.

YOUR TASK: Extract ONLY the category indicated below. Do not extract entities \
that belong to other categories — they will be captured in their own dedicated pass.\
"""

# ---------------------------------------------------------------------------
# Protocol-aligned definitions and cues (from research protocol)
# ---------------------------------------------------------------------------

_EVENT_DEFINITION = (
    "Events are defined as a single occurrence or occasion that contributes to a coherent "
    "chronicle of an initiative when ordered in time. Ideally includes a time reference "
    "(year/month/date). Events must be discrete (not spanning multiple years/decades) and "
    "must fall within 1925–2025 (exclude projections/predictions)."
)
_EVENT_CUES = (
    "Events can be (but are not always) identified by words such as: movement, negotiation, "
    "formal recognition, workshop, meeting, summit, conference, adoption of resolution or agenda, "
    "endorsement of a resolution or agenda, court ruling, forum, formal ban or moratorium, "
    "intergovernmental dialogue, lawsuit, symposium, agreement, alliance formation, seminar, "
    "assembly, convention, ratification, and opening of a first site."
)
_PROCESS_DEFINITION = (
    "Processes are defined as a longer-running sequence of activities or developments explicitly "
    "described in the text, which may span multiple years. Extract only when the text clearly "
    "describes an extended process (e.g., multi-year review, decade-long reform)."
)
_PROCESS_CUES = (
    "Processes can be (but are not always) identified by words such as: long-term process, "
    "ongoing, gradual, over time, over the following years/decades, multi-year review, "
    "consultation process, drafting process, negotiation process, reform, restructuring, "
    "transition, institutionalisation, mainstreaming, implementation, roll-out, scaling up, "
    "expansion, proliferation, diffusion/spread, harmonisation/standardisation, "
    "capacity-building, monitoring and reporting, policy integration, governance shift."
)

_ACTOR_DEFINITION = (
    "An actor is defined as any set of living bodies (individual or collective) to which "
    "observers attribute coherent intention to partake in an initiative. Actors should be "
    "concrete — prefer proper names (e.g., 'Aldo Leopold', 'Greenpeace', 'World Health "
    "Organisation'). Accept specific attributed groups anchored to a place or field "
    "(e.g., 'Ecuadorian judges', 'environmental lawyers'). Exclude overly general groups "
    "(e.g., 'humans', 'society', 'young people', 'activists' without further specification)."
)
_ACTOR_CUES = (
    "Actors can be (but are not always) identified by words such as: Government, indigenous "
    "community, scholar, academic, lawyer, institution, organisation, community, network, "
    "thinker, advocate, scientist, international community, local community, negotiator, "
    "politician, activist, global hub, NGO, transnational network, business leaders, city "
    "officials, state leaders, provincial government, religious leaders, expert, tribunal, "
    "civil society groups, tribes, companies, universities, judge, philanthropic organisation, "
    "broker, founder, co-founder, community leaders, committee, international agency, panel, "
    "researcher, coalition, council, taskforce, associations, policymakers, artists and poets."
)

_CONCEPT_DEFINITION = (
    "A concept is defined as a set of mental representations signifying actors' cognition when "
    "partaking in an initiative. Prefer concrete named concepts (e.g., 'sustainable development', "
    "'Buen Vivir', 'planetary boundaries'). Accept attributed concept categories anchored to a "
    "place, field or established concept (e.g., 'earth-centered approach', 'indigenous "
    "cosmovision'). Note: if the text introduces or quotes a formal definition/standard/rule in "
    "a named document (e.g., 'the Guidelines define…'), extract that as an EXPRESSION instead."
)
_CONCEPT_CUES = (
    "Concepts can be (but are not always) identified by words such as: argument, idea, "
    "terminology, term, principle, paradigm, approach, common understanding, norm, critique, "
    "vision, framing, models, values, view, worldview, doctrine, emerging field, knowledge "
    "system, theory, methodology, conception, theme, philosophy, and metaphor."
)

_EXPRESSION_DEFINITION = (
    "An expression is defined as a tangible, named output created or modified by actors to "
    "record and communicate ideas and practices relevant to an initiative. Prefer concrete "
    "named titles (e.g., 'Treaty of Waitangi', 'Silent Spring', 'Laudato Si'). Do NOT "
    "describe the act of adopting/publishing/holding — those belong in EVENTS."
)
_EXPRESSION_CUES = (
    "Expressions can be (but are not always) identified by words such as: treaty, regulation, "
    "framework, book, policy, declaration, report, resolution, ordinance, law, agreement, "
    "encyclical, rights, statute, statute amendment, court decision, constitution, legal "
    "provision, agenda, document, publication, programme, paper, strategies and action plans, "
    "assessment, journal, protocol, global goals, indicator, editorial, widely referenced text, "
    "study, documentation, practice, regulatory act, decision, metrics, poems, songs, "
    "pictures, and sites."
)

_LOCATION_DEFINITION = (
    "A location is defined as a place-based entity (country, city, region, ecosystem, "
    "protected area, institution, etc.) relevant to the initiative."
)

# ---------------------------------------------------------------------------
# Entity extraction prompts
# ---------------------------------------------------------------------------

EVENT_EXTRACTION_PROMPT = f"""{_KG_PREAMBLE}

--- CURRENT PASS: EVENTS & PROCESSES ---

{CONTEXT_SENTENCE}

Definition: {_EVENT_DEFINITION}
Cues: {_EVENT_CUES}
Process definition: {_PROCESS_DEFINITION}
Process cues: {_PROCESS_CUES}

Rules:
- Cue words are hints, not triggers. Do not extract an event unless the text clearly describes a specific occurrence and you can quote exact supporting_text.
- Time bounds (EVENTS only): extract events only if they fall between 1925 and 2025 (inclusive). Exclude projections/predictions.
- Discreteness (EVENTS only): exclude events that span multiple years/decades — treat such multi-year developments as PROCESSES if explicitly described.
- Event titles should be action-based when applicable (e.g., "Publication of X", "Adoption of Y", "Establishment of A").
- If a field is not mentioned, use null or an empty list.

For each event/process, extract:
1. Title (required)
2. Year or period (required if mentioned)
3. Description
4. Type (Process, Publication, Conference, Meeting, Policy, Research, Movement, Organization, Court decision, Other)
5. Start/end dates (if mentioned)
6. Associated locations
7. Key actors involved
8. Related concepts
9. Supporting text (required) — exact excerpt from the text supporting this extraction

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
      "dates": {{{{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}}}},
      "locations": ["Location names"],
      "actors": ["Actor names"],
      "concepts": ["Concept names"],
      "supporting_text": "The exact text excerpt that supports this extraction"
    }}}}
  ]
}}}}
"""

ACTOR_EXTRACTION_PROMPT = f"""{_KG_PREAMBLE}

--- CURRENT PASS: ACTORS ---

{CONTEXT_SENTENCE}

Definition: {_ACTOR_DEFINITION}
Cues: {_ACTOR_CUES}

Rules:
- Actors must be concrete and attributable. Prefer proper names; accept specific attributed groups (e.g., 'Ecuadorian judges').
- Cue words are hints, not triggers. Do not extract an actor unless the text clearly describes a specific actor and you can quote exact supporting_text.
- Exclude general/ambiguous groups (e.g., 'humans', 'society', 'young people', 'activists') unless made specific by a place, field, or attribution.
- IMPORTANT: All actor subtypes MUST be returned under the single key "actors". Do NOT use separate keys like "organizations", "movements", "individuals", etc.
- If a field is not mentioned, use null or an empty list.

For each actor, extract:
1. Name (required)
2. Type (Individual, Organization, Government, NGO, Coalition, Indigenous and local communities, Other)
3. Description
4. Role in {CONTEXT_PHRASE}
5. Country/location
6. Supporting text (required) — exact excerpt from the text mentioning this actor

Text to analyze:
{{text}}

Respond in the following JSON format — ALL actors in the single "actors" array:
{{{{
  "actors": [
    {{{{
      "name": "Actor name",
      "type": "Actor type",
      "description": "Description of the actor",
      "role": "Role in the initiative",
      "country": "Country code or name",
      "supporting_text": "The exact text excerpt that mentions this actor"
    }}}}
  ]
}}}}
"""

CONCEPT_EXTRACTION_PROMPT = f"""{_KG_PREAMBLE}

--- CURRENT PASS: CONCEPTS ---

{CONTEXT_SENTENCE}

Definition: {_CONCEPT_DEFINITION}
Cues: {_CONCEPT_CUES}

Rules:
- Cue words are hints, not triggers. Do not extract a concept unless the text clearly describes a specific concept and you can quote exact supporting_text.
- If the text introduces or quotes a formal definition/standard/rule in a named document, extract it as an EXPRESSION (not a concept).
- If a field is not mentioned, use null or an empty list.

For each concept, extract:
1. Name (required)
2. Definition/explanation (required; based on the text)
3. Key proponents (if mentioned)
4. Supporting text (required) — exact excerpt from the text mentioning this concept

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

EXPRESSION_EXTRACTION_PROMPT = f"""{_KG_PREAMBLE}

--- CURRENT PASS: EXPRESSIONS ---

{CONTEXT_SENTENCE}

Definition: {_EXPRESSION_DEFINITION}
Cues: {_EXPRESSION_CUES}

Rules:
- Extract only named artefacts (title + type). Do NOT describe the act of adopting/publishing/holding — those belong in EVENTS.
- When the text introduces or quotes a formal definition/standard/rule (e.g., 'Part I sets out a definition…'), extract that definitional statement as an EXPRESSION; the implications belong in CONCEPTS.
- Cue words are hints, not triggers. Do not extract an expression unless the text clearly names a specific artefact and you can quote exact supporting_text.
- If a field is not mentioned, use null or an empty list.

For each expression, extract:
1. Title (required)
2. Type (Book, Report, Guideline, Law, Policy, Declaration, Treaty, Speech, Recommendation, Standard, Programme, Other)
3. Year or period (if mentioned)
4. Related actors
5. Supporting text (required) — exact excerpt from the text mentioning this expression

Text to analyze:
{{text}}

Respond in the following JSON format:
{{{{
  "expressions": [
    {{{{
      "title": "Expression title",
      "type": "Expression type",
      "year": YYYY,
      "actors": ["Actor 1", "Actor 2"],
      "supporting_text": "The exact text excerpt that mentions this expression"
    }}}}
  ]
}}}}
"""

LOCATION_EXTRACTION_PROMPT = f"""{_KG_PREAMBLE}

--- CURRENT PASS: LOCATIONS ---

{CONTEXT_SENTENCE}

Definition: {_LOCATION_DEFINITION}

Rules:
- If a field is not mentioned, use null or an empty list.

For each location, extract:
1. Name (required)
2. Type (Country, City, Region, Institution, Other)
3. Country (if not a country itself)
4. Description/context
5. Supporting text (required) — exact excerpt from the text mentioning this location

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
            # Call LLM API with retry/backoff on transient errors
            response = retry_api_call(
                self.llm_client.messages.create,
                model=self.llm_client.model,
                max_tokens=MAX_TOKENS,
                system="You are an expert knowledge graph builder specialising in eco-jurisprudence and the planetary health movement. You extract one category of entities per pass from academic texts, contributing to a shared structured knowledge graph. Always include supporting text that justifies each extraction.",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
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

                # Collapse any actor sub-type keys the model may have invented
                # (e.g. "organizations", "movements", "individuals") into "actors"
                _ACTOR_ALIASES = {
                    "organizations", "organisation", "organisations", "organization",
                    "movements", "movement", "individuals", "individual",
                    "ngos", "ngo", "governments", "government",
                    "coalitions", "coalition", "institutions", "institution",
                }
                for key in list(result.keys()):
                    if key.lower() in _ACTOR_ALIASES:
                        logger.warning("Merging unexpected key %r into 'actors'", key)
                        result.setdefault("actors", []).extend(result.pop(key))

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
                entity_types = ["events", "actors", "concepts", "expressions", "locations", "relationships"]
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
        all_significance = {"item_significance": [], "relation_significance": []}
        
        logger.info("=== PHASE 1: EXTRACTING ENTITIES AND RELATIONS FROM ALL CHUNKS ===")

        # _TITLE_TYPES: entity types that use "title" as their primary name field
        _TITLE_TYPES = {"event", "expression"}

        # PHASE 1: Extract entities (+ per-chunk relations) from every chunk
        for i, chunk in enumerate(chunks):
            logger.info(f"Phase 1 - Processing chunk {i+1}/{len(chunks)}")

            chunk_entities = {entity_type: [] for entity_type in entity_types}

            # --- 5 entity extraction passes ---
            for entity_type, prompt in prompts.items():
                logger.info(f"  Extracting {entity_type}s from chunk {i+1}")
                result = self.process_chunk(chunk, prompt)

                entity_type_plural = f"{entity_type}s"
                extracted_entities = result.get(entity_type_plural, [])

                # Drop entities missing their primary name field
                _name_field = "name" if entity_type not in _TITLE_TYPES else "title"
                valid_entities = []
                for entity in extracted_entities:
                    if isinstance(entity, dict) and entity.get(_name_field, "").strip():
                        valid_entities.append(entity)
                    else:
                        logger.warning(
                            "Dropping %s entity with empty %r field: %s",
                            entity_type, _name_field, entity
                        )
                extracted_entities = valid_entities

                # Assign UUID and chunk metadata
                for entity in extracted_entities:
                    entity["source_chunk"] = i
                    if "id" not in entity:
                        entity["id"] = str(uuid.uuid4())

                chunk_entities[entity_type].extend(extracted_entities)
                time.sleep(0.5)

            # Accumulate entities
            for entity_type, entities in chunk_entities.items():
                all_entities[entity_type].extend(entities)

            # --- 6th pass: relation extraction (per-chunk, uses extracted items) ---
            chunk_items = []
            for entity_type in ["event", "expression", "concept", "actor", "location"]:
                entities = chunk_entities.get(entity_type, [])
                name_field = "title" if entity_type in _TITLE_TYPES else "name"
                for entity in entities:
                    chunk_items.append({
                        "id": entity["id"],
                        "item_type": entity_type,
                        "name": entity.get(name_field, ""),
                    })

            chunk_relations = []
            if extract_relationships:
                logger.info(f"  Extracting relations from chunk {i+1} ({len(chunk_items)} items)")
                chunk_relations = self.relationship_processor.extract_relations_from_chunk(chunk, chunk_items)
                all_relationships.extend(chunk_relations)
                time.sleep(0.5)

            # --- 7th pass: significance attribution (per-chunk, uses items + relations) ---
            if extract_relationships:
                logger.info(f"  Attributing significance from chunk {i+1}")
                chunk_sig = self.relationship_processor.extract_significance_from_chunk(
                    chunk, chunk_items, chunk_relations
                )
                all_significance["item_significance"].extend(chunk_sig["item_significance"])
                all_significance["relation_significance"].extend(chunk_sig["relation_significance"])
                time.sleep(0.5)

            # Save intermediate results if requested
            if update_after_each:
                intermediate_results = {
                    "entities": all_entities,
                    "relationships": [],
                    "stats": {
                        "total_chunks": len(chunks),
                        "chunks_processed": i + 1,
                        "phase": "entities_only",
                        "entity_counts": {et: len(ents) for et, ents in all_entities.items()},
                        "relationship_count": 0
                    }
                }
                resolved_intermediate = resolve_entities(
                    intermediate_results["entities"], manual_mappings=self.manual_mappings
                )
                intermediate_results["entities"] = resolved_intermediate
                logger.info(f"Saving intermediate results after chunk {i+1}/{len(chunks)}")
                save_results(intermediate_results, output_dir, f"{base_filename}_entities_phase1_{i+1}")

        # Save raw (pre-merge) results so the user can inspect what the LLM extracted
        # before any deduplication is applied.
        if output_dir and base_filename:
            raw_dir = os.path.join(output_dir, "raw")
            os.makedirs(raw_dir, exist_ok=True)
            # Per-type entity files
            for et, ents in all_entities.items():
                raw_entity_path = os.path.join(raw_dir, f"{base_filename}_{et}s.json")
                with open(raw_entity_path, "w", encoding="utf-8") as f:
                    json.dump({f"{et}s": ents}, f, indent=2, ensure_ascii=False)
                csv_path = os.path.join(raw_dir, f"{base_filename}_{et}s.csv")
                create_entity_csv(ents, et, csv_path)
            # Relationships
            raw_rel_path = os.path.join(raw_dir, f"{base_filename}_relationships.json")
            with open(raw_rel_path, "w", encoding="utf-8") as f:
                json.dump({"relationships": all_relationships}, f, indent=2, ensure_ascii=False)
            # Combined KG
            raw_kg = {f"{et}s": ents for et, ents in all_entities.items()}
            raw_kg["relationships"] = all_relationships
            raw_kg_path = os.path.join(raw_dir, f"{base_filename}_knowledge_graph.json")
            with open(raw_kg_path, "w", encoding="utf-8") as f:
                json.dump(raw_kg, f, indent=2, ensure_ascii=False)
            logger.info("Raw (pre-merge) output saved to %s/", raw_dir)

        logger.info("=== PHASE 2: ENTITY RESOLUTION ===")

        # Build pre-resolution UUID → (type, name) map for relation remapping
        _name_field_for = lambda t: "title" if t in _TITLE_TYPES else "name"
        pre_resolution = {
            entity["id"]: (entity_type, entity.get(_name_field_for(entity_type), ""))
            for entity_type, entities in all_entities.items()
            for entity in entities
        }

        # Resolve and deduplicate entities
        logger.info("Resolving and deduplicating entities")
        resolved_entities = resolve_entities(all_entities, manual_mappings=self.manual_mappings)

        # Create disambiguation report if requested
        if create_report and output_dir and base_filename:
            os.makedirs(output_dir, exist_ok=True)
            report_path = os.path.join(output_dir, f"{base_filename}_disambiguation_report.json")
            resolved_entities = create_disambiguation_report(
                all_entities,
                report_path,
                manual_mappings=self.manual_mappings
            )

        logger.info("=== PHASE 3: RELATION REMAPPING AND DEDUPLICATION ===")

        # Build post-resolution (type, name) → UUID map
        post_resolution = {
            (entity_type, entity.get(_name_field_for(entity_type), "")): entity["id"]
            for entity_type, entities in resolved_entities.items()
            for entity in entities
        }

        # Build original UUID → canonical UUID remap
        uuid_map = {}
        for orig_uuid, (entity_type, name) in pre_resolution.items():
            canonical = post_resolution.get((entity_type, name))
            uuid_map[orig_uuid] = canonical if canonical else orig_uuid

        resolved_relationships = []
        resolved_significance = {"item_significance": [], "relation_significance": []}
        if extract_relationships and all_relationships:
            logger.info("Remapping relation UUIDs after entity resolution")
            resolved_relationships = self.relationship_processor.remap_relation_uuids(all_relationships, uuid_map)
            logger.info("Deduplicating relations")
            resolved_relationships = self.relationship_processor.deduplicate_relationships(resolved_relationships)

        if extract_relationships and (all_significance["item_significance"] or all_significance["relation_significance"]):
            logger.info("Remapping significance UUIDs after entity resolution")
            resolved_significance = self.relationship_processor.remap_significance_uuids(all_significance, uuid_map)

        # Return the results
        return {
            "entities": resolved_entities,
            "relationships": resolved_relationships,
            "significance": resolved_significance,
            "stats": {
                "total_chunks": len(chunks),
                "chunks_processed": len(chunks),
                "entity_counts": {entity_type: len(entities) for entity_type, entities in resolved_entities.items()},
                "relationship_count": len(resolved_relationships)
            }
        }


def _attach_significance(results: Dict) -> Dict:
    """
    Merge significance data into each entity and relation in-place.

    item_significance entries are matched to entities by UUID and attached as
    a "significance" field.  relation_significance entries are matched to
    relationships the same way.  The top-level "significance" key is removed
    so consumers always find significance on the item itself.
    """
    sig = results.get("significance", {})
    item_sig_map = {s["id"]: s for s in sig.get("item_significance", []) if "id" in s}
    rel_sig_map  = {s["id"]: s for s in sig.get("relation_significance", []) if "id" in s}

    for entities in results["entities"].values():
        for entity in entities:
            if entity.get("id") in item_sig_map:
                entry = item_sig_map[entity["id"]]
                entity["significance"] = {
                    "primary_category": entry.get("primary_category"),
                    "justification":    entry.get("justification"),
                    "supporting_text":  entry.get("supporting_text"),
                }

    for rel in results["relationships"]:
        if rel.get("id") in rel_sig_map:
            entry = rel_sig_map[rel["id"]]
            rel["significance"] = {
                "primary_category": entry.get("primary_category"),
                "justification":    entry.get("justification"),
                "supporting_text":  entry.get("supporting_text"),
            }

    results.pop("significance", None)
    return results


def save_results(results: Dict, output_dir: str, base_filename: str) -> Dict[str, str]:
    """
    Save extraction results to files.

    Significance is attached to each entity/relation before writing so that
    consumers never need a separate join.
    """
    os.makedirs(output_dir, exist_ok=True)

    results = _attach_significance(results)

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
        
        elif entity_type == "expression":
            f.write("Title,Year,Type,Actors,Supporting_Text\n")
            for entity in entities:
                title = entity.get("title", "").replace('"', '""')
                year = entity.get("year", "")
                exp_type = entity.get("type", "")
                actors = ", ".join(entity.get("actors", [])) if entity.get("actors") else ""
                supporting_text = entity.get("supporting_text", "").replace('"', '""')[:300] + "..." if len(entity.get("supporting_text", "")) > 300 else entity.get("supporting_text", "")
                f.write(f'"{title}",{year},"{exp_type}","{actors}","{supporting_text}"\n')
        
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
    configure_logging()
    parser = argparse.ArgumentParser(description="Process document chunks with an LLM to extract entities with supporting text")
    parser.add_argument("chunks_file", help="Path to JSON file with document chunks")
    parser.add_argument("--output-dir", default="data/processed", help="Directory to save output files")
    parser.add_argument("--entity-types", nargs="+", default=["event", "actor", "concept", "expression", "location"],
                        help="Entity types to extract")
    parser.add_argument("--no-relationships", action="store_true", help="Skip relationship extraction")
    parser.add_argument("--max-chunks", type=int, default=None, help="Maximum number of chunks to process")
    parser.add_argument("--chunk-index", type=int, default=None, help="Process only the chunk at this index (0-based)")
    parser.add_argument("--chunk-range", type=str, default=None, help="Process chunks in this range (e.g., '0-5')")
    parser.add_argument("--update-after-each", action="store_true", help="Write/update output files after each chunk is processed")
    parser.add_argument("--reverse", action="store_true", help="Process chunks in reverse order")
    parser.add_argument("--manual-mappings", type=str, default=None, help="Path to JSON file with manual entity mappings")
    parser.add_argument("--use-example-mappings", action="store_true", help="Use built-in example manual mappings")
    parser.add_argument("--no-disambiguation-report", action="store_true", help="Skip creating disambiguation report")
    parser.add_argument(
        "--backend", choices=["anthropic", "external"], default=None,
        help="LLM backend to use: 'anthropic' (default) or 'external' (AcademicCloud). "
             "Falls back to LLM_BACKEND env var, then 'anthropic'."
    )
    parser.add_argument(
        "--model", default=None,
        help="Model name to use (overrides KG_MODEL env var and per-backend default). "
             "External models: openai-gpt-oss-120b, qwen3-235b-a22b, glm-4.7"
    )
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

        if args.reverse:
            logger.info("Processing chunks in reverse order")
            chunks = list(reversed(chunks))
        
        try:
            from llm_client import create_llm_client
            client = create_llm_client(backend=args.backend, model=args.model)

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
