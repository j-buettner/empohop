#!/usr/bin/env python3
"""
Consolidate human review changes into the main knowledge graph.

This script:
1. Loads the main knowledge graph
2. Loads all corrected data from individual review files
3. Updates the entities and relationships in the knowledge graph with the corrected versions
4. Adds metadata about the review process
5. Saves the updated knowledge graph to a new file with a version number
"""

import argparse
import json
import logging
import os
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
from logging_config import configure_logging

logger = logging.getLogger(__name__)

class KnowledgeGraphConsolidator:
    """Class for consolidating human review changes into the main knowledge graph"""
    
    def __init__(self, knowledge_graph_file: str, review_dir: str, output_file: Optional[str] = None):
        """
        Initialize the consolidator
        
        Args:
            knowledge_graph_file: Path to the main knowledge graph file
            review_dir: Directory containing the corrected data files
            output_file: Path to save the updated knowledge graph (if None, will generate a versioned filename)
        """
        self.knowledge_graph_file = knowledge_graph_file
        self.review_dir = review_dir
        self.output_file = output_file
        
        # Initialize data structures
        self.knowledge_graph = {}
        self.corrected_data = {
            "events": [],
            "actors": [],
            "concepts": [],
            "locations": [],
            "publications": [],
            "relationships": []
        }
        self.review_history = []
        
    def load_knowledge_graph(self):
        """Load the main knowledge graph"""
        try:
            with open(self.knowledge_graph_file, 'r', encoding='utf-8') as f:
                self.knowledge_graph = json.load(f)
                
            logger.info(f"Loaded knowledge graph from {self.knowledge_graph_file}")
            
            # Log entity counts
            for entity_type, entities in self.knowledge_graph.items():
                if isinstance(entities, list):
                    logger.info(f"  {entity_type}: {len(entities)} entities")
                
        except Exception as e:
            logger.error(f"Error loading knowledge graph: {str(e)}")
            raise
    
    def load_corrected_data(self):
        """Load all corrected data from individual review files"""
        try:
            # Check if the review directory exists
            if not os.path.isdir(self.review_dir):
                logger.error(f"Review directory not found: {self.review_dir}")
                return
            
            # Get all corrected data files
            corrected_files = [f for f in os.listdir(self.review_dir) if f.startswith("corrected_") and f.endswith(".json")]
            
            if not corrected_files:
                logger.warning(f"No corrected data files found in {self.review_dir}")
                return
            
            logger.info(f"Found {len(corrected_files)} corrected data files")
            
            # Load each corrected data file
            for file_name in corrected_files:
                file_path = os.path.join(self.review_dir, file_name)
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        
                    # Extract corrected data
                    corrected_data = data.get("corrected_data", {})
                    
                    # Extract entities
                    entities = corrected_data.get("entities", {})
                    for entity_type, entity_list in entities.items():
                        # Map entity type to the corresponding key in the knowledge graph
                        kg_entity_type = self._map_entity_type(entity_type)
                        
                        if kg_entity_type in self.corrected_data:
                            self.corrected_data[kg_entity_type].extend(entity_list)
                    
                    # Extract relationships
                    relationships = corrected_data.get("relationships", [])
                    self.corrected_data["relationships"].extend(relationships)
                    
                    # Add to review history
                    self.review_history.append({
                        "task_id": data.get("task_id", ""),
                        "reviewer_notes": data.get("reviewer_notes", ""),
                        "original_data": data.get("original_data", {}),
                        "corrected_data": corrected_data,
                        "timestamp": data.get("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
                    })
                    
                except Exception as e:
                    logger.error(f"Error loading corrected data from {file_path}: {str(e)}")
                    continue
            
            # Log corrected entity counts
            for entity_type, entities in self.corrected_data.items():
                logger.info(f"  {entity_type}: {len(entities)} corrected entities")
                
        except Exception as e:
            logger.error(f"Error loading corrected data: {str(e)}")
            raise
    
    def _map_entity_type(self, entity_type: str) -> str:
        """
        Map entity type to the corresponding key in the knowledge graph
        
        Args:
            entity_type: Entity type from the corrected data
            
        Returns:
            Corresponding key in the knowledge graph
        """
        # Map singular to plural
        entity_type_map = {
            "event": "events",
            "actor": "actors",
            "concept": "concepts",
            "location": "locations",
            "publication": "publications",
            "relationship": "relationships"
        }
        
        return entity_type_map.get(entity_type, entity_type)
    
    def update_knowledge_graph(self):
        """Update the knowledge graph with the corrected data"""
        try:
            # Track the number of updates
            update_counts = {
                "events": 0,
                "actors": 0,
                "concepts": 0,
                "locations": 0,
                "publications": 0,
                "relationships": 0
            }
            
            # Update each entity type
            for entity_type, corrected_entities in self.corrected_data.items():
                if not corrected_entities:
                    continue
                
                # Skip if the entity type is not in the knowledge graph
                if entity_type not in self.knowledge_graph:
                    logger.warning(f"Entity type {entity_type} not found in knowledge graph")
                    continue
                
                # Get the entities from the knowledge graph
                kg_entities = self.knowledge_graph[entity_type]
                
                # Update each corrected entity
                for corrected_entity in corrected_entities:
                    # Skip if the entity doesn't have an ID
                    if "id" not in corrected_entity:
                        logger.warning(f"Corrected entity missing ID: {corrected_entity}")
                        continue
                    
                    # Find the entity in the knowledge graph
                    entity_id = corrected_entity["id"]
                    found = False
                    
                    for i, kg_entity in enumerate(kg_entities):
                        if kg_entity.get("id") == entity_id:
                            # Add review metadata
                            corrected_entity["_review_metadata"] = {
                                "reviewed": True,
                                "reviewed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                "previous_version": kg_entity
                            }
                            
                            # Update the entity
                            kg_entities[i] = corrected_entity
                            found = True
                            update_counts[entity_type] += 1
                            break
                    
                    if not found:
                        logger.warning(f"Entity {entity_id} not found in knowledge graph")
            
            # Log update counts
            for entity_type, count in update_counts.items():
                logger.info(f"  {entity_type}: {count} entities updated")
                
        except Exception as e:
            logger.error(f"Error updating knowledge graph: {str(e)}")
            raise
    
    def save_updated_knowledge_graph(self):
        """Save the updated knowledge graph"""
        try:
            # Generate output file name if not provided
            if not self.output_file:
                # Extract the base name from the input file
                base_name = os.path.basename(self.knowledge_graph_file)
                name_parts = os.path.splitext(base_name)
                
                # Add version and timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                self.output_file = f"{name_parts[0]}_reviewed_{timestamp}{name_parts[1]}"
                
                # Add the directory
                self.output_file = os.path.join(os.path.dirname(self.knowledge_graph_file), self.output_file)
            
            # Add metadata to the knowledge graph
            self.knowledge_graph["_metadata"] = {
                "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "review_count": len(self.review_history),
                "source_file": os.path.basename(self.knowledge_graph_file)
            }
            
            # Save the updated knowledge graph
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(self.knowledge_graph, f, indent=2)
                
            logger.info(f"Saved updated knowledge graph to {self.output_file}")
            
            # Save the review history
            history_file = f"{os.path.splitext(self.output_file)[0]}_review_history.json"
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "review_history": self.review_history,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                }, f, indent=2)
                
            logger.info(f"Saved review history to {history_file}")
            
        except Exception as e:
            logger.error(f"Error saving updated knowledge graph: {str(e)}")
            raise
    
    def consolidate(self):
        """Consolidate the human review changes into the main knowledge graph"""
        try:
            # Load the knowledge graph
            self.load_knowledge_graph()
            
            # Load the corrected data
            self.load_corrected_data()
            
            # Update the knowledge graph
            self.update_knowledge_graph()
            
            # Save the updated knowledge graph
            self.save_updated_knowledge_graph()
            
            return self.output_file
            
        except Exception as e:
            logger.error(f"Error consolidating human review changes: {str(e)}")
            return None


def main():
    """Main function"""
    configure_logging()
    parser = argparse.ArgumentParser(description='Consolidate human review changes into the main knowledge graph')
    parser.add_argument('--kg', type=str, default='data/processed/book_9780262366601-compressed_knowledge_graph.json',
                        help='Path to the main knowledge graph file')
    parser.add_argument('--review', type=str, default='data/review',
                        help='Directory containing the corrected data files')
    parser.add_argument('--output', type=str, default=None,
                        help='Path to save the updated knowledge graph (if not provided, will generate a versioned filename)')
    args = parser.parse_args()
    
    # Create the consolidator
    consolidator = KnowledgeGraphConsolidator(args.kg, args.review, args.output)
    
    # Consolidate the changes
    output_file = consolidator.consolidate()
    
    if output_file:
        print(f"Successfully consolidated human review changes into {output_file}")
    else:
        print("Failed to consolidate human review changes")


if __name__ == "__main__":
    main()
