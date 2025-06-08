// Neo4j Constraints for Planetary Health Knowledge Graph
// These constraints ensure data integrity and uniqueness

// Event Constraints
CREATE CONSTRAINT event_id_unique IF NOT EXISTS
FOR (e:Event) REQUIRE e.id IS UNIQUE;

CREATE CONSTRAINT event_id_exists IF NOT EXISTS
FOR (e:Event) REQUIRE e.id IS NOT NULL;

CREATE CONSTRAINT event_year_exists IF NOT EXISTS
FOR (e:Event) REQUIRE e.year IS NOT NULL;

CREATE CONSTRAINT event_title_exists IF NOT EXISTS
FOR (e:Event) REQUIRE e.title IS NOT NULL;

// Actor Constraints
CREATE CONSTRAINT actor_id_unique IF NOT EXISTS
FOR (a:Actor) REQUIRE a.id IS UNIQUE;

CREATE CONSTRAINT actor_id_exists IF NOT EXISTS
FOR (a:Actor) REQUIRE a.id IS NOT NULL;

CREATE CONSTRAINT actor_name_exists IF NOT EXISTS
FOR (a:Actor) REQUIRE a.name IS NOT NULL;

CREATE CONSTRAINT actor_type_exists IF NOT EXISTS
FOR (a:Actor) REQUIRE a.type IS NOT NULL;

// Location Constraints
CREATE CONSTRAINT location_id_unique IF NOT EXISTS
FOR (l:Location) REQUIRE l.id IS UNIQUE;

CREATE CONSTRAINT location_id_exists IF NOT EXISTS
FOR (l:Location) REQUIRE l.id IS NOT NULL;

CREATE CONSTRAINT location_name_exists IF NOT EXISTS
FOR (l:Location) REQUIRE l.name IS NOT NULL;

CREATE CONSTRAINT location_type_exists IF NOT EXISTS
FOR (l:Location) REQUIRE l.type IS NOT NULL;

// Concept Constraints
CREATE CONSTRAINT concept_id_unique IF NOT EXISTS
FOR (c:Concept) REQUIRE c.id IS UNIQUE;

CREATE CONSTRAINT concept_id_exists IF NOT EXISTS
FOR (c:Concept) REQUIRE c.id IS NOT NULL;

CREATE CONSTRAINT concept_name_exists IF NOT EXISTS
FOR (c:Concept) REQUIRE c.name IS NOT NULL;

CREATE CONSTRAINT concept_definition_exists IF NOT EXISTS
FOR (c:Concept) REQUIRE c.definition IS NOT NULL;

// Publication Constraints
CREATE CONSTRAINT publication_id_unique IF NOT EXISTS
FOR (p:Publication) REQUIRE p.id IS UNIQUE;

CREATE CONSTRAINT publication_id_exists IF NOT EXISTS
FOR (p:Publication) REQUIRE p.id IS NOT NULL;

CREATE CONSTRAINT publication_title_exists IF NOT EXISTS
FOR (p:Publication) REQUIRE p.title IS NOT NULL;

CREATE CONSTRAINT publication_year_exists IF NOT EXISTS
FOR (p:Publication) REQUIRE p.year IS NOT NULL;

// Optional: DOI uniqueness (if available)
CREATE CONSTRAINT publication_doi_unique IF NOT EXISTS
FOR (p:Publication) REQUIRE p.doi IS UNIQUE;

// Optional: ISBN uniqueness (if available)
CREATE CONSTRAINT publication_isbn_unique IF NOT EXISTS
FOR (p:Publication) REQUIRE p.isbn IS UNIQUE;

// Relationship Constraints
// Note: Neo4j doesn't support constraints on relationship properties in the same way as node properties
// But we can create constraints on composite relationship properties in newer versions

// Comment out if using Neo4j < 4.4
CREATE CONSTRAINT relationship_id_unique IF NOT EXISTS
FOR ()-[r:RELATES_TO]-() REQUIRE r.id IS UNIQUE;
