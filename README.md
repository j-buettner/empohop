# Planetary Health Knowledge Graph Extraction

This project provides a comprehensive pipeline for extracting structured information about planetary health from academic documents and building a knowledge graph. It includes tools for document extraction, entity recognition, relationship extraction, human review, and visualization.

## Project Structure

```
.
├── data/                      # Data storage
│   ├── extracted/             # Extracted document chunks
│   ├── processed/             # Processed entities and relationships
│   └── review/                # Human review tasks and corrections
├── schema/                    # Schema definitions
│   ├── documentation/         # Schema documentation
│   ├── json-schema/           # JSON Schema definitions
│   └── neo4j/                 # Neo4j database schema
├── tools/                     # Utility tools
│   ├── data-entry/            # Data entry forms
│   ├── import-export/         # Import/export utilities
│   └── validation/            # Data validation tools
├── visualization/             # Visualization tools
│   ├── network/               # Network visualization
│   └── timeline/              # Timeline visualization
├── extractor.py               # Document extraction module
├── extraction_utils.py        # Extraction utilities
├── extract_document.py        # Document extraction script
├── llm_processor.py           # LLM-based entity extraction
├── human_review.py            # Human review interface
├── main.py                    # Main entry point
├── requirements.txt           # Project dependencies
└── setup.py                   # Package setup script
```

## Features

- **Document Extraction**: Extract text and metadata from PDF, DOCX, and other document formats
- **Entity Recognition**: Identify events, actors, concepts, publications, and locations
- **Relationship Extraction**: Detect relationships between entities
- **Human Review Interface**: Web-based interface for reviewing and correcting extracted information
- **Knowledge Graph Construction**: Build a knowledge graph from the extracted entities and relationships
- **Visualization**: Visualize the knowledge graph as a network or timeline

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/planetary-health-kg.git
   cd planetary-health-kg
   ```

2. Create a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Set up OpenAI API key:
   ```
   export OPENAI_API_KEY=your_api_key  # On Windows: set OPENAI_API_KEY=your_api_key
   ```

## Usage

### Document Extraction

Extract text and metadata from a document:

```
python extract_document.py path/to/document.pdf --output-dir data/extracted --analyze --extract-entities
```

### Entity Extraction with LLM

Process extracted chunks with an LLM to identify entities and relationships:

```
python llm_processor.py data/extracted/document_chunks.json --output-dir data/processed
```

### Human Review Interface

Start the human review interface:

```
python main.py --tasks-file data/review/review_tasks.json --output-dir data/review/corrected
```

Then open a web browser and navigate to http://localhost:8000 to access the interface.

### Viewing Visualizations

To view the visualizations (network graph and timeline), you need to run the included HTTP server to avoid CORS issues:

```
python server.py
```

Then open a web browser and navigate to http://localhost:8080 to access the visualizations. The server provides:

- Main interface: http://localhost:8080/index.html
- Network visualization: http://localhost:8080/visualization/network/index.html
- Timeline visualization: http://localhost:8080/visualization/timeline/index.html

The visualizations will load data from the processed directory, showing the extracted entities and relationships.

## Schema

The knowledge graph schema includes the following entity types:

- **Events**: Significant events in the planetary health movement
- **Actors**: Individuals, organizations, and institutions involved in planetary health
- **Concepts**: Theories, ideas, and frameworks related to planetary health
- **Publications**: Books, articles, reports, and other published materials
- **Locations**: Countries, cities, regions, and other geographical entities

Relationships between these entities capture the connections and interactions in the planetary health domain.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
