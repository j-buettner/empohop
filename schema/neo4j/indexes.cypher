// Neo4j Indexes for Planetary Health Knowledge Graph
// These indexes improve query performance for frequently accessed properties

// Event Indexes
CREATE INDEX event_year_index IF NOT EXISTS FOR (e:Event) ON (e.year);
CREATE INDEX event_type_index IF NOT EXISTS FOR (e:Event) ON (e.type);
CREATE INDEX event_significance_index IF NOT EXISTS FOR (e:Event) ON (e.significance);
CREATE INDEX event_title_index IF NOT EXISTS FOR (e:Event) ON (e.title);

// Actor Indexes
CREATE INDEX actor_name_index IF NOT EXISTS FOR (a:Actor) ON (a.name);
CREATE INDEX actor_type_index IF NOT EXISTS FOR (a:Actor) ON (a.type);
CREATE INDEX actor_country_index IF NOT EXISTS FOR (a:Actor) ON (a.country);
CREATE INDEX actor_role_index IF NOT EXISTS FOR (a:Actor) ON (a.role);

// Location Indexes
CREATE INDEX location_name_index IF NOT EXISTS FOR (l:Location) ON (l.name);
CREATE INDEX location_type_index IF NOT EXISTS FOR (l:Location) ON (l.type);
CREATE INDEX location_country_index IF NOT EXISTS FOR (l:Location) ON (l.country);
CREATE INDEX location_geoname_id_index IF NOT EXISTS FOR (l:Location) ON (l.geoname_id);

// Concept Indexes
CREATE INDEX concept_name_index IF NOT EXISTS FOR (c:Concept) ON (c.name);
CREATE INDEX concept_domain_index IF NOT EXISTS FOR (c:Concept) ON (c.domain);
CREATE INDEX concept_significance_index IF NOT EXISTS FOR (c:Concept) ON (c.significance);

// Publication Indexes
CREATE INDEX publication_title_index IF NOT EXISTS FOR (p:Publication) ON (p.title);
CREATE INDEX publication_year_index IF NOT EXISTS FOR (p:Publication) ON (p.year);
CREATE INDEX publication_type_index IF NOT EXISTS FOR (p:Publication) ON (p.type);
CREATE INDEX publication_doi_index IF NOT EXISTS FOR (p:Publication) ON (p.doi);
CREATE INDEX publication_isbn_index IF NOT EXISTS FOR (p:Publication) ON (p.isbn);
CREATE INDEX publication_publisher_index IF NOT EXISTS FOR (p:Publication) ON (p.publisher);
CREATE INDEX publication_journal_index IF NOT EXISTS FOR (p:Publication) ON (p.journal);

// Full-text indexes for text search capabilities
// Note: These require Neo4j Enterprise Edition or newer Community versions

// Full-text search on event titles and descriptions
CREATE FULLTEXT INDEX event_fulltext_index IF NOT EXISTS
FOR (e:Event) ON EACH [e.title, e.description];

// Full-text search on actor names and descriptions
CREATE FULLTEXT INDEX actor_fulltext_index IF NOT EXISTS
FOR (a:Actor) ON EACH [a.name, a.description];

// Full-text search on concept names and definitions
CREATE FULLTEXT INDEX concept_fulltext_index IF NOT EXISTS
FOR (c:Concept) ON EACH [c.name, c.definition];

// Full-text search on publication titles and abstracts
CREATE FULLTEXT INDEX publication_fulltext_index IF NOT EXISTS
FOR (p:Publication) ON EACH [p.title, p.abstract];

// Composite indexes for common query patterns

// Events by year and type
CREATE INDEX event_year_type_index IF NOT EXISTS
FOR (e:Event) ON (e.year, e.type);

// Publications by year and type
CREATE INDEX publication_year_type_index IF NOT EXISTS
FOR (p:Publication) ON (p.year, p.type);

// Actors by type and country
CREATE INDEX actor_type_country_index IF NOT EXISTS
FOR (a:Actor) ON (a.type, a.country);
