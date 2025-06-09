import json
import logging
import uuid
from typing import Dict, List, Optional, Any, Tuple
import time

# Configure logging
logger = logging.getLogger(__name__)

class KnowledgeGraphCritic:
    """
    Comprehensive critic system for evaluating extracted entities and relationships
    """
    
    def __init__(self, llm_client, critic_llm_client=None):
        """
        Initialize the critic system
        
        Args:
            llm_client: Client for the primary LLM
            critic_llm_client: Client for the critic LLM (optional)
        """
        self.llm_client = llm_client
        self.critic_llm_client = critic_llm_client or llm_client
        logger.info("Initialized KnowledgeGraphCritic")
    
    def evaluate_extraction_results(self, entities: Dict[str, List[Dict]], 
                                  relationships: List[Dict],
                                  chunks: List[Dict] = None,
                                  exclude_auto_created: bool = True) -> Dict:
        """
        Comprehensive evaluation of all extraction results
        
        Args:
            entities: Dictionary of entities by type
            relationships: List of relationships
            chunks: Original document chunks (optional, for context)
            exclude_auto_created: Whether to exclude auto-created entities from evaluation
            
        Returns:
            Comprehensive evaluation report
        """
        logger.info("Starting comprehensive evaluation of extraction results")
        
        # Filter entities if requested
        filtered_entities = self._filter_entities(entities, exclude_auto_created)
        
        # Evaluate entities
        entity_evaluations = self._evaluate_all_entities(filtered_entities, chunks)
        
        # Evaluate relationships
        relationship_evaluations = self._evaluate_all_relationships(relationships, entities, chunks)
        
        # Generate overall quality assessment
        overall_assessment = self._generate_overall_assessment(
            entity_evaluations, relationship_evaluations, filtered_entities, relationships
        )
        
        # Create human review tasks
        review_tasks = self._create_review_tasks(entity_evaluations, relationship_evaluations)
        
        return {
            "entity_evaluations": entity_evaluations,
            "relationship_evaluations": relationship_evaluations,
            "overall_assessment": overall_assessment,
            "review_tasks": review_tasks,
            "statistics": {
                "entities_evaluated": sum(len(evals) for evals in entity_evaluations.values()),
                "relationships_evaluated": len(relationship_evaluations),
                "entities_needing_review": sum(1 for evals in entity_evaluations.values() 
                                             for eval in evals if eval.get("human_review_recommended")),
                "relationships_needing_review": sum(1 for eval in relationship_evaluations 
                                                  if eval.get("human_review_recommended")),
                "high_quality_entities": sum(1 for evals in entity_evaluations.values() 
                                           for eval in evals if eval.get("extraction_quality") == "excellent"),
                "high_quality_relationships": sum(1 for eval in relationship_evaluations 
                                                if eval.get("extraction_quality") == "excellent")
            }
        }
    
    def _filter_entities(self, entities: Dict[str, List[Dict]], exclude_auto_created: bool) -> Dict[str, List[Dict]]:
        """Filter out auto-created entities if requested"""
        if not exclude_auto_created:
            return entities
        
        filtered = {}
        for entity_type, entity_list in entities.items():
            filtered[entity_type] = [
                entity for entity in entity_list 
                if not entity.get("auto_created_from_relationship", False)
            ]
        
        total_original = sum(len(entity_list) for entity_list in entities.values())
        total_filtered = sum(len(entity_list) for entity_list in filtered.values())
        logger.info(f"Filtered entities: {total_filtered}/{total_original} entities will be evaluated (excluding auto-created)")
        
        return filtered
    
    def _evaluate_all_entities(self, entities: Dict[str, List[Dict]], chunks: List[Dict] = None) -> Dict[str, List[Dict]]:
        """Evaluate all entities by type"""
        entity_evaluations = {}
        
        for entity_type, entity_list in entities.items():
            if not entity_list:
                entity_evaluations[entity_type] = []
                continue
                
            logger.info(f"Evaluating {len(entity_list)} {entity_type} entities")
            entity_evaluations[entity_type] = []
            
            for i, entity in enumerate(entity_list):
                logger.debug(f"Evaluating {entity_type} {i+1}/{len(entity_list)}")
                
                # Find supporting chunk if available
                supporting_chunk = self._find_supporting_chunk(entity, chunks)
                
                evaluation = self._evaluate_single_entity(entity, entity_type, supporting_chunk)
                evaluation["entity_id"] = entity.get("id")
                evaluation["entity_type"] = entity_type
                
                entity_evaluations[entity_type].append(evaluation)
                
                # Rate limiting
                time.sleep(0.3)
        
        return entity_evaluations
    
    def _evaluate_all_relationships(self, relationships: List[Dict], 
                                   entities: Dict[str, List[Dict]], 
                                   chunks: List[Dict] = None) -> List[Dict]:
        """Evaluate all relationships"""
        if not relationships:
            return []
            
        logger.info(f"Evaluating {len(relationships)} relationships")
        relationship_evaluations = []
        
        # Create entity lookup for context
        entity_lookup = {}
        for entity_type, entity_list in entities.items():
            for entity in entity_list:
                entity_lookup[entity.get("id")] = entity
        
        for i, relationship in enumerate(relationships):
            logger.debug(f"Evaluating relationship {i+1}/{len(relationships)}")
            
            # Find supporting chunk if available
            supporting_chunk = self._find_supporting_chunk(relationship, chunks)
            
            # Get entity context
            source_entity = entity_lookup.get(relationship.get("source_id"))
            target_entity = entity_lookup.get(relationship.get("target_id"))
            
            evaluation = self._evaluate_single_relationship(
                relationship, source_entity, target_entity, supporting_chunk
            )
            evaluation["relationship_id"] = relationship.get("id")
            
            relationship_evaluations.append(evaluation)
            
            # Rate limiting
            time.sleep(0.3)
        
        return relationship_evaluations
    
    def _evaluate_single_entity(self, entity: Dict, entity_type: str, supporting_chunk: Dict = None) -> Dict:
        """Evaluate a single entity using the critic LLM"""
        
        # Get entity name/title
        entity_name = entity.get("title" if entity_type == "event" else "name", "")
        
        # Prepare context
        chunk_text = supporting_chunk.get("text", "") if supporting_chunk else ""
        supporting_text = entity.get("supporting_text", "")
        
        critic_prompt = f"""
You are an expert reviewer of entity extraction for a planetary health knowledge graph.

Below is an extracted {entity_type.upper()} entity, along with the original text context and supporting text that was used for extraction.

EXTRACTED {entity_type.upper()}:
{json.dumps(entity, indent=2)}

ORIGINAL TEXT CONTEXT:
{chunk_text[:1000] + "..." if len(chunk_text) > 1000 else chunk_text}

SUPPORTING TEXT:
{supporting_text}

Please evaluate this {entity_type} extraction on the following criteria:

1. **Evidence**: Is there clear evidence for this {entity_type} in the provided text?
2. **Accuracy**: Are the extracted attributes (name, description, dates, etc.) accurate?
3. **Completeness**: Are all important attributes present and well-filled?
4. **Relevance**: Is this {entity_type} relevant to planetary health?
5. **Supporting Text Quality**: Does the supporting text actually support this extraction?
6. **Consistency**: Are the attributes internally consistent with each other?

For {entity_type}-specific evaluation:
{self._get_entity_specific_criteria(entity_type)}

Respond in the following JSON format:
{{
  "evaluation": {{
    "evidence_score": 1-5,
    "accuracy_score": 1-5,
    "completeness_score": 1-5,
    "relevance_score": 1-5,
    "supporting_text_score": 1-5,
    "consistency_score": 1-5,
    "overall_confidence": 1-5,
    "extraction_quality": "excellent|good|fair|poor",
    "issues_identified": [
      {{
        "issue_type": "evidence|accuracy|completeness|relevance|supporting_text|consistency",
        "description": "Specific description of the issue",
        "severity": 1-5,
        "suggested_correction": "suggested fix (if applicable)"
      }}
    ],
    "strengths": [
      "List of strengths in this extraction"
    ],
    "human_review_recommended": true|false,
    "human_review_reason": "Explanation if review is recommended",
    "confidence_explanation": "Why this confidence score was assigned"
  }}
}}
"""
        
        return self._call_critic_llm(critic_prompt, f"{entity_type} entity evaluation")
    
    def _evaluate_single_relationship(self, relationship: Dict, 
                                    source_entity: Dict = None, 
                                    target_entity: Dict = None,
                                    supporting_chunk: Dict = None) -> Dict:
        """Evaluate a single relationship using the critic LLM"""
        
        # Prepare context
        chunk_text = supporting_chunk.get("text", "") if supporting_chunk else ""
        
        # Entity context
        source_context = f"Source Entity: {json.dumps(source_entity, indent=2)}" if source_entity else "Source Entity: Not found"
        target_context = f"Target Entity: {json.dumps(target_entity, indent=2)}" if target_entity else "Target Entity: Not found"
        
        critic_prompt = f"""
You are an expert reviewer of relationship extraction for a planetary health knowledge graph.

Below is an extracted RELATIONSHIP, along with the entities it connects and the original text context.

EXTRACTED RELATIONSHIP:
{json.dumps(relationship, indent=2)}

{source_context}

{target_context}

ORIGINAL TEXT CONTEXT:
{chunk_text[:1000] + "..." if len(chunk_text) > 1000 else chunk_text}

Please evaluate this relationship extraction on the following criteria:

1. **Evidence**: Is there clear evidence for this relationship in the text?
2. **Entity Accuracy**: Are the source and target entities correctly identified?
3. **Relationship Type**: Is the relationship type appropriate and accurate?
4. **Direction**: Is the relationship direction correct (if applicable)?
5. **Strength**: Is the relationship strength rating appropriate (1-5)?
6. **Relevance**: Is this relationship relevant to planetary health?
7. **Entity Existence**: Do both entities actually exist and are they well-defined?

Respond in the following JSON format:
{{
  "evaluation": {{
    "evidence_score": 1-5,
    "entity_accuracy_score": 1-5,
    "relationship_type_score": 1-5,
    "direction_score": 1-5,
    "strength_score": 1-5,
    "relevance_score": 1-5,
    "entity_existence_score": 1-5,
    "overall_confidence": 1-5,
    "extraction_quality": "excellent|good|fair|poor",
    "issues_identified": [
      {{
        "issue_type": "evidence|entity_accuracy|relationship_type|direction|strength|relevance|entity_existence",
        "description": "Specific description of the issue",
        "severity": 1-5,
        "suggested_correction": "suggested fix (if applicable)"
      }}
    ],
    "strengths": [
      "List of strengths in this extraction"
    ],
    "human_review_recommended": true|false,
    "human_review_reason": "Explanation if review is recommended",
    "confidence_explanation": "Why this confidence score was assigned"
  }}
}}
"""
        
        return self._call_critic_llm(critic_prompt, "relationship evaluation")
    
    def _get_entity_specific_criteria(self, entity_type: str) -> str:
        """Get entity-type-specific evaluation criteria"""
        criteria = {
            "event": """
- Is the event title descriptive and accurate?
- Is the year plausible and consistent with the description?
- Is the event type classification appropriate?
- Is the significance rating (1-5) reasonable for this event's impact?
- Are associated locations, actors, and concepts relevant?
""",
            "actor": """
- Is the actor name correctly identified?
- Is the actor type (Individual, Institution, Government, NGO, etc.) accurate?
- Is the role in planetary health clearly defined and accurate?
- Are the expertise fields relevant to the actor's work?
- Is the country/location information accurate?
""",
            "concept": """
- Is the concept name clear and standard in the field?
- Is the definition accurate and complete?
- Are alternative names/synonyms correctly identified?
- Is the domain classification appropriate?
- Are related concepts actually related?
""",
            "publication": """
- Is the publication title accurate and complete?
- Is the publication type correctly classified?
- Are the authors correctly identified?
- Is the year plausible?
- Is the publisher/journal information accurate?
""",
            "location": """
- Is the location name correctly identified?
- Is the location type (Country, City, Region, etc.) accurate?
- Is the country information correct (if applicable)?
- Is the significance to planetary health clearly explained?
"""
        }
        return criteria.get(entity_type, "")
    
    def _call_critic_llm(self, prompt: str, task_description: str) -> Dict:
        """Call the critic LLM and parse the response"""
        try:
            response = self.critic_llm_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4000,
                system="You are a critical evaluator of knowledge graph extractions. Provide detailed, constructive evaluation with specific scores and actionable feedback.",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )

            content = response.content[0].text.strip()
            
            # Parse JSON response
            try:
                # Extract JSON from response
                if "```json" in content:
                    json_start = content.find("```json") + 7
                    json_end = content.find("```", json_start)
                    if json_end != -1:
                        content = content[json_start:json_end].strip()
                
                # Find JSON object
                json_start = content.find("{")
                json_end = content.rfind("}")
                if json_start != -1 and json_end != -1:
                    content = content[json_start:json_end+1]
                
                result = json.loads(content)
                return result.get("evaluation", {})
                
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse critic response for {task_description}: {str(e)}")
                return self._create_fallback_evaluation("Failed to parse critic response")
                
        except Exception as e:
            logger.error(f"Error calling critic LLM for {task_description}: {str(e)}")
            return self._create_fallback_evaluation(f"Error calling critic LLM: {str(e)}")
    
    def _create_fallback_evaluation(self, reason: str) -> Dict:
        """Create a fallback evaluation when critic fails"""
        return {
            "evidence_score": 1,
            "accuracy_score": 1,
            "completeness_score": 1,
            "relevance_score": 1,
            "overall_confidence": 1,
            "extraction_quality": "poor",
            "issues_identified": [
                {
                    "issue_type": "system",
                    "description": reason,
                    "severity": 5,
                    "suggested_correction": "Manual review required"
                }
            ],
            "human_review_recommended": True,
            "human_review_reason": reason,
            "confidence_explanation": "System error during evaluation"
        }
    
    def _find_supporting_chunk(self, item: Dict, chunks: List[Dict] = None) -> Optional[Dict]:
        """Find the supporting chunk for an entity or relationship"""
        if not chunks:
            return None
        
        source_chunk_id = item.get("source_chunk")
        if source_chunk_id is not None:
            # Try to find by index
            if isinstance(source_chunk_id, int) and 0 <= source_chunk_id < len(chunks):
                return chunks[source_chunk_id]
            
            # Try to find by chunk_id
            for chunk in chunks:
                if chunk.get("chunk_id") == source_chunk_id:
                    return chunk
        
        return None
    
    def _generate_overall_assessment(self, entity_evaluations: Dict[str, List[Dict]], 
                                   relationship_evaluations: List[Dict],
                                   entities: Dict[str, List[Dict]], 
                                   relationships: List[Dict]) -> Dict:
        """Generate an overall quality assessment of the extraction"""
        
        # Calculate entity statistics
        entity_stats = {}
        total_entities = 0
        total_entity_confidence = 0
        
        for entity_type, evaluations in entity_evaluations.items():
            if evaluations:
                confidences = [eval.get("overall_confidence", 1) for eval in evaluations]
                qualities = [eval.get("extraction_quality", "poor") for eval in evaluations]
                
                entity_stats[entity_type] = {
                    "count": len(evaluations),
                    "avg_confidence": sum(confidences) / len(confidences),
                    "quality_distribution": {
                        "excellent": qualities.count("excellent"),
                        "good": qualities.count("good"), 
                        "fair": qualities.count("fair"),
                        "poor": qualities.count("poor")
                    }
                }
                
                total_entities += len(evaluations)
                total_entity_confidence += sum(confidences)
        
        # Calculate relationship statistics
        rel_confidences = [eval.get("overall_confidence", 1) for eval in relationship_evaluations]
        rel_qualities = [eval.get("extraction_quality", "poor") for eval in relationship_evaluations]
        
        relationship_stats = {
            "count": len(relationship_evaluations),
            "avg_confidence": sum(rel_confidences) / len(rel_confidences) if rel_confidences else 0,
            "quality_distribution": {
                "excellent": rel_qualities.count("excellent"),
                "good": rel_qualities.count("good"),
                "fair": rel_qualities.count("fair"), 
                "poor": rel_qualities.count("poor")
            }
        }
        
        # Overall assessment
        total_items = total_entities + len(relationship_evaluations)
        overall_confidence = (total_entity_confidence + sum(rel_confidences)) / total_items if total_items > 0 else 0
        
        return {
            "entity_statistics": entity_stats,
            "relationship_statistics": relationship_stats,
            "overall_confidence": overall_confidence,
            "quality_summary": {
                "total_items_evaluated": total_items,
                "high_quality_items": sum(stats.get("quality_distribution", {}).get("excellent", 0) for stats in entity_stats.values()) + rel_qualities.count("excellent"),
                "items_needing_review": sum(1 for evals in entity_evaluations.values() for eval in evals if eval.get("human_review_recommended")) + sum(1 for eval in relationship_evaluations if eval.get("human_review_recommended")),
                "avg_confidence": overall_confidence
            },
            "recommendations": self._generate_recommendations(entity_stats, relationship_stats, overall_confidence)
        }
    
    def _generate_recommendations(self, entity_stats: Dict, relationship_stats: Dict, overall_confidence: float) -> List[str]:
        """Generate recommendations based on the evaluation results"""
        recommendations = []
        
        if overall_confidence < 3.0:
            recommendations.append("Overall extraction quality is low. Consider reviewing extraction prompts and methodology.")
        
        if relationship_stats.get("avg_confidence", 0) < 2.5:
            recommendations.append("Relationship extraction quality is particularly low. Review relationship extraction criteria.")
        
        for entity_type, stats in entity_stats.items():
            if stats.get("avg_confidence", 0) < 2.5:
                recommendations.append(f"{entity_type.title()} entity extraction needs improvement.")
            
            poor_ratio = stats.get("quality_distribution", {}).get("poor", 0) / stats.get("count", 1)
            if poor_ratio > 0.3:
                recommendations.append(f"High proportion of poor quality {entity_type} entities ({poor_ratio:.1%}). Review extraction criteria.")
        
        if not recommendations:
            recommendations.append("Extraction quality is acceptable. Consider spot-checking flagged items.")
        
        return recommendations
    
    def _create_review_tasks(self, entity_evaluations: Dict[str, List[Dict]], 
                           relationship_evaluations: List[Dict]) -> List[Dict]:
        """Create human review tasks based on critic evaluations"""
        review_tasks = []
        
        # Entity review tasks
        for entity_type, evaluations in entity_evaluations.items():
            for eval in evaluations:
                if eval.get("human_review_recommended"):
                    task = {
                        "id": str(uuid.uuid4()),
                        "type": "entity_review",
                        "entity_type": entity_type,
                        "entity_id": eval.get("entity_id"),
                        "priority": self._calculate_priority(eval),
                        "reason": eval.get("human_review_reason", "Quality concerns"),
                        "confidence": eval.get("overall_confidence", 1),
                        "quality": eval.get("extraction_quality", "poor"),
                        "issues": eval.get("issues_identified", []),
                        "created_at": time.time()
                    }
                    review_tasks.append(task)
        
        # Relationship review tasks
        for eval in relationship_evaluations:
            if eval.get("human_review_recommended"):
                task = {
                    "id": str(uuid.uuid4()),
                    "type": "relationship_review", 
                    "relationship_id": eval.get("relationship_id"),
                    "priority": self._calculate_priority(eval),
                    "reason": eval.get("human_review_reason", "Quality concerns"),
                    "confidence": eval.get("overall_confidence", 1),
                    "quality": eval.get("extraction_quality", "poor"),
                    "issues": eval.get("issues_identified", []),
                    "created_at": time.time()
                }
                review_tasks.append(task)
        
        # Sort by priority (higher priority first)
        review_tasks.sort(key=lambda x: x["priority"], reverse=True)
        
        return review_tasks
    
    def _calculate_priority(self, evaluation: Dict) -> int:
        """Calculate priority for review tasks based on evaluation"""
        confidence = evaluation.get("overall_confidence", 1)
        quality = evaluation.get("extraction_quality", "poor")
        
        # Base priority on confidence (lower confidence = higher priority)
        priority = 6 - confidence
        
        # Adjust based on quality
        quality_bonus = {
            "poor": 3,
            "fair": 1,
            "good": 0,
            "excellent": -1
        }
        priority += quality_bonus.get(quality, 0)
        
        # Adjust based on issues
        high_severity_issues = sum(1 for issue in evaluation.get("issues_identified", []) 
                                 if issue.get("severity", 1) >= 4)
        priority += high_severity_issues
        
        return max(1, min(10, int(priority)))  # Clamp between 1-10

def save_critic_results(results: Dict, output_dir: str, base_filename: str) -> Dict[str, str]:
    """Save critic evaluation results to files"""
    import os
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Save complete results
    complete_path = os.path.join(output_dir, f"{base_filename}_critic_evaluation.json")
    with open(complete_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    # Save review tasks
    tasks_path = os.path.join(output_dir, f"{base_filename}_review_tasks.json") 
    with open(tasks_path, 'w', encoding='utf-8') as f:
        json.dump({"review_tasks": results["review_tasks"]}, f, indent=2, ensure_ascii=False)
    
    # Save summary report
    summary_path = os.path.join(output_dir, f"{base_filename}_quality_report.json")
    summary = {
        "overall_assessment": results["overall_assessment"],
        "statistics": results["statistics"]
    }
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    return {
        "complete_evaluation": complete_path,
        "review_tasks": tasks_path,
        "quality_report": summary_path
    }