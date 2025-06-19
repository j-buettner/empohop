import os
import json
import logging
from typing import Dict, List, Optional, Any, Union, Tuple
import re

# Handle import errors gracefully
try:
    from docling.document_converter import DocumentConverter
    from docling.chunking import HybridChunker
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.datamodel.base_models import InputFormat
    from docling.document_converter import PdfFormatOption
    DOCLING_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Docling not available due to import error: {e}")
    print("Falling back to basic text extraction")
    DOCLING_AVAILABLE = False
    DocumentConverter = None
    HybridChunker = None
    PdfPipelineOptions = None
    InputFormat = None
    PdfFormatOption = None

try:
    from transformers import AutoTokenizer
    TRANSFORMERS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Transformers not available: {e}")
    TRANSFORMERS_AVAILABLE = False
    AutoTokenizer = None

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DoclingExtractor:
    """
    Document extractor using Docling library for improved text extraction and chunking
    Falls back to basic extraction if Docling is not available
    """
    
    def __init__(self, 
                 chunk_size: int = 5000, 
                 chunk_overlap: int = 100,
                 use_ocr: bool = False,
                 embed_model: str = "sentence-transformers/all-MiniLM-L6-v2"):
        """
        Initialize the Docling-based document extractor
        
        Args:
            chunk_size: Maximum number of tokens per chunk
            chunk_overlap: Number of overlapping tokens between chunks
            use_ocr: Whether to use OCR for scanned documents
            embed_model: Model to use for tokenization in chunking
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.use_ocr = use_ocr
        self.embed_model = embed_model
        
        if not DOCLING_AVAILABLE:
            logger.warning("Docling not available, using fallback extraction methods")
            self.converter = None
            self.chunker = None
            self.tokenizer = None
            return
        
        try:
            # Configure OCR settings through pipeline options
            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = use_ocr
            pipeline_options.do_table_structure = True
            
            # Initialize Docling converter with OCR settings
            self.converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
                }
            )
            
            # Initialize tokenizer for chunking if transformers is available
            if TRANSFORMERS_AVAILABLE:
                self.tokenizer = AutoTokenizer.from_pretrained(embed_model)
                
                # Initialize chunker
                self.chunker = HybridChunker(
                    tokenizer=self.tokenizer,
                    max_tokens=chunk_size,
                    merge_peers=True  # Merge similar semantic sections
                )
            else:
                self.tokenizer = None
                self.chunker = None
                logger.warning("Transformers not available, using basic tokenization")
            
            logger.info(f"Initialized DoclingExtractor with chunk_size={chunk_size}, use_ocr={use_ocr}")
            
        except Exception as e:
            logger.error(f"Error initializing DoclingExtractor: {e}")
            logger.warning("Falling back to basic extraction")
            self.converter = None
            self.chunker = None
            self.tokenizer = None
    
    def extract_and_chunk(self, source: str) -> Dict[str, Any]:
        """
        Extract text and metadata from a document and chunk it
        
        Args:
            source: Path to local file or URL
            
        Returns:
            Dictionary with document, chunks, and metadata
        """
        try:
            if self.converter is not None:
                return self._extract_with_docling(source)
            else:
                return self._extract_fallback(source)
                
        except Exception as e:
            logger.error(f"Error extracting document: {str(e)}")
            # Try fallback extraction
            try:
                return self._extract_fallback(source)
            except Exception as fallback_error:
                logger.error(f"Fallback extraction also failed: {fallback_error}")
                raise e
    
    def _extract_with_docling(self, source: str) -> Dict[str, Any]:
        """Extract using Docling"""
        logger.info(f"Converting document with Docling: {source}")
        
        # Convert document using Docling (no ocr parameter needed - it's configured in pipeline options)
        result = self.converter.convert(source)
        
        # Extract the document
        doc = result.document
        
        # Get full text for compatibility
        full_text = doc.export_to_markdown()
        
        # Extract metadata
        metadata = self._extract_metadata_docling(doc, source)
        
        # Create chunks using Docling's hybrid chunker if available
        if self.chunker is not None:
            chunks = self._create_chunks_docling(doc, metadata)
        else:
            chunks = self._fallback_chunk(full_text, metadata)
        
        # Build document structure
        document = {
            "text": full_text,
            "metadata": metadata,
            "sections": self._extract_sections_docling(doc),
            "pages": self._extract_pages_docling(doc)
        }
        
        return {
            "document": document,
            "chunks": chunks,
            "metadata": metadata
        }
    
    def _extract_fallback(self, source: str) -> Dict[str, Any]:
        """Fallback extraction for when Docling is not available"""
        logger.info(f"Using fallback extraction for: {source}")
        
        # Basic file reading
        if source.lower().endswith('.txt'):
            with open(source, 'r', encoding='utf-8') as f:
                text = f.read()
        elif source.lower().endswith('.pdf'):
            try:
                import PyPDF2
                with open(source, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    text = ""
                    for page in reader.pages:
                        text += page.extract_text() + "\n"
            except ImportError:
                raise ImportError("PyPDF2 not available for PDF extraction. Please install it or fix Docling setup.")
        else:
            raise ValueError(f"Unsupported file type for fallback extraction: {source}")
        
        # Create basic metadata
        metadata = {
            "source": source,
            "title": os.path.basename(source),
            "type": self._get_file_type(source),
            "text_length": len(text),
            "word_count": len(text.split())
        }
        
        # Create basic chunks
        chunks = self._fallback_chunk(text, metadata)
        
        # Build document structure
        document = {
            "text": text,
            "metadata": metadata,
            "sections": [{"title": "Content", "content": text, "start_page": 1}],
            "pages": [{"page_number": 1, "text": text}]
        }
        
        return {
            "document": document,
            "chunks": chunks,
            "metadata": metadata
        }
    
    def _extract_metadata_docling(self, doc: Any, source: str) -> Dict[str, Any]:
        """Extract metadata from Docling document"""
        metadata = {
            "source": source,
            "title": os.path.basename(source),  # Default to filename
            "type": self._get_file_type(source),
        }
        
        # Try to extract more metadata from the document if available
        try:
            if hasattr(doc, 'metadata'):
                doc_meta = doc.metadata
                if hasattr(doc_meta, 'title') and doc_meta.title:
                    metadata["title"] = doc_meta.title
                if hasattr(doc_meta, 'author') and doc_meta.author:
                    metadata["author"] = doc_meta.author
                if hasattr(doc_meta, 'pages'):
                    metadata["pages"] = doc_meta.pages
        except:
            pass
        
        # Try to extract title from document content
        full_text = doc.export_to_markdown()
        extracted_title = self._extract_title_from_content(full_text)
        if extracted_title:
            metadata["title"] = extracted_title
        
        # Add text statistics
        metadata["text_length"] = len(full_text)
        metadata["word_count"] = len(full_text.split())
        
        return metadata
    
    def _extract_title_from_content(self, text: str) -> Optional[str]:
        """Extract title from document content"""
        lines = text.split('\n')
        
        # Look for the first substantial heading or title
        for line in lines[:20]:  # Check first 20 lines
            line = line.strip()
            if not line:
                continue
                
            # Remove markdown formatting and clean up
            clean_line = re.sub(r'^#+\s*', '', line)  # Remove markdown headers
            clean_line = re.sub(r'\*\*([^*]+)\*\*', r'\1', clean_line)  # Remove bold
            clean_line = re.sub(r'\*([^*]+)\*', r'\1', clean_line)  # Remove italic
            clean_line = clean_line.strip()
            
            # Skip very short lines, common headers, or lines with special characters
            if (len(clean_line) < 10 or 
                clean_line.lower() in ['contents', 'table of contents', 'index', 'preface', 'abstract'] or
                clean_line.startswith('<!--') or
                len(clean_line.split()) < 3):
                continue
            
            # If it looks like a title (reasonable length, not too long)
            if 10 <= len(clean_line) <= 200 and not clean_line.endswith('.'):
                return clean_line
        
        return None
    
    def _get_file_type(self, source: str) -> str:
        """Determine file type from source"""
        if source.startswith(('http://', 'https://')):
            return 'web'
        
        ext = os.path.splitext(source)[1].lower()
        ext_map = {
            '.pdf': 'pdf',
            '.docx': 'docx',
            '.doc': 'doc',
            '.pptx': 'pptx',
            '.xlsx': 'xlsx',
            '.md': 'markdown',
            '.txt': 'text',
            '.png': 'image',
            '.jpg': 'image',
            '.jpeg': 'image'
        }
        
        return ext_map.get(ext, 'unknown')
    
    def _extract_sections_docling(self, doc: Any) -> List[Dict[str, Any]]:
        """Extract sections from Docling document"""
        sections = []
        
        try:
            markdown = doc.export_to_markdown()
            current_section = {"title": "Introduction", "content": "", "start_page": 1}
            
            lines = markdown.split('\n')
            for line in lines:
                if line.startswith('#'):
                    if current_section["content"].strip():
                        sections.append(current_section)
                    
                    title = line.lstrip('#').strip()
                    current_section = {
                        "title": title,
                        "content": "",
                        "start_page": len(sections) + 1
                    }
                else:
                    current_section["content"] += line + "\n"
            
            if current_section["content"].strip():
                sections.append(current_section)
                
        except Exception as e:
            logger.warning(f"Could not extract sections: {e}")
            sections = [{
                "title": "Content",
                "content": doc.export_to_markdown(),
                "start_page": 1
            }]
        
        return sections
    
    def _extract_pages_docling(self, doc: Any) -> List[Dict[str, Any]]:
        """Extract page information from Docling document"""
        pages = []
        
        try:
            if hasattr(doc, 'pages'):
                for i, page in enumerate(doc.pages, 1):
                    pages.append({
                        "page_number": i,
                        "text": str(page)
                    })
            else:
                pages.append({
                    "page_number": 1,
                    "text": doc.export_to_markdown()
                })
        except:
            pages.append({
                "page_number": 1,
                "text": doc.export_to_markdown()
            })
        
        return pages
    
    def _create_chunks_docling(self, doc: Any, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create chunks using custom chunking that respects chunk_size"""
        chunks = []
        
        try:
            # Extract sections first for better section mapping
            sections = self._extract_sections_docling(doc)
            full_text = doc.export_to_markdown()
            
            # Use custom chunking that respects chunk_size instead of Docling's chunker
            chunks = self._custom_chunk_with_sections(full_text, sections, metadata)
                
        except Exception as e:
            logger.error(f"Error creating chunks with Docling: {e}")
            chunks = self._fallback_chunk(doc.export_to_markdown(), metadata)
        
        logger.info(f"Created {len(chunks)} chunks")
        return chunks
    
    def _custom_chunk_with_sections(self, text: str, sections: List[Dict[str, Any]], metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Custom chunking that respects chunk_size and maps sections properly"""
        chunks = []
        
        # Create a mapping of text positions to sections
        section_map = self._create_section_position_map(text, sections)
        
        # Split text into paragraphs for chunking
        paragraphs = text.split('\n\n')
        current_chunk = ""
        current_tokens = 0
        text_position = 0
        current_section_title = None
        section_start_chunk_index = 0
        
        for paragraph in paragraphs:
            if not paragraph.strip():
                text_position += len(paragraph) + 2  # +2 for \n\n
                continue
            
            # Estimate tokens using tokenizer if available, otherwise rough approximation
            if self.tokenizer:
                try:
                    paragraph_tokens = len(self.tokenizer.encode(paragraph))
                except:
                    paragraph_tokens = len(paragraph.split()) * 1.3
            else:
                paragraph_tokens = len(paragraph.split()) * 1.3
            
            # Find the section for this paragraph
            paragraph_section = self._find_section_for_position(text_position, section_map)
            
            # Check if adding this paragraph would exceed chunk size
            if current_tokens + paragraph_tokens > self.chunk_size and current_chunk:
                # Find the section for this chunk
                section_title = self._find_section_for_position(text_position - len(current_chunk), section_map)
                
                # Determine if this chunk was split due to max tokens within the same section
                is_max_token_chunked = (current_section_title == paragraph_section and 
                                      current_section_title is not None)
                
                chunk_metadata = {
                    "chunk_number": len(chunks) + 1,  # Add chunk number
                    "section_title": section_title,
                    "source": metadata["source"],
                    "title": metadata["title"],
                    "type": metadata["type"],
                    "is_max_token_chunked": is_max_token_chunked
                }
                
                chunks.append({
                    "text": current_chunk.strip(),
                    "metadata": chunk_metadata
                })
                
                current_chunk = paragraph
                current_tokens = paragraph_tokens
                current_section_title = paragraph_section
            else:
                if current_chunk:
                    current_chunk += "\n\n" + paragraph
                else:
                    current_chunk = paragraph
                    current_section_title = paragraph_section
                current_tokens += paragraph_tokens
            
            text_position += len(paragraph) + 2  # +2 for \n\n
        
        # Add last chunk
        if current_chunk:
            section_title = self._find_section_for_position(text_position - len(current_chunk), section_map)
            
            chunk_metadata = {
                "chunk_number": len(chunks) + 1,  # Add chunk number
                "section_title": section_title,
                "source": metadata["source"],
                "title": metadata["title"],
                "type": metadata["type"],
                "is_max_token_chunked": False  # Last chunk is never split
            }
            
            chunks.append({
                "text": current_chunk.strip(),
                "metadata": chunk_metadata
            })
        
        logger.info(f"Custom chunking created {len(chunks)} chunks with average size: {sum(len(c['text'].split()) for c in chunks) / len(chunks) if chunks else 0:.0f} words")
        return chunks
    
    def _create_section_position_map(self, text: str, sections: List[Dict[str, Any]]) -> List[Tuple[int, str]]:
        """Create a mapping of text positions to section titles"""
        position_map = []
        
        for section in sections:
            section_title = section["title"]
            section_content = section["content"]
            
            # Find where this section starts in the full text
            start_pos = text.find(section_content[:100])  # Use first 100 chars to find position
            if start_pos != -1:
                position_map.append((start_pos, section_title))
        
        # Sort by position
        position_map.sort(key=lambda x: x[0])
        return position_map
    
    def _find_section_for_position(self, position: int, section_map: List[Tuple[int, str]]) -> str:
        """Find which section a given text position belongs to"""
        if not section_map:
            return "Content"
        
        # Find the section that starts before or at this position
        current_section = section_map[0][1]  # Default to first section
        
        for section_pos, section_title in section_map:
            if section_pos <= position:
                current_section = section_title
            else:
                break
        
        return current_section
    
    def _fallback_chunk(self, text: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback chunking method"""
        chunks = []
        
        # Simple paragraph-based chunking
        paragraphs = text.split('\n\n')
        current_chunk = ""
        current_tokens = 0
        
        for paragraph in paragraphs:
            if not paragraph.strip():
                continue
            
            # Estimate tokens (rough approximation)
            paragraph_tokens = len(paragraph.split()) * 1.3  # Rough token estimate
            
            if current_tokens + paragraph_tokens > self.chunk_size and current_chunk:
                # In fallback mode, we consider chunks as max-token chunked since we're splitting by size
                chunk_metadata = {
                    "chunk_number": len(chunks) + 1,  # Add chunk number
                    "section_title": "Content",
                    "source": metadata["source"],
                    "title": metadata["title"],
                    "type": metadata["type"],
                    "is_max_token_chunked": True
                }
                
                chunks.append({
                    "text": current_chunk,
                    "metadata": chunk_metadata
                })
                current_chunk = paragraph
                current_tokens = paragraph_tokens
            else:
                if current_chunk:
                    current_chunk += "\n\n" + paragraph
                else:
                    current_chunk = paragraph
                current_tokens += paragraph_tokens
        
        # Add last chunk
        if current_chunk:
            chunk_metadata = {
                "chunk_number": len(chunks) + 1,  # Add chunk number
                "section_title": "Content",
                "source": metadata["source"],
                "title": metadata["title"],
                "type": metadata["type"],
                "is_max_token_chunked": False  # Last chunk is never split
            }
            
            chunks.append({
                "text": current_chunk,
                "metadata": chunk_metadata
            })
        
        return chunks
    
    def export_to_markdown(self, document: Dict[str, Any], output_path: str) -> str:
        """Export a document to Markdown"""
        try:
            # Only create directories if there's a directory path
            dir_path = os.path.dirname(output_path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            
            markdown_content = document["text"]
            
            # Add metadata header
            header = f"# {document['metadata']['title']}\n\n"
            header += "## Metadata\n\n"
            for key, value in document["metadata"].items():
                if key != "title":
                    header += f"- **{key}**: {value}\n"
            header += "\n---\n\n"
            
            full_markdown = header + markdown_content
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(full_markdown)
            
            logger.info(f"Exported document to Markdown: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error exporting to Markdown: {str(e)}")
            raise
    
    def save_chunks_to_json(self, chunks: List[Dict[str, Any]], output_path: str) -> str:
        """Save chunks to a JSON file"""
        try:
            # Only create directories if there's a directory path
            dir_path = os.path.dirname(output_path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(chunks, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved {len(chunks)} chunks to JSON: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error saving chunks to JSON: {str(e)}")
            raise
    
    def export_to_markdown_with_chunks(self, document: Dict[str, Any], chunks: List[Dict[str, Any]], output_path: str) -> str:
        """
        Export a document to Markdown with chunk break indicators
        
        Args:
            document: The document dictionary containing text and metadata
            chunks: List of chunks with their text and metadata
            output_path: Path where to save the markdown file
            
        Returns:
            Path to the saved markdown file
        """
        try:
            # Only create directories if there's a directory path
            dir_path = os.path.dirname(output_path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            
            # Start with metadata header
            markdown_content = f"# {document['metadata']['title']}\n\n"
            markdown_content += "## Metadata\n\n"
            for key, value in document["metadata"].items():
                if key != "title":
                    markdown_content += f"- **{key}**: {value}\n"
            markdown_content += "\n---\n\n"
            
            # Add chunk summary
            total_chunks = len(chunks)
            max_token_chunks = sum(1 for chunk in chunks if chunk['metadata'].get('is_max_token_chunked', False))
            markdown_content += f"## Chunking Summary\n\n"
            markdown_content += f"- **Total chunks**: {total_chunks}\n"
            markdown_content += f"- **Max-token chunked sections**: {max_token_chunks}\n"
            markdown_content += f"- **Natural section breaks**: {total_chunks - max_token_chunks}\n\n"
            markdown_content += "---\n\n"
            
            # Build the content with chunk indicators
            full_text = document["text"]
            
            # Create a mapping of chunk text to chunk numbers and metadata
            chunk_positions = []
            for i, chunk in enumerate(chunks):
                chunk_text = chunk["text"].strip()
                # Find the position of this chunk in the full text
                start_pos = full_text.find(chunk_text)
                if start_pos != -1:
                    chunk_positions.append({
                        'start': start_pos,
                        'end': start_pos + len(chunk_text),
                        'chunk_num': i + 1,
                        'is_max_token_chunked': chunk['metadata'].get('is_max_token_chunked', False),
                        'section_title': chunk['metadata'].get('section_title', 'Unknown')
                    })
            
            # Sort by position
            chunk_positions.sort(key=lambda x: x['start'])
            
            # Build the final markdown with chunk indicators
            result_content = ""
            last_pos = 0
            
            for chunk_info in chunk_positions:
                # Add any text before this chunk (shouldn't happen in normal cases)
                if chunk_info['start'] > last_pos:
                    result_content += full_text[last_pos:chunk_info['start']]
                
                # Add chunk indicator
                chunk_indicator = f"\n\n{'#' * 12} CHUNK {chunk_info['chunk_num']} {'#' * 12}\n"
                chunk_indicator += f"**Section**: {chunk_info['section_title']}\n"
                chunk_indicator += f"**Max-token chunked**: {'Yes' if chunk_info['is_max_token_chunked'] else 'No'}\n"
                chunk_indicator += f"{'#' * (24 + len(str(chunk_info['chunk_num'])))}\n\n"
                
                result_content += chunk_indicator
                
                # Add the chunk content
                chunk_content = full_text[chunk_info['start']:chunk_info['end']]
                result_content += chunk_content
                
                last_pos = chunk_info['end']
            
            # Add any remaining text
            if last_pos < len(full_text):
                result_content += full_text[last_pos:]
            
            # Combine header and content
            final_markdown = markdown_content + result_content
            
            # Write to file
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(final_markdown)
            
            logger.info(f"Exported document with chunk indicators to Markdown: {output_path}")
            logger.info(f"Total chunks: {total_chunks}, Max-token chunked: {max_token_chunks}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error exporting to Markdown with chunks: {str(e)}")
            raise


# Wrapper class to maintain compatibility with existing code
class DocumentExtractor(DoclingExtractor):
    """Compatibility wrapper to use the same class name as the original extractor"""
    pass
