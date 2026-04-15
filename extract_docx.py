#!/usr/bin/env python3
"""
Lightweight DOCX chunker using python-docx (no docling/ONNX required).
Produces the same _chunks.json format as extractor_docling.py.

Usage:
    python extract_docx.py "data/pilot_texts/Pilot texts 1 [Protected Areas].docx" \
        --output-dir data/extracted/pilot_texts
"""

import argparse
import json
import logging
import os
import re
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TARGET_CHARS = 4000   # target chunk size in characters (~1000 tokens)
MAX_CHARS    = 6000   # hard max before forced split

HEADING_STYLES = {"heading 1", "heading 2", "heading 3", "heading 4",
                  "heading 5", "heading 6", "title"}


def is_heading(para):
    return para.style.name.lower() in HEADING_STYLES


def extract_paragraphs(path: str):
    """Return list of (text, style_name, is_heading) for each non-empty paragraph."""
    from docx import Document
    doc = Document(path)
    result = []
    for p in doc.paragraphs:
        text = p.text.strip()
        if not text:
            continue
        result.append((text, p.style.name, p.style.name.lower() in HEADING_STYLES))
    return result, doc.core_properties


def build_chunks(paragraphs, source_path, title):
    """
    Group paragraphs into chunks of ~TARGET_CHARS, respecting section boundaries.
    Returns list of chunk dicts matching the extractor_docling output format.
    """
    chunks = []
    current_texts = []
    current_chars = 0
    current_section = "Introduction"
    chunk_number = 0

    def flush():
        nonlocal chunk_number, current_texts, current_chars
        if not current_texts:
            return
        text = "\n\n".join(current_texts)
        chunks.append({
            "text": text,
            "metadata": {
                "chunk_number": chunk_number + 1,
                "section_title": current_section,
                "source": source_path,
                "title": title,
                "type": "docx",
                "is_max_token_chunked": len(text) >= MAX_CHARS,
            }
        })
        chunk_number += 1
        current_texts = []
        current_chars = 0

    for text, style, heading in paragraphs:
        if heading:
            # Flush before starting a new section (if there's enough content)
            if current_chars >= TARGET_CHARS // 2:
                flush()
            current_section = text
            # Don't add heading-only paragraphs as standalone chunks;
            # carry the heading into the next chunk's text
            current_texts.append(text)
            current_chars += len(text)
            continue

        # If adding this paragraph would exceed MAX_CHARS, flush first
        if current_chars + len(text) > MAX_CHARS and current_chars > 0:
            flush()

        current_texts.append(text)
        current_chars += len(text)

        # Flush at natural break when we've hit the target size
        if current_chars >= TARGET_CHARS:
            flush()

    flush()  # final leftover
    return chunks


def main():
    parser = argparse.ArgumentParser(description="Chunk a DOCX file into JSON chunks")
    parser.add_argument("input", help="Path to .docx file")
    parser.add_argument("--output-dir", default="data/extracted/pilot_texts",
                        help="Directory for output JSON")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        logger.error("File not found: %s", args.input)
        sys.exit(1)

    os.makedirs(args.output_dir, exist_ok=True)

    logger.info("Extracting: %s", args.input)
    paragraphs, props = extract_paragraphs(args.input)

    try:
        title = props.title or os.path.splitext(os.path.basename(args.input))[0]
    except Exception:
        title = os.path.splitext(os.path.basename(args.input))[0]

    chunks = build_chunks(paragraphs, args.input, title)
    logger.info("Produced %d chunks", len(chunks))

    base = os.path.splitext(os.path.basename(args.input))[0]
    out_path = os.path.join(args.output_dir, f"{base}_chunks.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)
    logger.info("Saved: %s", out_path)

    # Also save metadata
    meta = {
        "source": args.input,
        "title": title,
        "type": "docx",
        "chunk_count": len(chunks),
        "paragraph_count": len(paragraphs),
    }
    meta_path = os.path.join(args.output_dir, f"{base}_metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    logger.info("Saved: %s", meta_path)


if __name__ == "__main__":
    main()
