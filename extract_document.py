import argparse
import json
import logging
import os
import sys
from typing import Dict, List, Optional, Any

from extractor import DocumentExtractor

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def analyze_chunks(chunks: List[Dict]) -> Dict[str, Any]:
    """
    Analyze document chunks to extract statistics and insights
    
    Args:
        chunks: List of document chunks
        
    Returns:
        Dictionary with analysis results
    """
    # Initialize analysis results
    analysis = {
        "chunk_count": len(chunks),
        "total_tokens": 0,
        "avg_tokens_per_chunk": 0,
        "section_distribution": {},
        "potential_entities": {
            "events": [],
            "actors": [],
            "concepts": [],
            "publications": [],
            "locations": []
        }
    }
    
    # Analyze chunks
    for chunk in chunks:
        # Count tokens (rough approximation)
        token_count = len(chunk["text"].split())
        analysis["total_tokens"] += token_count
        
        # Track section distribution
        section_title = chunk["metadata"].get("section_title", "Unknown")
        if section_title in analysis["section_distribution"]:
            analysis["section_distribution"][section_title] += 1
        else:
            analysis["section_distribution"][section_title] = 1
        
        # Simple entity detection (very basic, just for illustration)
        # In a real system, you would use NER or other techniques
        text = chunk["text"].lower()
        
        # Look for potential events (years followed by text)
        import re
        year_pattern = r'\b(19|20)\d{2}\b'
        years = re.findall(year_pattern, text)
        for year in years:
            # Get context around the year
            year_index = text.find(year)
            start = max(0, year_index - 50)
            end = min(len(text), year_index + 50)
            context = text[start:end]
            
            # Add to potential events
            if len(analysis["potential_entities"]["events"]) < 10:  # Limit to 10 examples
                analysis["potential_entities"]["events"].append({
                    "year": year,
                    "context": context
                })
        
        # Look for potential actors (organizations, people)
        org_indicators = ["university", "institute", "organization", "association", "society", "foundation"]
        for indicator in org_indicators:
            if indicator in text:
                # Get context around the indicator
                indicator_index = text.find(indicator)
                start = max(0, indicator_index - 50)
                end = min(len(text), indicator_index + 50)
                context = text[start:end]
                
                # Add to potential actors
                if len(analysis["potential_entities"]["actors"]) < 10:  # Limit to 10 examples
                    analysis["potential_entities"]["actors"].append({
                        "type": "organization",
                        "indicator": indicator,
                        "context": context
                    })
    
    # Calculate average tokens per chunk
    if len(chunks) > 0:
        analysis["avg_tokens_per_chunk"] = analysis["total_tokens"] / len(chunks)
    
    return analysis

def extract_entities_simple(chunks: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Simple entity extraction from document chunks
    
    Args:
        chunks: List of document chunks
        
    Returns:
        Dictionary with extracted entities
    """
    # Initialize entities
    entities = {
        "events": [],
        "actors": [],
        "concepts": [],
        "publications": [],
        "locations": []
    }
    
    # Extract entities from chunks
    for chunk in chunks:
        text = chunk["text"].lower()
        
        # Extract events (years followed by text)
        import re
        year_pattern = r'\b(19|20)\d{2}\b'
        years = re.findall(year_pattern, text)
        for year in years:
            # Get context around the year
            year_index = text.find(year)
            start = max(0, year_index - 50)
            end = min(len(text), year_index + 100)
            context = text[start:end]
            
            # Try to extract a title
            title = "Unknown Event"
            if "conference" in context:
                title = "Conference"
            elif "publication" in context:
                title = "Publication"
            elif "established" in context or "founded" in context:
                title = "Organization Founding"
            elif "report" in context:
                title = "Report"
            
            # Add to events
            entities["events"].append({
                "title": title,
                "year": int(year),
                "description": context,
                "type": "Unknown",
                "significance": 3
            })
        
        # Extract actors (organizations)
        org_indicators = ["university", "institute", "organization", "association", "society", "foundation"]
        for indicator in org_indicators:
            if indicator in text:
                # Get context around the indicator
                indicator_index = text.find(indicator)
                start = max(0, indicator_index - 50)
                end = min(len(text), indicator_index + 100)
                context = text[start:end]
                
                # Try to extract a name
                name = "Unknown Organization"
                words = context.split()
                indicator_word_index = -1
                for i, word in enumerate(words):
                    if indicator in word:
                        indicator_word_index = i
                        break
                
                if indicator_word_index > 0:
                    # Look for capitalized words before the indicator
                    name_words = []
                    for i in range(indicator_word_index - 1, max(0, indicator_word_index - 5), -1):
                        if words[i][0].isupper() if words[i] else False:
                            name_words.insert(0, words[i])
                        else:
                            break
                    
                    if name_words:
                        name_words.append(words[indicator_word_index])
                        name = " ".join(name_words)
                
                # Add to actors
                entities["actors"].append({
                    "name": name,
                    "type": "Institution",
                    "description": context,
                    "role": "Unknown"
                })
    
    # Deduplicate entities
    for entity_type in entities:
        unique_entities = {}
        for entity in entities[entity_type]:
            if entity_type == "events":
                key = f"{entity['title']}_{entity['year']}"
            else:
                key = entity["name"]
            
            if key not in unique_entities:
                unique_entities[key] = entity
        
        entities[entity_type] = list(unique_entities.values())
    
    return entities

def main():
    """Main function to extract text and metadata from a document"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Extract text and metadata from a document")
    parser.add_argument("source", help="Path to document or URL")
    parser.add_argument("--output-dir", default="data/extracted", help="Directory to save output files")
    parser.add_argument("--chunk-size", type=int, default=1000, help="Maximum number of tokens per chunk")
    parser.add_argument("--chunk-overlap", type=int, default=100, help="Number of overlapping tokens between chunks")
    parser.add_argument("--analyze", action="store_true", help="Analyze document chunks")
    parser.add_argument("--extract-entities", action="store_true", help="Extract entities from document chunks")
    parser.add_argument("--export-markdown", action="store_true", help="Export document to Markdown")
    args = parser.parse_args()
    
    try:
        # Create output directory if it doesn't exist
        os.makedirs(args.output_dir, exist_ok=True)
        
        # Initialize document extractor
        extractor = DocumentExtractor(
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap
        )
        
        # Extract text and metadata from document
        logger.info(f"Extracting text and metadata from {args.source}")
        result = extractor.extract_and_chunk(args.source)
        
        # Get base filename for outputs
        base_filename = os.path.splitext(os.path.basename(args.source))[0]
        
        # Save chunks to JSON
        chunks_path = os.path.join(args.output_dir, f"{base_filename}_chunks.json")
        extractor.save_chunks_to_json(result["chunks"], chunks_path)
        
        # Save metadata to JSON
        metadata_path = os.path.join(args.output_dir, f"{base_filename}_metadata.json")
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(result["metadata"], f, indent=2)
        
        # Export to Markdown if requested
        if args.export_markdown:
            markdown_path = os.path.join(args.output_dir, f"{base_filename}.md")
            extractor.export_to_markdown(result["document"], markdown_path)
            logger.info(f"Exported document to Markdown: {markdown_path}")
        
        # Analyze chunks if requested
        if args.analyze:
            logger.info("Analyzing document chunks")
            analysis = analyze_chunks(result["chunks"])
            
            # Save analysis to JSON
            analysis_path = os.path.join(args.output_dir, f"{base_filename}_analysis.json")
            with open(analysis_path, 'w', encoding='utf-8') as f:
                json.dump(analysis, f, indent=2)
            
            logger.info(f"Saved analysis to {analysis_path}")
            
            # Print summary
            logger.info(f"Document Summary:")
            logger.info(f"  - Chunks: {analysis['chunk_count']}")
            logger.info(f"  - Total Tokens: {analysis['total_tokens']}")
            logger.info(f"  - Avg Tokens per Chunk: {analysis['avg_tokens_per_chunk']:.2f}")
            logger.info(f"  - Sections: {len(analysis['section_distribution'])}")
            logger.info(f"  - Potential Events: {len(analysis['potential_entities']['events'])}")
            logger.info(f"  - Potential Actors: {len(analysis['potential_entities']['actors'])}")
        
        # Extract entities if requested
        if args.extract_entities:
            logger.info("Extracting entities from document chunks")
            entities = extract_entities_simple(result["chunks"])
            
            # Save entities to JSON
            entities_path = os.path.join(args.output_dir, f"{base_filename}_entities.json")
            with open(entities_path, 'w', encoding='utf-8') as f:
                json.dump(entities, f, indent=2)
            
            logger.info(f"Saved entities to {entities_path}")
            
            # Print summary
            logger.info(f"Entity Extraction Summary:")
            for entity_type, entity_list in entities.items():
                logger.info(f"  - {entity_type.capitalize()}: {len(entity_list)}")
        
        logger.info("Extraction complete")
        
    except Exception as e:
        logger.error(f"Error extracting document: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
