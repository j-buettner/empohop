import argparse
import json
import logging
import os
import sys
from typing import Dict, List, Optional, Any

from logging_config import configure_logging
logger = logging.getLogger(__name__)

def get_extractor(use_docling: bool = False, **kwargs):
    """
    Get the appropriate document extractor
    
    Args:
        use_docling: Whether to use Docling-based extractor
        **kwargs: Additional arguments for the extractor
        
    Returns:
        Document extractor instance
    """
    if use_docling:
        try:
            from extractor_docling import DocumentExtractor
            logger.info("Using Docling-based extractor")
        except ImportError:
            logger.error("Docling not installed. Install with: pip install docling transformers")
            logger.info("Falling back to original extractor")
            from extractor import DocumentExtractor
    else:
        from extractor import DocumentExtractor
        logger.info("Using original extractor")
    
    return DocumentExtractor(**kwargs)

def analyze_chunks(chunks: List[Dict]) -> Dict[str, Any]:
    """
    Analyze document chunks to extract basic statistics
    
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
        "chunk_size_distribution": {
            "min": 0,
            "max": 0,
            "median": 0
        },
        "page_distribution": {},
        "chunking_strategy": {
            "max_token_chunked": 0,
            "natural_section_breaks": 0,
            "max_token_percentage": 0.0
        }
    }
    
    chunk_sizes = []
    
    # Analyze chunks
    for chunk in chunks:
        # Count tokens (rough approximation)
        token_count = len(chunk["text"].split())
        analysis["total_tokens"] += token_count
        chunk_sizes.append(token_count)
        
        # Track chunking strategy (new feature)
        is_max_token_chunked = chunk["metadata"].get("is_max_token_chunked", False)
        if is_max_token_chunked:
            analysis["chunking_strategy"]["max_token_chunked"] += 1
        else:
            analysis["chunking_strategy"]["natural_section_breaks"] += 1
        
        # Track section distribution
        section_title = chunk["metadata"].get("section_title", "Unknown")
        if section_title in analysis["section_distribution"]:
            analysis["section_distribution"][section_title] += 1
        else:
            analysis["section_distribution"][section_title] = 1
        
        # Track page distribution
        page_info = "Unknown"
        if "page" in chunk["metadata"]:
            page_info = f"Page {chunk['metadata']['page']}"
        elif "page_start" in chunk["metadata"] and "page_end" in chunk["metadata"]:
            page_info = f"Pages {chunk['metadata']['page_start']}-{chunk['metadata']['page_end']}"
        
        if page_info in analysis["page_distribution"]:
            analysis["page_distribution"][page_info] += 1
        else:
            analysis["page_distribution"][page_info] = 1
    
    # Calculate statistics
    if len(chunks) > 0:
        analysis["avg_tokens_per_chunk"] = analysis["total_tokens"] / len(chunks)
        analysis["chunk_size_distribution"]["min"] = min(chunk_sizes)
        analysis["chunk_size_distribution"]["max"] = max(chunk_sizes)
        chunk_sizes.sort()
        median_index = len(chunk_sizes) // 2
        if len(chunk_sizes) % 2 == 0:
            analysis["chunk_size_distribution"]["median"] = (chunk_sizes[median_index - 1] + chunk_sizes[median_index]) / 2
        else:
            analysis["chunk_size_distribution"]["median"] = chunk_sizes[median_index]
        
        # Calculate chunking strategy percentage
        total_chunks = analysis["chunking_strategy"]["max_token_chunked"] + analysis["chunking_strategy"]["natural_section_breaks"]
        if total_chunks > 0:
            analysis["chunking_strategy"]["max_token_percentage"] = (analysis["chunking_strategy"]["max_token_chunked"] / total_chunks) * 100
    
    return analysis

def main():
    """Main function to extract text and metadata from a document"""
    configure_logging()
    parser = argparse.ArgumentParser(description="Extract text and metadata from a document")
    parser.add_argument("source", help="Path to document or URL")
    parser.add_argument("--output-dir", default="data/extracted", help="Directory to save output files")
    parser.add_argument("--chunk-size", type=int, default=1000, help="Maximum number of tokens per chunk")
    parser.add_argument("--chunk-overlap", type=int, default=100, help="Number of overlapping tokens between chunks")
    parser.add_argument("--analyze", action="store_true", help="Analyze document chunks")
    parser.add_argument("--export-markdown", action="store_true", help="Export document to Markdown")
    parser.add_argument("--use-docling", action="store_true", help="Use Docling for extraction (better OCR support)")
    parser.add_argument("--ocr", action="store_true", help="Enable OCR for scanned documents (requires --use-docling)")
    parser.add_argument("--embed-model", default="sentence-transformers/all-MiniLM-L6-v2", 
                       help="Embedding model for Docling chunking")
    parser.add_argument("--filter-sections", action="store_true", 
                       help="Filter out References and Index sections and save as *_core_chunks.json")
    parser.add_argument("--export-markdown-with-chunks", action="store_true", 
                       help="Export document to Markdown with chunk break indicators (requires --use-docling)")
    args = parser.parse_args()
    
    # Validate arguments
    if args.ocr and not args.use_docling:
        logger.warning("OCR requires Docling. Adding --use-docling flag.")
        args.use_docling = True
    
    try:
        # Create output directory if it doesn't exist
        os.makedirs(args.output_dir, exist_ok=True)
        
        # Initialize document extractor
        extractor_kwargs = {
            "chunk_size": args.chunk_size,
            "chunk_overlap": args.chunk_overlap
        }
        
        # Add Docling-specific arguments
        if args.use_docling:
            extractor_kwargs["use_ocr"] = args.ocr
            extractor_kwargs["embed_model"] = args.embed_model
        
        extractor = get_extractor(use_docling=args.use_docling, **extractor_kwargs)
        
        # Extract text and metadata from document
        logger.info(f"Extracting text and metadata from {args.source}")
        if args.ocr:
            logger.info("OCR enabled for scanned document processing")
        
        result = extractor.extract_and_chunk(args.source)
        
        # Get base filename for outputs
        base_filename = os.path.splitext(os.path.basename(args.source))[0]
        
        # Save chunks to JSON
        chunks_path = os.path.join(args.output_dir, f"{base_filename}_chunks.json")
        extractor.save_chunks_to_json(result["chunks"], chunks_path)
        logger.info(f"Saved {len(result['chunks'])} chunks to {chunks_path}")
        
        # Filter sections if requested
        if args.filter_sections:
            exclude_sections = ["REFERENCES", "INDEX"]
            filtered_chunks = []
            excluded_count = 0
            
            for chunk in result["chunks"]:
                section_title = chunk.get("metadata", {}).get("section_title", "")
                if section_title in exclude_sections:
                    excluded_count += 1
                    continue
                filtered_chunks.append(chunk)
            
            # Save filtered chunks
            core_chunks_path = os.path.join(args.output_dir, f"{base_filename}_core_chunks.json")
            extractor.save_chunks_to_json(filtered_chunks, core_chunks_path)
            logger.info(f"Filtered {len(result['chunks'])} chunks -> {len(filtered_chunks)} chunks")
            logger.info(f"Excluded {excluded_count} chunks from sections: {exclude_sections}")
            logger.info(f"Saved core chunks to {core_chunks_path}")
        
        # Save metadata to JSON
        metadata_path = os.path.join(args.output_dir, f"{base_filename}_metadata.json")
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(result["metadata"], f, indent=2, ensure_ascii=False)
        logger.info(f"Saved metadata to {metadata_path}")
        
        # Export to Markdown if requested
        if args.export_markdown:
            markdown_path = os.path.join(args.output_dir, f"{base_filename}.md")
            extractor.export_to_markdown(result["document"], markdown_path)
            logger.info(f"Exported document to Markdown: {markdown_path}")
        
        # Export to Markdown with chunk indicators if requested (Docling only)
        if args.export_markdown_with_chunks:
            if args.use_docling and hasattr(extractor, 'export_to_markdown_with_chunks'):
                chunks_markdown_path = os.path.join(args.output_dir, f"{base_filename}_with_chunks.md")
                extractor.export_to_markdown_with_chunks(result["document"], result["chunks"], chunks_markdown_path)
                logger.info(f"Exported document with chunk indicators to Markdown: {chunks_markdown_path}")
            else:
                logger.warning("Markdown with chunk indicators requires --use-docling flag and Docling extractor")
        
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
            logger.info("Document Summary:")
            logger.info(f"  - Chunks: {analysis['chunk_count']}")
            logger.info(f"  - Total Tokens: {analysis['total_tokens']}")
            logger.info(f"  - Avg Tokens per Chunk: {analysis['avg_tokens_per_chunk']:.2f}")
            logger.info(f"  - Token Range: {analysis['chunk_size_distribution']['min']} - {analysis['chunk_size_distribution']['max']}")
            logger.info(f"  - Sections: {len(analysis['section_distribution'])}")
            
            # Show chunking strategy analysis (new feature)
            if 'chunking_strategy' in analysis:
                logger.info(f"  - Chunking Strategy:")
                logger.info(f"    - Max-token chunked: {analysis['chunking_strategy']['max_token_chunked']}")
                logger.info(f"    - Natural section breaks: {analysis['chunking_strategy']['natural_section_breaks']}")
                logger.info(f"    - Max-token percentage: {analysis['chunking_strategy']['max_token_percentage']:.1f}%")
            
            # Show section distribution
            if analysis['section_distribution']:
                logger.info("  - Section Distribution:")
                for section, count in sorted(analysis['section_distribution'].items(), 
                                           key=lambda x: x[1], reverse=True)[:5]:
                    logger.info(f"    - {section}: {count} chunks")
                if len(analysis['section_distribution']) > 5:
                    logger.info(f"    - ... and {len(analysis['section_distribution']) - 5} more sections")
            
            # Show page distribution summary
            if analysis['page_distribution'] and len(analysis['page_distribution']) < 20:
                logger.info("  - Page Distribution:")
                for page_info, count in sorted(analysis['page_distribution'].items()):
                    logger.info(f"    - {page_info}: {count} chunks")
        
        logger.info("Extraction complete")
        
    except Exception as e:
        logger.error(f"Error extracting document: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
