# Planetary Health Knowledge Graph: Schema Guide

This guide provides comprehensive documentation for the Planetary Health Knowledge Graph schema, including entity definitions, relationship types, data validation rules, and usage examples.

## Table of Contents

1. [Introduction](#introduction)
2. [Entity Types](#entity-types)
3. [Relationship Types](#relationship-types)
4. [Data Validation](#data-validation)
5. [Identifiers and References](#identifiers-and-references)
6. [Querying Examples](#querying-examples)
7. [Data Entry Guidelines](#data-entry-guidelines)
8. [Schema Evolution](#schema-evolution)

## Introduction

The Planetary Health Knowledge Graph is designed to capture and represent the complex relationships between events, actors, locations, concepts, and publications in the planetary health movement. This schema enables:

- Tracking the historical development of planetary health concepts and practices
- Identifying key influencers and their relationships
- Mapping geographical patterns in planetary health activities
- Analyzing citation networks and concept evolution
- Discovering connections between seemingly disparate events and ideas

## Entity Types

### Event

Events represent significant occurrences in the planetary health movement, such as conferences, policy adoptions, research milestones, or organizational formations.

**Key Properties:**
- `id`: Unique identifier (UUID v4)
- `year`: Year when the event occurred (required)
- `title`: Short descriptive title (required)
- `description`: Detailed description (required)
- `significance`: Importance rating (1-5 scale)
- `type`: Categorization (Publication, Conference, Policy, Research, etc.)
- `start_date`/`end_date`: Specific dates (ISO 8601 format)

**Usage Notes:**
- Events should be discrete, identifiable occurrences
- The `year` property is required for chronological ordering
- Use `significance` to indicate the event's impact on planetary health

### Actor

Actors represent individuals, organizations, institutions, or other entities that participate in the planetary health movement.

**Key Properties:**
- `id`: Unique identifier (UUID v4)
- `name`: Full name (required)
- `type`: Actor type (Individual, Institution, Government, NGO, etc.) (required)
- `country`: ISO 3166-1 alpha-2 country code
- `description`: Biographical information
- `role`: Primary role in planetary health
- `affiliation_ids`: References to other affiliated actors

**Usage Notes:**
- Use standardized naming conventions for consistency
- Link to external identifiers (ORCID, GRID, ROR) when available
- Capture hierarchical relationships through affiliations

### Location

Locations represent geographical places relevant to planetary health events and activities.

**Key Properties:**
- `id`: Unique identifier (UUID v4)
- `name`: Location name (required)
- `type`: Location type (City, Country, Region, etc.) (required)
- `coordinates`: GeoJSON Point format [longitude, latitude]
- `country`: ISO 3166-1 alpha-2 country code
- `geoname_id`: GeoNames database identifier

**Usage Notes:**
- Use standardized geographical references (GeoNames, Wikidata)
- Capture hierarchical relationships (e.g., city within country)
- Include environmental features relevant to planetary health

### Concept

Concepts represent theories, ideas, frameworks, or terms relevant to planetary health.

**Key Properties:**
- `id`: Unique identifier (UUID v4)
- `name`: Concept name (required)
- `definition`: Definition or explanation (required)
- `alternative_names`: Synonyms or alternative terms
- `parent_concept_id`: Reference to parent concept
- `domain`: Field categories (Ecology, PublicHealth, etc.)
- `significance`: Importance rating (1-5 scale)

**Usage Notes:**
- Organize concepts hierarchically when appropriate
- Document the evolution of concepts over time
- Link concepts to their key proponents and publications

### Publication

Publications represent books, articles, reports, or other published materials relevant to planetary health.

**Key Properties:**
- `id`: Unique identifier (UUID v4)
- `title`: Publication title (required)
- `type`: Publication type (Journal Article, Book, Report, etc.)
- `year`: Publication year (required)
- `author_ids`: References to actor IDs
- `doi`: Digital Object Identifier
- `isbn`: International Standard Book Number
- `abstract`: Summary of the publication

**Usage Notes:**
- Use standard identifiers (DOI, ISBN) when available
- Capture citation relationships between publications
- Link publications to the concepts they discuss and events they document

## Relationship Types

Relationships connect entities in the knowledge graph, representing how they interact, influence, or relate to each other.

### Event Relationships

- **INFLUENCES**: An event influences another event
  - Properties: strength, description
  - Example: `(Climate_Paris_Agreement)-[:INFLUENCES]->(WHO_Planetary_Health_Initiative)`

- **PRECEDES/FOLLOWS**: Chronological relationship between events
  - Properties: time_gap (in years)
  - Example: `(First_Planetary_Health_Conference)-[:PRECEDES]->(Second_Planetary_Health_Conference)`

- **TAKES_PLACE_AT**: Event occurs at a location
  - Properties: description
  - Example: `(Lancet_Commission_Formation)-[:TAKES_PLACE_AT]->(London)`

### Actor Relationships

- **PARTICIPATES_IN**: Actor participates in an event
  - Properties: role, description
  - Example: `(WHO)-[:PARTICIPATES_IN {role: "Organizer"}]->(Global_Health_Summit)`

- **AUTHORS**: Actor authors a publication
  - Properties: role (Lead Author, Contributor, etc.)
  - Example: `(Jane_Smith)-[:AUTHORS {role: "Lead Author"}]->(Planetary_Boundaries_Paper)`

- **DEVELOPS**: Actor develops a concept
  - Properties: description, year
  - Example: `(Rockefeller_Foundation)-[:DEVELOPS]->(Planetary_Health_Concept)`

- **COLLABORATES_WITH**: Actor collaborates with another actor
  - Properties: start_date, end_date, description
  - Example: `(Harvard_University)-[:COLLABORATES_WITH]->(London_School_Hygiene)`

### Publication Relationships

- **CITES**: Publication cites another publication
  - Properties: context, page_number
  - Example: `(Recent_Climate_Paper)-[:CITES]->(Original_Planetary_Boundaries_Paper)`

- **DISCUSSES**: Publication discusses a concept
  - Properties: significance, context
  - Example: `(Lancet_Report)-[:DISCUSSES {significance: 5}]->(One_Health_Approach)`

### Concept Relationships

- **RELATES_TO**: Concept relates to another concept
  - Properties: relationship_type, description
  - Example: `(Planetary_Boundaries)-[:RELATES_TO {relationship_type: "Builds Upon"}]->(Sustainability)`

## Data Validation

The schema includes validation rules to ensure data quality and consistency:

### Required Properties

- Events: id, year, title, description
- Actors: id, name, type
- Locations: id, name, type
- Concepts: id, name, definition
- Publications: id, title, year

### Value Constraints

- Years must be between 1800 and 2100
- Significance ratings must be between 1 and 5
- Country codes must follow ISO 3166-1 alpha-2 format
- Coordinates must follow GeoJSON Point format

### Referential Integrity

- All referenced IDs must exist in the database
- Relationship endpoints must be of the correct entity types
- Hierarchical references must not create cycles

## Identifiers and References

### UUID Generation

All entities use UUID v4 identifiers to ensure global uniqueness. Generate these using standard UUID libraries:

```python
import uuid
entity_id = str(uuid.uuid4())
```

### External Identifiers

Link to standardized external identifiers whenever possible:

- Actors: ORCID (individuals), GRID/ROR (institutions), Wikidata QIDs
- Locations: GeoNames IDs, Wikidata QIDs
- Publications: DOIs, ISBNs, ISSNs
- Concepts: Wikidata QIDs

## Querying Examples

### Neo4j Cypher Queries

**Find events influenced by a specific event:**

```cypher
MATCH (e:Event {title: "Lancet Commission on Planetary Health"})-[:INFLUENCES]->(influenced:Event)
RETURN influenced.title, influenced.year, influenced.significance
ORDER BY influenced.year;
```

**Find key actors in the development of a concept:**

```cypher
MATCH (a:Actor)-[:DEVELOPS]->(c:Concept {name: "Planetary Health"})
RETURN a.name, a.type, a.country
ORDER BY a.significance DESC;
```

**Find the evolution of a concept over time:**

```cypher
MATCH (e:Event)-[:INTRODUCES]->(c:Concept {name: "Planetary Boundaries"})
WITH c, e ORDER BY e.year ASC LIMIT 1
MATCH path = (e)-[:PRECEDES*]->(later:Event)-[:DISCUSSES]->(c)
RETURN path
LIMIT 10;
```

## Data Entry Guidelines

### Best Practices

1. **Consistency**: Use consistent naming conventions and formatting
2. **Completeness**: Fill in all relevant fields, not just required ones
3. **Precision**: Be specific in descriptions and relationship characterizations
4. **Evidence**: Include sources and citations for all information
5. **Neutrality**: Maintain objective descriptions, especially for significance ratings

### Workflow

1. Start by entering foundational entities (major events, key actors, core concepts)
2. Add relationships between existing entities
3. Expand with more specific or peripheral entities
4. Continuously review and refine the knowledge graph

## Schema Evolution

The schema may evolve over time to accommodate new requirements:

1. **Backward Compatibility**: Changes should maintain compatibility with existing data
2. **Versioning**: Major schema changes should be versioned
3. **Documentation**: All changes must be documented
4. **Migration**: Provide migration scripts for significant changes

---

This guide is a living document and will be updated as the schema evolves and as best practices emerge from its use.
