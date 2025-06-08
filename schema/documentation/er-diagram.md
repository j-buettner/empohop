# Planetary Health Knowledge Graph: Entity-Relationship Diagram

This diagram illustrates the entities and relationships in the Planetary Health Knowledge Graph.

```mermaid
erDiagram
    EVENT {
        string id PK "UUID v4"
        int year "Required"
        string title "Required"
        string description "Required"
        int significance "1-5 scale"
        string type "Enum"
        date start_date "ISO 8601"
        date end_date "ISO 8601"
    }
    
    ACTOR {
        string id PK "UUID v4"
        string name "Required"
        string type "Required, Enum"
        string country "ISO 3166-1 alpha-2"
        string description "Bio/description"
        string role "Primary role"
        date start_date "Involvement start"
        date end_date "Involvement end"
    }
    
    LOCATION {
        string id PK "UUID v4"
        string name "Required"
        string type "Required, Enum"
        object coordinates "GeoJSON Point"
        string country "ISO 3166-1 alpha-2"
        string region "State/province"
        int geoname_id "GeoNames reference"
        string wikidata_id "Wikidata Q ID"
    }
    
    CONCEPT {
        string id PK "UUID v4"
        string name "Required"
        string definition "Required"
        array alternative_names "Synonyms"
        string parent_concept_id FK "Hierarchical parent"
        array domain "Field categories"
        int significance "1-5 scale"
        string wikidata_id "Wikidata Q ID"
    }
    
    PUBLICATION {
        string id PK "UUID v4"
        string title "Required"
        string subtitle "Optional"
        string type "Publication type"
        int year "Required"
        date date "Specific date"
        string publisher "Publisher name"
        string journal "For articles"
        string doi "Digital Object Identifier"
        string isbn "For books"
        string abstract "Summary"
    }
    
    ACTOR ||--o{ EVENT : "PARTICIPATES_IN"
    ACTOR ||--o{ PUBLICATION : "AUTHORS"
    ACTOR ||--o{ CONCEPT : "DEVELOPS"
    ACTOR ||--o{ ACTOR : "COLLABORATES_WITH"
    ACTOR }|--|| LOCATION : "BASED_IN"
    
    EVENT ||--o{ EVENT : "INFLUENCES"
    EVENT }|--|| LOCATION : "TAKES_PLACE_AT"
    EVENT ||--o{ CONCEPT : "INTRODUCES"
    
    PUBLICATION ||--o{ PUBLICATION : "CITES"
    PUBLICATION ||--o{ CONCEPT : "DISCUSSES"
    PUBLICATION ||--o{ EVENT : "DOCUMENTS"
    
    CONCEPT ||--o{ CONCEPT : "RELATES_TO"
    
    LOCATION ||--o{ LOCATION : "CONTAINS"
```

## Key Relationship Types

### Event Relationships
- **INFLUENCES**: An event influences another event
- **PRECEDES/FOLLOWS**: Chronological relationship between events
- **TAKES_PLACE_AT**: Event occurs at a location

### Actor Relationships
- **PARTICIPATES_IN**: Actor participates in an event
- **AUTHORS**: Actor authors a publication
- **DEVELOPS**: Actor develops a concept
- **COLLABORATES_WITH**: Actor collaborates with another actor
- **BASED_IN**: Actor is based in a location

### Publication Relationships
- **CITES**: Publication cites another publication
- **DISCUSSES**: Publication discusses a concept
- **DOCUMENTS**: Publication documents an event

### Concept Relationships
- **RELATES_TO**: Concept relates to another concept
- **BUILDS_UPON**: Concept builds upon another concept
- **CONTRADICTS**: Concept contradicts another concept

### Location Relationships
- **CONTAINS**: Location contains another location (e.g., country contains city)
