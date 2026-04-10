import json
import logging
import uuid
from typing import Dict, List, Optional, Any
import time
from config import MAX_TOKENS, CONTEXT_SENTENCE, CONTEXT_PHRASE
from extraction_utils import retry_api_call

# Configure logging
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Relation extraction prompt (6th pass — receives items extracted in passes 1-5)
# ---------------------------------------------------------------------------

RELATION_EXTRACTION_PROMPT = f"""
{CONTEXT_SENTENCE}

Identify RELATIONS explicitly evidenced in the text between the extracted items: EVENTS, ACTORS, EXPRESSIONS, CONCEPTS, and LOCATIONS.

A relation is defined as a stated or suggested linkage between items, supported by an exact excerpt.

Rules:
- Cue words are hints, not triggers. Do not extract a relation unless the text clearly links two specific items and you can quote supporting_text.
- Do NOT invent new items. source_id and target_id MUST be IDs that exist in the items table.
- If the relation is directly stated, modality="asserted". If hedged, modality="suggested". If disputed, modality="contested".
- Use directional relations whenever one item acts on/produces/defines/recommends another.
- Assign each relation a unique relation_id in the format "R1", "R2", ... in the order listed.
- If an optional field is not applicable, use null.
- Focus only on relations that are DIRECTLY AND CLEARLY evidenced in the text with an exact quote. Skip weak inferences. Extract at most 20 of the most important relations.

For each relation, provide:
1. relation_id (required)
2. relation_category (required):
   - "associative": linkage via inspiration, influence, framing, momentum, or encouragement — without a clearly described mechanism
   - "intervening": linkage that produces an effect through coordination, resource allocation, formal decision, implementation, or enforcement
3. directionality: "A_to_B", "B_to_A", "bidirectional", or "unclear"
4. modality: "asserted", "suggested", or "contested"
5. polarity: "enabling", "undermining", or "neutral"
6. relation_type (required), e.g.:
   - "involved_in"            (Actor -> Event)
   - "led_by"                 (Event -> Actor)
   - "funded_by"              (Event -> Actor)
   - "published_by"           (Expression -> Actor)
   - "adopted_by"             (Expression -> Actor)
   - "calls_on"               (Actor/Expression -> Actor)
   - "recommends_to"          (Expression/Event -> Actor)
   - "informed_by"            (Event -> Expression/Actor)
   - "based_on"               (Expression -> Expression/Concept)
   - "revises_or_updates"     (Expression -> Expression)
   - "defines"                (Expression -> Concept)
   - "applies_to"             (Concept/Expression -> Location)
   - "associated_with"        (any <-> any; use only if none above fit)
   - "other"                  (explain in short_relation_label)
7. short_relation_label: 1–5 words describing the relation (e.g., "funded", "adopted by", "defines concept")
8. source_id — UUID of the source item from items_json
9. target_id — UUID of the target item from items_json
10. supporting_text (required) — exact excerpt from the text

Text to analyze:
{{text}}

Extracted items to link — format: id | type | name
Type codes: E=event  A=actor  X=expression  C=concept  L=location
Use IDs exactly as given — do not invent new ones.
{{items_table}}

Respond in the following JSON format:
{{{{
  "relations": [
    {{{{
      "relation_id": "R1",
      "relation_category": "associative|intervening",
      "directionality": "A_to_B|B_to_A|bidirectional|unclear",
      "modality": "asserted|suggested|contested",
      "polarity": "enabling|undermining|neutral",
      "relation_type": "",
      "short_relation_label": "",
      "source_id": "",
      "target_id": "",
      "supporting_text": ""
    }}}}
  ]
}}}}
"""

# ---------------------------------------------------------------------------
# Significance attribution prompt (7th pass — receives items + relations)
# ---------------------------------------------------------------------------

_SIGNIFICANCE_CATEGORY_DEFINITIONS = {
    "exposing_prevailing_condition": (
        "Highlights prevailing economic/political processes or interests that perpetuate "
        "disharmony with nature (diagnostic or critical role)."
    ),
    "revealing_potential_for_system_change": (
        "Reveals interdependencies, cross-scale dynamics, or the potential for non-linear "
        "shifts in system dynamics towards living in harmony with nature."
    ),
    "fostering_collective_action": (
        "Builds or enables human agency, values, coordination, resource allocation, or "
        "implementation capacity to advance the initiative."
    ),
    "impacting_salience_and_social_acceptance": (
        "Shifts discourse, political relevance, legitimacy, or broad social acceptance "
        "for changes towards living in harmony with nature."
    ),
    "undermining_changes_and_progress": (
        "Weakens, delays, reverses, or delegitimizes progress — intended or unintended."
    ),
    "unclear": (
        "The text does not provide enough basis to classify significance."
    ),
}

SIGNIFICANCE_ATTRIBUTION_PROMPT = f"""
{CONTEXT_SENTENCE}

For each extracted ITEM and each extracted RELATION provided below, attribute one significance category based on the following definition:

Item/relation significance is defined as the degree to which an item or relation, in itself or through its interaction with other items, contributes to improvement or advancement of an initiative towards living in harmony with nature (quantitatively or qualitatively).

Significance categories (choose ONE per item/relation):
- exposing_prevailing_condition: {_SIGNIFICANCE_CATEGORY_DEFINITIONS["exposing_prevailing_condition"]}
- revealing_potential_for_system_change: {_SIGNIFICANCE_CATEGORY_DEFINITIONS["revealing_potential_for_system_change"]}
- fostering_collective_action: {_SIGNIFICANCE_CATEGORY_DEFINITIONS["fostering_collective_action"]}
- impacting_salience_and_social_acceptance: {_SIGNIFICANCE_CATEGORY_DEFINITIONS["impacting_salience_and_social_acceptance"]}
- undermining_changes_and_progress: {_SIGNIFICANCE_CATEGORY_DEFINITIONS["undermining_changes_and_progress"]}
- unclear: {_SIGNIFICANCE_CATEGORY_DEFINITIONS["unclear"]}

Rules:
- Do not infer significance that is not supported by the text.
- If significance is unclear or not supported, choose "unclear" and briefly explain why in justification.
- Do not invent items or relations. Reference ONLY id values provided in items_json and relations_json.
- ID integrity (ITEMS): For each item_significance entry, id MUST exist in the items table AND name MUST exactly match the name column.
- ID integrity (RELATIONS): For each relation_significance entry, id MUST exist in relations_json.
- Keep justification concise (1–2 sentences). Keep supporting_text short (under 30 words).

Text to analyze:
{{text}}

Extracted items to attribute significance to — format: id | type | name
Type codes: E=event  A=actor  X=expression  C=concept  L=location
{{items_table}}

Extracted relations to attribute significance to:
{{relations_json}}

Respond in the following JSON format:
{{{{
  "item_significance": [
    {{{{
      "item_type": "event|actor|expression|concept|location",
      "id": "",
      "name": "",
      "primary_category": "exposing_prevailing_condition|revealing_potential_for_system_change|fostering_collective_action|impacting_salience_and_social_acceptance|undermining_changes_and_progress|unclear",
      "justification": "",
      "supporting_text": "Exact excerpt supporting the significance claim"
    }}}}
  ],
  "relation_significance": [
    {{{{
      "id": "",
      "primary_category": "exposing_prevailing_condition|revealing_potential_for_system_change|fostering_collective_action|impacting_salience_and_social_acceptance|undermining_changes_and_progress|unclear",
      "justification": "",
      "supporting_text": "Exact excerpt supporting the significance claim"
    }}}}
  ]
}}}}
"""

class RelationshipProcessor:
    """
    Handles extraction and processing of relations between entities (6th pass).
    Relations are extracted per-chunk using the already-extracted items as input,
    so no fuzzy name matching or entity creation is needed.
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client
        logger.info("Initialized RelationshipProcessor")

    def extract_relations_from_chunk(self, chunk: Dict, items: List[Dict]) -> List[Dict]:
        """
        Extract relations from a single chunk given the already-extracted items.

        Args:
            chunk: Document chunk with text and metadata
            items: List of item dicts, each with id (UUID), item_type, and name

        Returns:
            List of raw relation dicts with source/target item_ids and UUIDs
        """
        if not items:
            return []

        chunk_text = chunk.get("text", "")
        items_table = self._items_to_table(items)

        try:
            prompt = RELATION_EXTRACTION_PROMPT.format(text=chunk_text, items_table=items_table)
        except KeyError as e:
            logger.error("Error formatting relation prompt: %s", e)
            return []

        try:
            response = retry_api_call(
                self.llm_client.messages.create,
                model=self.llm_client.model,
                max_tokens=MAX_TOKENS,
                system=(
                    "You are an expert knowledge graph builder specialising in eco-jurisprudence "
                    "and the planetary health movement. Extract relations between the provided items "
                    "only — do not invent new items."
                ),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )

            content = response.content[0].text.strip()
            content = self._extract_json(content)

            result = json.loads(content)
            raw_relations = result.get("relations", [])

            # Build lookup: UUID → item metadata for programmatic enrichment
            item_lookup = {item["id"]: item for item in items}

            relations = []
            for rel in raw_relations:
                if not isinstance(rel, dict):
                    continue

                src_id = rel.get("source_id", "")
                tgt_id = rel.get("target_id", "")

                if src_id not in item_lookup or tgt_id not in item_lookup:
                    logger.warning(
                        "Skipping relation %s — UUID not in chunk items: src=%s tgt=%s",
                        rel.get("relation_id"), src_id, tgt_id
                    )
                    continue

                src = item_lookup[src_id]
                tgt = item_lookup[tgt_id]

                relations.append({
                    "id": str(uuid.uuid4()),
                    "source_id": src_id,
                    "source_type": src.get("item_type", ""),
                    "source_name": src.get("name", ""),
                    "target_id": tgt_id,
                    "target_type": tgt.get("item_type", ""),
                    "target_name": tgt.get("name", ""),
                    "relation_type": rel.get("relation_type", ""),
                    "relation_category": rel.get("relation_category", ""),
                    "directionality": rel.get("directionality", ""),
                    "modality": rel.get("modality", ""),
                    "polarity": rel.get("polarity", ""),
                    "short_relation_label": rel.get("short_relation_label", ""),
                    "supporting_text": rel.get("supporting_text", ""),
                    "source_chunk": chunk.get("chunk_id", chunk.get("source_chunk")),
                })

            logger.info("Extracted %d relations from chunk", len(relations))
            return relations

        except json.JSONDecodeError as e:
            logger.warning("Failed to parse relation extraction response as JSON: %s", e)
            logger.debug("Raw relation response (first 500 chars): %r", content[:500])
            return []
        except Exception as e:
            logger.error("Error extracting relations from chunk: %s", e)
            return []

    def remap_relation_uuids(self, relations: List[Dict], uuid_map: Dict[str, str]) -> List[Dict]:
        """
        Update source_id and target_id in relations to point to canonical UUIDs
        after global entity resolution (which may have merged duplicates).

        Args:
            relations: List of relation dicts with source_id/target_id
            uuid_map: Mapping {original_uuid: canonical_uuid}

        Returns:
            Relations with remapped UUIDs; relations whose endpoints can't be
            resolved are dropped with a warning.
        """
        remapped = []
        for rel in relations:
            src = uuid_map.get(rel["source_id"], rel["source_id"])
            tgt = uuid_map.get(rel["target_id"], rel["target_id"])
            remapped.append({**rel, "source_id": src, "target_id": tgt})
        return remapped

    def deduplicate_relationships(self, relationships: List[Dict]) -> List[Dict]:
        """Remove duplicate relations based on source_id, target_id, and relation_type."""
        seen = set()
        deduplicated = []
        for rel in relationships:
            key = (rel.get("source_id", ""), rel.get("target_id", ""), rel.get("relation_type", ""))
            if key not in seen:
                seen.add(key)
                deduplicated.append(rel)
            else:
                logger.debug("Skipping duplicate relation: %s", key)
        logger.info("Deduplicated relations: %d/%d kept", len(deduplicated), len(relationships))
        return deduplicated

    # Items are batched for the significance pass to stay within model output limits.
    # All relations are kept in every batch so the model has full relational context.
    # Relation significances are deduplicated across batches (first occurrence wins).
    _SIG_ITEM_BATCH_SIZE = 15

    def extract_significance_from_chunk(
        self, chunk: Dict, items: List[Dict], relations: List[Dict]
    ) -> Dict[str, List[Dict]]:
        """
        7th pass: attribute significance to items and relations from a single chunk.

        Items are processed in batches of _SIG_ITEM_BATCH_SIZE.  All relations are
        included in every batch so the model has complete relational context.
        Relation significances are deduplicated across batches (first occurrence wins).

        Args:
            chunk: Document chunk with text
            items: List of {id, item_type, name} dicts for this chunk
            relations: List of relation dicts extracted from this chunk (with id field)

        Returns:
            Dict with "item_significance" and "relation_significance" lists
        """
        if not items:
            return {"item_significance": [], "relation_significance": []}

        # Slim down relations to just id + label for the prompt
        relations_slim = [
            {
                "id": r["id"],
                "source_name": r.get("source_name", ""),
                "target_name": r.get("target_name", ""),
                "relation_type": r.get("relation_type", ""),
            }
            for r in relations
        ]

        item_batches = [
            items[start : start + self._SIG_ITEM_BATCH_SIZE]
            for start in range(0, len(items), self._SIG_ITEM_BATCH_SIZE)
        ]

        if len(item_batches) > 1:
            logger.info(
                "  Splitting %d items into %d batches for significance attribution",
                len(items), len(item_batches),
            )

        all_item_sig: List[Dict] = []
        seen_rel_ids: set = set()
        all_rel_sig: List[Dict] = []

        valid_relation_uuids = {r["id"] for r in relations}

        for idx, batch in enumerate(item_batches):
            if len(item_batches) > 1:
                logger.info(
                    "  Significance batch %d/%d (%d items)", idx + 1, len(item_batches), len(batch)
                )

            items_table = self._items_to_table(batch)
            relations_json = json.dumps(relations_slim, ensure_ascii=False)

            try:
                prompt = SIGNIFICANCE_ATTRIBUTION_PROMPT.format(
                    text=chunk.get("text", ""),
                    items_table=items_table,
                    relations_json=relations_json,
                )
            except KeyError as e:
                logger.error("Error formatting significance prompt: %s", e)
                continue

            try:
                response = retry_api_call(
                    self.llm_client.messages.create,
                    model=self.llm_client.model,
                    max_tokens=MAX_TOKENS,
                    system=(
                        "You are an expert knowledge graph builder specialising in eco-jurisprudence "
                        "and the planetary health movement. Attribute significance only where clearly "
                        "supported by the text."
                    ),
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                )

                content = self._extract_json(response.content[0].text.strip())
                result = json.loads(content)

                valid_item_uuids = {item["id"] for item in batch}

                item_sig = [
                    s for s in result.get("item_significance", [])
                    if isinstance(s, dict) and s.get("id") in valid_item_uuids
                ]
                all_item_sig.extend(item_sig)

                for rs in result.get("relation_significance", []):
                    if isinstance(rs, dict) and rs.get("id") in valid_relation_uuids:
                        if rs["id"] not in seen_rel_ids:
                            seen_rel_ids.add(rs["id"])
                            all_rel_sig.append(rs)

                logger.info(
                    "Significance: %d item entries, %d relation entries from batch",
                    len(item_sig), len([rs for rs in result.get("relation_significance", [])
                                        if isinstance(rs, dict) and rs.get("id") in valid_relation_uuids])
                )

            except json.JSONDecodeError as e:
                logger.warning("Failed to parse significance response as JSON: %s", e)
            except Exception as e:
                logger.error("Error extracting significance from chunk: %s", e)

        logger.info(
            "Significance total: %d item entries, %d relation entries from chunk",
            len(all_item_sig), len(all_rel_sig),
        )
        return {"item_significance": all_item_sig, "relation_significance": all_rel_sig}

    def remap_significance_uuids(
        self, significance: Dict[str, List[Dict]], uuid_map: Dict[str, str]
    ) -> Dict[str, List[Dict]]:
        """
        Update item and relation UUIDs in significance data after global entity resolution.

        Args:
            significance: Dict with "item_significance" and "relation_significance"
            uuid_map: Mapping {original_uuid: canonical_uuid}

        Returns:
            Significance data with remapped UUIDs
        """
        item_sig = [
            {**s, "id": uuid_map.get(s["id"], s["id"])}
            for s in significance.get("item_significance", [])
        ]
        rel_sig = [
            {**s, "id": uuid_map.get(s["id"], s["id"])}
            for s in significance.get("relation_significance", [])
        ]
        return {"item_significance": item_sig, "relation_significance": rel_sig}

    _TYPE_CODE = {"event": "E", "actor": "A", "expression": "X", "concept": "C", "location": "L"}

    @staticmethod
    def _items_to_table(items: List[Dict]) -> str:
        """
        Convert items list to a compact pipe-delimited table.
        Each row: <uuid> | <type-code> | <name>
        Saves ~40% tokens compared to JSON key-value format.
        """
        codes = RelationshipProcessor._TYPE_CODE
        return "\n".join(
            f"{item['id']} | {codes.get(item.get('item_type', ''), '?')} | {item.get('name', '')}"
            for item in items
        )

    @staticmethod
    def _extract_json(content: str) -> str:
        """Strip markdown code fences and find the outermost JSON object."""
        if "```json" in content:
            s = content.find("```json") + 7
            e = content.find("```", s)
            if e != -1:
                content = content[s:e].strip()
        elif "```" in content:
            s = content.find("```") + 3
            e = content.find("```", s)
            if e != -1:
                content = content[s:e].strip()
        s = content.find("{")
        e = content.rfind("}")
        if s != -1 and e != -1 and e > s:
            content = content[s:e + 1]
        return content
