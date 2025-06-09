#!/usr/bin/env python3
"""
Command-line interface for running the Knowledge Graph Critic system
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from critic import KnowledgeGraphCritic, save_critic_results

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_extraction_results(kg_file: str) -> tuple:
    """
    Load extraction results from a knowledge graph file
    
    Args:
        kg_file: Path to the knowledge graph JSON file
        
    Returns:
        Tuple of (entities_dict, relationships_list)
    """
    try:
        with open(kg_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Extract entities by type
        entities = {}
        for key, value in data.items():
            if key.endswith('s') and key != 'relationships' and isinstance(value, list):
                entity_type = key[:-1]  # Remove 's' suffix
                entities[entity_type] = value
        
        # Extract relationships
        relationships = data.get('relationships', [])
        
        logger.info(f"Loaded extraction results:")
        for entity_type, entity_list in entities.items():
            logger.info(f"  - {entity_type.capitalize()}s: {len(entity_list)}")
        logger.info(f"  - Relationships: {len(relationships)}")
        
        return entities, relationships
        
    except Exception as e:
        logger.error(f"Error loading extraction results from {kg_file}: {str(e)}")
        raise

def load_chunks(chunks_file: str) -> list:
    """
    Load document chunks for context (optional)
    
    Args:
        chunks_file: Path to the chunks JSON file
        
    Returns:
        List of document chunks
    """
    try:
        with open(chunks_file, 'r', encoding='utf-8') as f:
            chunks_data = json.load(f)
        
        # Extract chunks from the loaded data
        if isinstance(chunks_data, list):
            chunks = chunks_data
        else:
            chunks = chunks_data.get("chunks", [])
        
        logger.info(f"Loaded {len(chunks)} document chunks for context")
        return chunks
        
    except Exception as e:
        logger.warning(f"Could not load chunks from {chunks_file}: {str(e)}")
        return []

def main():
    """Main function for running the critic system"""
    parser = argparse.ArgumentParser(
        description="Evaluate extracted knowledge graph entities and relationships using the KnowledgeGraphCritic",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic evaluation of a knowledge graph file
  python run_critic.py data/processed/document_knowledge_graph.json
  
  # Evaluation with document chunks for context
  python run_critic.py data/processed/document_knowledge_graph.json --chunks data/processed/document_chunks.json
  
  # Include auto-created entities in evaluation
  python run_critic.py data/processed/document_knowledge_graph.json --include-auto-created
  
  # Use a different LLM model for criticism
  python run_critic.py data/processed/document_knowledge_graph.json --critic-model claude-3-opus-20240229
  
  # Custom output directory and filename
  python run_critic.py data/processed/document_knowledge_graph.json --output-dir results --output-name my_evaluation
        """
    )
    
    # Required arguments
    parser.add_argument(
        "knowledge_graph_file", 
        help="Path to the knowledge graph JSON file containing extracted entities and relationships"
    )
    
    # Optional arguments
    parser.add_argument(
        "--chunks", 
        help="Path to the document chunks JSON file (for additional context)"
    )
    
    parser.add_argument(
        "--output-dir", 
        default="data/critic_results", 
        help="Directory to save critic evaluation results (default: data/critic_results)"
    )
    
    parser.add_argument(
        "--output-name", 
        help="Base name for output files (default: derived from input filename)"
    )
    
    parser.add_argument(
        "--include-auto-created", 
        action="store_true",
        help="Include auto-created entities (derived from relationships) in evaluation"
    )
    
    parser.add_argument(
        "--critic-model", 
        default="claude-sonnet-4-20250514",
        help="LLM model to use for critic evaluation (default: claude-sonnet-4-20250514)"
    )
    
    parser.add_argument(
        "--min-confidence", 
        type=float, 
        default=3.0,
        help="Minimum confidence threshold for flagging items for review (1-5, default: 3.0)"
    )
    
    parser.add_argument(
        "--batch-size", 
        type=int, 
        default=50,
        help="Number of items to evaluate in each batch (for rate limiting, default: 50)"
    )
    
    parser.add_argument(
        "--verbose", 
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Validate input file
    if not os.path.exists(args.knowledge_graph_file):
        logger.error(f"Knowledge graph file not found: {args.knowledge_graph_file}")
        sys.exit(1)
    
    try:
        # Initialize Anthropic client
        import anthropic
        
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            logger.error("ANTHROPIC_API_KEY environment variable not set")
            sys.exit(1)
        
        client = anthropic.Anthropic(api_key=api_key)
        
        # Initialize critic system
        logger.info("Initializing KnowledgeGraphCritic...")
        critic = KnowledgeGraphCritic(
            llm_client=client,
            critic_llm_client=client  # Use same client for now, could be different
        )
        
        # Load extraction results
        logger.info(f"Loading extraction results from {args.knowledge_graph_file}...")
        entities, relationships = load_extraction_results(args.knowledge_graph_file)
        
        # Load document chunks if provided
        chunks = []
        if args.chunks:
            chunks = load_chunks(args.chunks)
        
        # Determine output filename
        if args.output_name:
            base_filename = args.output_name
        else:
            base_filename = Path(args.knowledge_graph_file).stem
            if base_filename.endswith("_knowledge_graph"):
                base_filename = base_filename[:-16]  # Remove "_knowledge_graph" suffix
        
        # Run critic evaluation
        logger.info("Starting comprehensive evaluation...")
        logger.info(f"Exclude auto-created entities: {not args.include_auto_created}")
        logger.info(f"Minimum confidence threshold: {args.min_confidence}")
        
        evaluation_results = critic.evaluate_extraction_results(
            entities=entities,
            relationships=relationships,
            chunks=chunks,
            exclude_auto_created=not args.include_auto_created
        )
        
        # Save results
        logger.info(f"Saving evaluation results to {args.output_dir}...")
        output_paths = save_critic_results(evaluation_results, args.output_dir, base_filename)
        
        # Print summary
        stats = evaluation_results["statistics"]
        assessment = evaluation_results["overall_assessment"]
        
        print("\n" + "="*60)
        print("KNOWLEDGE GRAPH QUALITY EVALUATION SUMMARY")
        print("="*60)
        
        print(f"\nItems Evaluated:")
        print(f"  Entities: {stats['entities_evaluated']}")
        print(f"  Relationships: {stats['relationships_evaluated']}")
        print(f"  Total: {stats['entities_evaluated'] + stats['relationships_evaluated']}")
        
        print(f"\nQuality Distribution:")
        print(f"  High Quality Items: {stats['high_quality_entities'] + stats['high_quality_relationships']}")
        print(f"  Items Needing Review: {stats['entities_needing_review'] + stats['relationships_needing_review']}")
        
        print(f"\nOverall Assessment:")
        print(f"  Average Confidence: {assessment['overall_confidence']:.2f}/5.0")
        print(f"  Review Rate: {((stats['entities_needing_review'] + stats['relationships_needing_review']) / (stats['entities_evaluated'] + stats['relationships_evaluated']) * 100):.1f}%")
        
        print(f"\nEntity Quality by Type:")
        for entity_type, type_stats in assessment["entity_statistics"].items():
            if type_stats["count"] > 0:
                print(f"  {entity_type.capitalize()}s: {type_stats['avg_confidence']:.2f}/5.0 ({type_stats['count']} items)")
        
        if assessment["relationship_statistics"]["count"] > 0:
            print(f"  Relationships: {assessment['relationship_statistics']['avg_confidence']:.2f}/5.0 ({assessment['relationship_statistics']['count']} items)")
        
        print(f"\nRecommendations:")
        for rec in assessment["recommendations"]:
            print(f"  • {rec}")
        
        print(f"\nOutput Files:")
        for file_type, path in output_paths.items():
            print(f"  {file_type.replace('_', ' ').title()}: {path}")
        
        print(f"\nReview Tasks: {len(evaluation_results['review_tasks'])}")
        if evaluation_results['review_tasks']:
            high_priority = sum(1 for task in evaluation_results['review_tasks'] if task['priority'] >= 7)
            print(f"  High Priority: {high_priority}")
            print(f"  Medium Priority: {len(evaluation_results['review_tasks']) - high_priority}")
        
        print("\n" + "="*60)
        
        # Exit with appropriate code
        if stats['entities_needing_review'] + stats['relationships_needing_review'] > 0:
            logger.warning(f"{stats['entities_needing_review'] + stats['relationships_needing_review']} items flagged for human review")
            sys.exit(1)  # Non-zero exit code to indicate items need review
        else:
            logger.info("All items passed quality evaluation")
            sys.exit(0)
        
    except ImportError:
        logger.error("Anthropic package not installed. Please install it with 'pip install anthropic'")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error during critic evaluation: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()