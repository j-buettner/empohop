import os
import json
import logging
import tempfile
from typing import Dict, List, Optional, Any, Union, Tuple
import re

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DocumentExtractor:
    """
    Class for extracting text and metadata from documents
    """
    
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 100):
        """
        Initialize the document extractor
        
        Args:
            chunk_size: Maximum number of tokens per chunk
            chunk_overlap: Number of overlapping tokens between chunks
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        logger.info(f"Initialized DocumentExtractor with chunk_size={chunk_size}, chunk_overlap={chunk_overlap}")
    
    def extract_and_chunk(self, source: str) -> Dict[str, Any]:
        """
        Extract text and metadata from a document and chunk it
        
        Args:
            source: Path to local file or URL
            
        Returns:
            Dictionary with document, chunks, and metadata
        """
        # Determine source type
        if source.startswith(('http://', 'https://')):
            logger.info(f"Extracting from URL: {source}")
            document = self._extract_from_url(source)
        else:
            logger.info(f"Extracting from file: {source}")
            document = self._extract_from_file(source)
        
        # Chunk the document
        chunks = self._chunk_document(document)
        
        # Extract metadata
        metadata = self._extract_metadata(document)
        
        return {
            "document": document,
            "chunks": chunks,
            "metadata": metadata
        }
    
    def _is_likely_section_header(self, line: str, prev_line: str = "", next_line: str = "") -> bool:
        """
        Determine if a line is likely a section header
        
        Args:
            line: The line to check
            prev_line: The previous line (for context)
            next_line: The next line (for context)
            
        Returns:
            Boolean indicating if line is likely a section header
        """
        line = line.strip()
        
        # Skip if too short or too long
        if len(line) < 3 or len(line) > 100:
            return False
        
        # Common section header patterns
        header_patterns = [
            r'^\d+\.?\s+[A-Z]',  # Numbered sections like "1. INTRODUCTION"
            r'^[IVX]+\.?\s+',    # Roman numerals
            r'^(CHAPTER|Chapter|Section|SECTION)\s+\d+',  # Explicit section markers
            r'^(Introduction|Conclusion|Abstract|References|Bibliography|Appendix)',  # Common headers
        ]
        
        # Check patterns
        for pattern in header_patterns:
            if re.match(pattern, line):
                return True
        
        # Check if all uppercase and surrounded by whitespace
        if line.isupper():
            # Avoid single words unless they're common headers
            word_count = len(line.split())
            if word_count == 1:
                common_headers = ['INTRODUCTION', 'ABSTRACT', 'CONCLUSION', 'REFERENCES', 
                                'BIBLIOGRAPHY', 'ACKNOWLEDGMENTS', 'SUMMARY', 'RESULTS', 
                                'METHODS', 'DISCUSSION', 'APPENDIX']
                return line in common_headers
            
            # Multi-word uppercase lines are more likely headers if surrounded by space
            if (not prev_line.strip() or not next_line.strip()):
                return True
            
            # Avoid lines that look like data (e.g., "GARN 331,069")
            if any(char.isdigit() for char in line) and ',' in line:
                return False
            
            # Accept if 2-5 words and uppercase
            if 2 <= word_count <= 5:
                return True
        
        return False
        """
        Extract text and metadata from a URL
        
        Args:
            url: URL to extract from
            
        Returns:
            Dictionary with text and metadata
        """
        try:
            import requests
            from bs4 import BeautifulSoup
            
            # Download the content
            response = requests.get(url)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract text
            text = soup.get_text(separator='\n\n')
            
            # Extract metadata
            title = soup.title.string if soup.title else ""
            
            # Create document (no page structure for web content)
            document = {
                "text": text,
                "metadata": {
                    "source": url,
                    "title": title,
                    "type": "web",
                },
                "pages": [{"page_number": 1, "text": text}]  # Treat as single page
            }
            
            return document
            
        except Exception as e:
            logger.error(f"Error extracting from URL: {str(e)}")
            raise
    
    def _extract_from_file(self, file_path: str) -> Dict[str, Any]:
        """
        Extract text and metadata from a file
        
        Args:
            file_path: Path to the file
            
        Returns:
            Dictionary with text and metadata
        """
        # Get file extension
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()
        
        try:
            # Extract based on file type
            if ext == '.pdf':
                return self._extract_from_pdf(file_path)
            elif ext in ['.docx', '.doc']:
                return self._extract_from_docx(file_path)
            elif ext in ['.txt', '.md', '.rst']:
                return self._extract_from_text(file_path)
            else:
                logger.warning(f"Unsupported file type: {ext}")
                return self._extract_from_text(file_path)
                
        except Exception as e:
            logger.error(f"Error extracting from file: {str(e)}")
            raise
    
    def _extract_from_pdf(self, file_path: str) -> Dict[str, Any]:
        """
        Extract text and metadata from a PDF file
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Dictionary with text and metadata
        """
        try:
            # Try using PyPDF2 first
            return self._extract_from_pdf_pypdf2(file_path)
        except Exception as e:
            logger.warning(f"Error extracting with PyPDF2: {str(e)}")
            logger.info("Falling back to pdfminer.six")
            
            # Fall back to pdfminer.six
            return self._extract_from_pdf_pdfminer(file_path)
    
    def _extract_from_pdf_pypdf2(self, file_path: str) -> Dict[str, Any]:
        """
        Extract text and metadata from a PDF file using PyPDF2
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Dictionary with text and metadata
        """
        try:
            from PyPDF2 import PdfReader
            
            # Open the PDF
            reader = PdfReader(file_path)
            
            # Extract text
            full_text = ""
            metadata = {}
            sections = []
            pages = []
            current_section = {"title": "Introduction", "content": "", "start_page": 1}
            
            # Extract document info
            if reader.metadata:
                metadata = {
                    "title": reader.metadata.get('/Title', ''),
                    "author": reader.metadata.get('/Author', ''),
                    "subject": reader.metadata.get('/Subject', ''),
                    "creator": reader.metadata.get('/Creator', ''),
                    "producer": reader.metadata.get('/Producer', ''),
                }
            
            # Process each page
            for page_num, page in enumerate(reader.pages, 1):
                page_text = page.extract_text()
                
                if page_text:
                    # Store page data
                    pages.append({
                        "page_number": page_num,
                        "text": page_text
                    })
                    
                    # Look for section headers
                    lines = page_text.split('\n')
                    for i, line in enumerate(lines):
                        prev_line = lines[i-1] if i > 0 else ""
                        next_line = lines[i+1] if i < len(lines)-1 else ""
                        
                        # Check if this is a section header
                        if self._is_likely_section_header(line, prev_line, next_line):
                            # Save the current section
                            if current_section["content"].strip():
                                current_section["end_page"] = page_num
                                # Ensure page order is correct
                                if current_section["start_page"] > current_section["end_page"]:
                                    current_section["end_page"] = current_section["start_page"]
                                sections.append(current_section)
                            
                            # Start a new section
                            current_section = {
                                "title": line.strip(), 
                                "content": "",
                                "start_page": page_num
                            }
                        else:
                            current_section["content"] += line + "\n"
                    
                    full_text += page_text + "\n\n"
            
            # Add the last section
            if current_section["content"].strip():
                current_section["end_page"] = len(reader.pages)
                sections.append(current_section)
            
            # Create document
            document = {
                "text": full_text,
                "metadata": {
                    "source": file_path,
                    "title": metadata.get("title", os.path.basename(file_path)),
                    "author": metadata.get("author", ""),
                    "type": "pdf",
                    "pages": len(reader.pages),
                },
                "sections": sections,
                "pages": pages
            }
            
            return document
            
        except Exception as e:
            logger.error(f"Error extracting from PDF with PyPDF2: {str(e)}")
            raise
    
    def _extract_from_pdf_pdfminer(self, file_path: str) -> Dict[str, Any]:
        """
        Extract text and metadata from a PDF file using pdfminer.six
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Dictionary with text and metadata
        """
        try:
            from pdfminer.high_level import extract_pages
            from pdfminer.layout import LTTextContainer
            from pdfminer.pdfparser import PDFParser
            from pdfminer.pdfdocument import PDFDocument
            
            # Extract metadata
            with open(file_path, 'rb') as f:
                parser = PDFParser(f)
                doc = PDFDocument(parser)
                metadata = doc.info[0] if doc.info else {}
                
                # Convert metadata values from bytes to str
                metadata = {k: v.decode('utf-8', errors='ignore') if isinstance(v, bytes) else v 
                           for k, v in metadata.items()}
            
            # Extract text page by page
            pages = []
            full_text = ""
            sections = []
            current_section = {"title": "Introduction", "content": "", "start_page": 1}
            
            for page_num, page_layout in enumerate(extract_pages(file_path), 1):
                page_text = ""
                for element in page_layout:
                    if isinstance(element, LTTextContainer):
                        page_text += element.get_text()
                
                # Store page data
                pages.append({
                    "page_number": page_num,
                    "text": page_text
                })
                
                # Look for section headers
                lines = page_text.split('\n')
                for i, line in enumerate(lines):
                    prev_line = lines[i-1] if i > 0 else ""
                    next_line = lines[i+1] if i < len(lines)-1 else ""
                    
                    # Check if this is a section header
                    if self._is_likely_section_header(line, prev_line, next_line):
                        # Save the current section
                        if current_section["content"].strip():
                            current_section["end_page"] = page_num
                            # Ensure page order is correct
                            if current_section["start_page"] > current_section["end_page"]:
                                current_section["end_page"] = current_section["start_page"]
                            sections.append(current_section)
                        
                        # Start a new section
                        current_section = {
                            "title": line.strip(), 
                            "content": "",
                            "start_page": page_num
                        }
                    else:
                        current_section["content"] += line + "\n"
                
                full_text += page_text + "\n\n"
            
            # Add the last section
            if current_section["content"].strip():
                current_section["end_page"] = page_num
                sections.append(current_section)
            
            # Create document
            document = {
                "text": full_text,
                "metadata": {
                    "source": file_path,
                    "title": metadata.get("Title", os.path.basename(file_path)),
                    "author": metadata.get("Author", ""),
                    "type": "pdf",
                    "pages": len(pages),
                },
                "sections": sections,
                "pages": pages
            }
            
            return document
            
        except Exception as e:
            logger.error(f"Error extracting from PDF with pdfminer.six: {str(e)}")
            raise
    
    def _extract_from_docx(self, file_path: str) -> Dict[str, Any]:
        """
        Extract text and metadata from a DOCX file
        
        Args:
            file_path: Path to the DOCX file
            
        Returns:
            Dictionary with text and metadata
        """
        try:
            import docx
            
            # Open the document
            doc = docx.Document(file_path)
            
            # Extract text with page tracking (approximate for DOCX)
            full_text = ""
            pages = []
            current_page_text = ""
            current_page_num = 1
            approx_chars_per_page = 3000  # Rough approximation
            
            # Extract metadata
            core_properties = doc.core_properties
            
            # Extract sections
            sections = []
            current_section = {"title": "Introduction", "content": "", "start_page": 1}
            
            for para in doc.paragraphs:
                para_text = para.text
                
                # Check if paragraph is a heading
                if para.style.name.startswith('Heading'):
                    # Save the current section
                    if current_section["content"].strip():
                        current_section["end_page"] = current_page_num
                        sections.append(current_section)
                    
                    # Start a new section
                    current_section = {
                        "title": para_text, 
                        "content": "",
                        "start_page": current_page_num
                    }
                else:
                    current_section["content"] += para_text + "\n"
                
                # Add to current page
                current_page_text += para_text + "\n"
                full_text += para_text + "\n"
                
                # Check if we should start a new page (rough approximation)
                if len(current_page_text) > approx_chars_per_page:
                    pages.append({
                        "page_number": current_page_num,
                        "text": current_page_text
                    })
                    current_page_num += 1
                    current_page_text = ""
            
            # Add the last page
            if current_page_text.strip():
                pages.append({
                    "page_number": current_page_num,
                    "text": current_page_text
                })
            
            # Add the last section
            if current_section["content"].strip():
                current_section["end_page"] = current_page_num
                sections.append(current_section)
            
            # Create document
            document = {
                "text": full_text,
                "metadata": {
                    "source": file_path,
                    "title": core_properties.title or os.path.basename(file_path),
                    "author": core_properties.author or "",
                    "type": "docx",
                    "pages": len(pages),
                },
                "sections": sections,
                "pages": pages
            }
            
            return document
            
        except Exception as e:
            logger.error(f"Error extracting from DOCX: {str(e)}")
            raise
    
    def _extract_from_text(self, file_path: str) -> Dict[str, Any]:
        """
        Extract text from a plain text file
        
        Args:
            file_path: Path to the text file
            
        Returns:
            Dictionary with text and metadata
        """
        try:
            # Read the file
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
            
            # For text files, treat as single page
            pages = [{"page_number": 1, "text": text}]
            
            # Extract sections
            sections = []
            current_section = {"title": "Introduction", "content": "", "start_page": 1}
            
            lines = text.split('\n')
            for line in lines:
                # Simple heuristic for section headers
                if line.strip() and not line.strip()[0].isspace() and line.strip().endswith(':'):
                    # Save the current section
                    if current_section["content"].strip():
                        current_section["end_page"] = 1
                        sections.append(current_section)
                    
                    # Start a new section
                    current_section = {
                        "title": line.strip(), 
                        "content": "",
                        "start_page": 1
                    }
                else:
                    current_section["content"] += line + "\n"
            
            # Add the last section
            if current_section["content"].strip():
                current_section["end_page"] = 1
                sections.append(current_section)
            
            # Create document
            document = {
                "text": text,
                "metadata": {
                    "source": file_path,
                    "title": os.path.basename(file_path),
                    "type": "text",
                    "pages": 1,
                },
                "sections": sections,
                "pages": pages
            }
            
            return document
            
        except Exception as e:
            logger.error(f"Error extracting from text file: {str(e)}")
            raise
    
    def _chunk_document(self, document: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Chunk a document into smaller pieces with page tracking
        
        Args:
            document: Document to chunk
            
        Returns:
            List of chunks
        """
        chunks = []
        
        # Create a mapping of text position to page number
        page_mapping = self._create_page_mapping(document)
        
        # Check if document has sections
        if "sections" in document and document["sections"]:
            # Chunk by section
            for section in document["sections"]:
                section_chunks = self._chunk_text(
                    section["content"], 
                    {
                        "section_title": section["title"],
                        "section_start_page": section.get("start_page"),
                        "section_end_page": section.get("end_page")
                    },
                    page_mapping
                )
                chunks.extend(section_chunks)
        else:
            # Chunk the entire document
            chunks = self._chunk_text(document["text"], {}, page_mapping)
        
        # Add document metadata to each chunk
        for chunk in chunks:
            chunk["metadata"].update({
                "source": document["metadata"]["source"],
                "title": document["metadata"]["title"],
                "type": document["metadata"]["type"],
            })
        
        return chunks
    
    def _create_page_mapping(self, document: Dict[str, Any]) -> Dict[int, int]:
        """
        Create a mapping of character position to page number
        
        Args:
            document: Document with page information
            
        Returns:
            Dictionary mapping character position to page number
        """
        page_mapping = {}
        
        if "pages" not in document:
            return page_mapping
        
        current_pos = 0
        for page in document["pages"]:
            page_text = page["text"]
            page_num = page["page_number"]
            
            # Map all positions in this page to the page number
            for i in range(len(page_text)):
                page_mapping[current_pos + i] = page_num
            
            current_pos += len(page_text) + 2  # +2 for \n\n between pages
        
        return page_mapping
    
    def _get_page_range(self, text: str, start_pos: int, page_mapping: Dict[int, int]) -> Tuple[int, int]:
        """
        Get the page range for a chunk of text
        
        Args:
            text: The chunk text
            start_pos: Starting position in the document
            page_mapping: Character position to page mapping
            
        Returns:
            Tuple of (start_page, end_page)
        """
        if not page_mapping:
            return (None, None)
        
        # Find start page
        start_page = page_mapping.get(start_pos, None)
        
        # Find end page
        end_pos = start_pos + len(text) - 1
        end_page = page_mapping.get(end_pos, None)
        
        # Handle cases where exact position not found
        if start_page is None:
            # Find closest position
            for pos in sorted(page_mapping.keys()):
                if pos >= start_pos:
                    start_page = page_mapping[pos]
                    break
        
        if end_page is None:
            # Find closest position
            for pos in sorted(page_mapping.keys(), reverse=True):
                if pos <= end_pos:
                    end_page = page_mapping[pos]
                    break
        
        return (start_page, end_page)
    
    def _chunk_text(self, text: str, metadata: Dict[str, Any], page_mapping: Dict[int, int] = None) -> List[Dict[str, Any]]:
        """
        Chunk text into smaller pieces with page tracking
        
        Args:
            text: Text to chunk
            metadata: Metadata to add to each chunk
            page_mapping: Character position to page mapping
            
        Returns:
            List of chunks
        """
        chunks = []
        
        # Split text into paragraphs
        paragraphs = text.split('\n\n')
        
        current_chunk = ""
        current_tokens = 0
        current_pos = 0  # Track position in original text
        chunk_start_pos = 0
        
        # Minimum chunk size to avoid ultra-short chunks
        min_chunk_tokens = 50
        
        for paragraph in paragraphs:
            # Skip empty paragraphs
            if not paragraph.strip():
                current_pos += 2  # Account for \n\n
                continue
            
            # Estimate tokens (rough approximation)
            paragraph_tokens = len(paragraph.split())
            
            # If adding this paragraph would exceed the chunk size AND we have a reasonable chunk, save it
            if (current_tokens + paragraph_tokens > self.chunk_size and 
                current_chunk and 
                current_tokens >= min_chunk_tokens):
                
                # Get page range for this chunk
                start_page, end_page = self._get_page_range(
                    current_chunk, chunk_start_pos, page_mapping
                ) if page_mapping else (None, None)
                
                # Create chunk with page info
                chunk_metadata = metadata.copy()
                
                # Only add page info if it makes sense
                if start_page is not None and end_page is not None:
                    # Ensure page order is correct
                    if start_page <= end_page:
                        if start_page == end_page:
                            chunk_metadata["page"] = start_page
                        else:
                            chunk_metadata["page_start"] = start_page
                            chunk_metadata["page_end"] = end_page
                    else:
                        # If pages are reversed, use the section's page info as fallback
                        if "section_start_page" in metadata and "section_end_page" in metadata:
                            # Fix section page order if needed
                            section_start = metadata["section_start_page"]
                            section_end = metadata["section_end_page"]
                            if section_start <= section_end:
                                chunk_metadata["page_start"] = section_start
                                chunk_metadata["page_end"] = section_end
                            else:
                                # Use single page
                                chunk_metadata["page"] = section_start
                        else:
                            # Use the smaller page number
                            chunk_metadata["page"] = min(start_page, end_page)
                
                chunks.append({
                    "text": current_chunk,
                    "metadata": chunk_metadata
                })
                
                # Start a new chunk with overlap
                overlap_tokens = min(current_tokens, self.chunk_overlap)
                overlap_words = current_chunk.split()[-overlap_tokens:]
                current_chunk = " ".join(overlap_words) + "\n\n" + paragraph
                current_tokens = overlap_tokens + paragraph_tokens
                
                # Update chunk start position
                chunk_start_pos = current_pos - len(" ".join(overlap_words))
            else:
                # Add paragraph to current chunk
                if current_chunk:
                    current_chunk += "\n\n" + paragraph
                else:
                    current_chunk = paragraph
                    chunk_start_pos = current_pos
                current_tokens += paragraph_tokens
            
            # Update position
            current_pos += len(paragraph) + 2  # +2 for \n\n
        
        # Add the last chunk if it has meaningful content
        if current_chunk and len(current_chunk.split()) >= min_chunk_tokens:
            # Get page range for this chunk
            start_page, end_page = self._get_page_range(
                current_chunk, chunk_start_pos, page_mapping
            ) if page_mapping else (None, None)
            
            # Create chunk with page info
            chunk_metadata = metadata.copy()
            
            # Only add page info if it makes sense
            if start_page is not None and end_page is not None:
                if start_page <= end_page:
                    if start_page == end_page:
                        chunk_metadata["page"] = start_page
                    else:
                        chunk_metadata["page_start"] = start_page
                        chunk_metadata["page_end"] = end_page
                else:
                    # Use fallback logic
                    if "section_start_page" in metadata:
                        chunk_metadata["page"] = metadata["section_start_page"]
                    else:
                        chunk_metadata["page"] = min(start_page, end_page)
            
            chunks.append({
                "text": current_chunk,
                "metadata": chunk_metadata
            })
        elif current_chunk and chunks:
            # If we have a small leftover, append it to the previous chunk
            chunks[-1]["text"] += "\n\n" + current_chunk
            # Update the end page of the last chunk if needed
            if page_mapping:
                _, end_page = self._get_page_range(current_chunk, chunk_start_pos, page_mapping)
                if end_page is not None and "page_end" in chunks[-1]["metadata"]:
                    chunks[-1]["metadata"]["page_end"] = max(
                        chunks[-1]["metadata"]["page_end"], 
                        end_page
                    )
                elif end_page is not None and "page" in chunks[-1]["metadata"]:
                    # Convert from single page to page range if needed
                    start = chunks[-1]["metadata"]["page"]
                    if start != end_page:
                        del chunks[-1]["metadata"]["page"]
                        chunks[-1]["metadata"]["page_start"] = start
                        chunks[-1]["metadata"]["page_end"] = end_page
        
        return chunks
    
    def _extract_metadata(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract metadata from a document
        
        Args:
            document: Document to extract metadata from
            
        Returns:
            Dictionary with metadata
        """
        metadata = document["metadata"].copy()
        
        # Add section information
        if "sections" in document and document["sections"]:
            metadata["sections"] = [
                {
                    "title": section["title"],
                    "start_page": section.get("start_page"),
                    "end_page": section.get("end_page")
                }
                for section in document["sections"]
            ]
            metadata["section_count"] = len(document["sections"])
        
        # Add text statistics
        metadata["text_length"] = len(document["text"])
        metadata["word_count"] = len(document["text"].split())
        
        return metadata
    
    def export_to_markdown(self, document: Dict[str, Any], output_path: str) -> str:
        """
        Export a document to Markdown with page annotations
        
        Args:
            document: Document to export
            output_path: Path to save the Markdown file
            
        Returns:
            Path to the saved file
        """
        try:
            # Create output directory if it doesn't exist
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Generate Markdown
            markdown = f"# {document['metadata']['title']}\n\n"
            
            # Add metadata
            markdown += "## Metadata\n\n"
            for key, value in document["metadata"].items():
                if key != "title":
                    markdown += f"- **{key}**: {value}\n"
            markdown += "\n"
            
            # Add sections with page info
            if "sections" in document and document["sections"]:
                for section in document["sections"]:
                    page_info = ""
                    if "start_page" in section:
                        if section.get("start_page") == section.get("end_page"):
                            page_info = f" (Page {section['start_page']})"
                        else:
                            page_info = f" (Pages {section['start_page']}-{section['end_page']})"
                    
                    markdown += f"## {section['title']}{page_info}\n\n"
                    markdown += section["content"] + "\n\n"
            else:
                markdown += "## Content\n\n"
                markdown += document["text"] + "\n\n"
            
            # Save to file
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(markdown)
            
            logger.info(f"Exported document to Markdown: {output_path}")
            
            return output_path
            
        except Exception as e:
            logger.error(f"Error exporting to Markdown: {str(e)}")
            raise
    
    def save_chunks_to_json(self, chunks: List[Dict[str, Any]], output_path: str) -> str:
        """
        Save chunks to a JSON file
        
        Args:
            chunks: Chunks to save
            output_path: Path to save the JSON file
            
        Returns:
            Path to the saved file
        """
        try:
            # Create output directory if it doesn't exist
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Save to file
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(chunks, f, indent=2)
            
            logger.info(f"Saved {len(chunks)} chunks to JSON: {output_path}")
            
            return output_path
            
        except Exception as e:
            logger.error(f"Error saving chunks to JSON: {str(e)}")
            raise