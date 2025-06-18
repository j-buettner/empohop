# Planetary Health Knowledge Graph Extraction

This project provides a comprehensive pipeline for extracting structured information about planetary health from academic documents and building a knowledge graph. It includes tools for document extraction, entity recognition with advanced disambiguation, relationship extraction, human review, and visualization.

## Project Structure

```
.
├── data/                      # Data storage
│   ├── extracted/             # Extracted document chunks
│   ├── processed/             # Processed entities and relationships
│   ├── review/                # Human review tasks and corrections
│   └── critic_results/        # Critic system assessment results
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
├── entity_resolver.py         # Advanced entity resolution and disambiguation
├── relationship_processor.py  # Relationship extraction and processing
├── human_review.py            # Human review interface
├── main.py                    # Main entry point
├── requirements.txt           # Project dependencies
└── setup.py                   # Package setup script
```

## Features

- **Document Extraction**: Extract text and metadata from PDF, DOCX, and other document formats
- **Entity Recognition**: Identify events, actors, concepts, publications, and locations with supporting text evidence
- **Advanced Entity Resolution**: 
  - Fuzzy matching for entity disambiguation
  - Abbreviation and acronym detection
  - Manual mapping support for known variations
  - Detailed disambiguation reports
- **Relationship Extraction**: Detect and validate relationships between entities
- **Human Review Interface**: Web-based interface for reviewing and correcting extracted information
- **Knowledge Graph Construction**: Build a knowledge graph from the extracted entities and relationships
- **Visualization**: Visualize the knowledge graph as a network or timeline
- **Quality Assessment**: Integration with critic system for extraction quality evaluation

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/planetary-health-kg.git
   cd planetary-health-kg
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up API keys:
   ```bash
   # For Anthropic Claude (primary LLM)
   export ANTHROPIC_API_KEY=your_api_key  # On Windows: set ANTHROPIC_API_KEY=your_api_key
   
   # For OpenAI (optional, for fallback)
   export OPENAI_API_KEY=your_api_key  # On Windows: set OPENAI_API_KEY=your_api_key
   ```

## Usage

### Document Extraction

Extract text and metadata from a document:

```bash
python extract_document.py path/to/document.pdf --output-dir data/extracted --analyze --extract-entities
```

### Entity Extraction with LLM

Process extracted chunks with an LLM to identify entities and relationships:

```bash
# Basic usage
python llm_processor.py data/extracted/document_chunks.json --output-dir data/processed

# With specific entity types
python llm_processor.py data/extracted/document_chunks.json \
  --entity-types event actor concept \
  --output-dir data/processed

# With manual entity mappings
python llm_processor.py data/extracted/document_chunks.json \
  --manual-mappings mappings/planetary_health_mappings.json \
  --output-dir data/processed

# Using built-in example mappings
python llm_processor.py data/extracted/document_chunks.json \
  --use-example-mappings \
  --output-dir data/processed

# Process specific chunks
python llm_processor.py data/extracted/document_chunks.json \
  --chunk-range 0-10 \
  --output-dir data/processed

# Without disambiguation report
python llm_processor.py data/extracted/document_chunks.json \
  --no-disambiguation-report \
  --output-dir data/processed
```

### Entity Resolution and Manual Mappings

Create a template for manual entity mappings:

```bash
python -c "from entity_resolver import create_manual_mappings_template; create_manual_mappings_template()"
```

Edit the generated `manual_mappings_template.json` to add your custom mappings:

```json
{
  "event": {
    "Rio Summit": "United Nations Conference on Environment and Development",
    "Earth Summit": "United Nations Conference on Environment and Development"
  },
  "actor": {
    "WHO": "World Health Organization",
    "UN": "United Nations"
  }
}
```

### Reviewing Disambiguation Reports

After processing, review the disambiguation report to understand how entities were merged:

```bash
# View summary statistics
cat data/processed/document_disambiguation_report.json | jq '.summary'

# Find low-confidence merges
cat data/processed/document_disambiguation_report.json | jq '.merges[] | select(.confidence < 0.8)'

# See entities that were manually mapped
cat data/processed/document_disambiguation_report.json | jq '.merges[] | select(.manual_mappings | length > 0)'
```

### Human Review Interface

Start the human review interface:

```bash
python main.py --tasks-file data/review/review_tasks.json --output-dir data/review/corrected
```

Then open a web browser and navigate to http://localhost:8000 to access the interface.

### Viewing Visualizations

To view the visualizations (network graph and timeline), run the included HTTP server:

```bash
python server.py
```

Then open a web browser and navigate to http://localhost:8080 to access:
- Main interface: http://localhost:8080/index.html
- Network visualization: http://localhost:8080/visualization/network/index.html
- Timeline visualization: http://localhost:8080/visualization/timeline/index.html

### Critic Assessment

Run the critic system to assess extraction quality:

```bash
python run_critic.py data/processed/your_knowledge_graph.json
```

The visualizations support displaying critic assessments:
- Toggle "Show Critic Assessments" to display quality indicators
- Entities are color-coded by extraction quality (Excellent, Good, Fair, Poor)
- Detailed assessments appear in entity detail panels

## Schema

The knowledge graph schema includes the following entity types:

- **Events**: Significant events in the planetary health movement
  - Title, year, description, type, significance, dates, locations, actors, concepts
- **Actors**: Individuals, organizations, and institutions involved in planetary health
  - Name, type, description, role, country, expertise, affiliations
- **Concepts**: Theories, ideas, and frameworks related to planetary health
  - Name, definition, alternative names, domain, significance, related concepts
- **Publications**: Books, articles, reports, and other published materials
  - Title, type, year, authors, publisher, identifier, abstract, significance
- **Locations**: Countries, cities, regions, and other geographical entities
  - Name, type, country, description, significance

All entities include:
- Supporting text evidence from source documents
- Source chunk references
- Unique identifiers
- Merge confidence scores (when applicable)

Relationships between entities capture connections and interactions in the planetary health domain.

## Advanced Features

### Entity Resolution

The system uses advanced entity resolution techniques:
- **Fuzzy String Matching**: Handles spelling variations and typos
- **Abbreviation Detection**: Recognizes acronyms and common abbreviations
- **Context-Aware Disambiguation**: Uses supporting text to verify matches
- **Type-Specific Rules**: Different matching strategies for different entity types
- **Confidence Scoring**: Tracks merge confidence for quality assurance

### Relationship Processing

The relationship extraction includes:
- Multi-phase extraction process
- Entity-relationship resolution
- Relationship deduplication
- Supporting text evidence for all relationships

### Quality Assurance

- Disambiguation reports for all entity merges
- Critic system integration for quality assessment
- Human review interface for corrections
- Validation tools for data consistency

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.