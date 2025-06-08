// Neo4j Relationship Types for Planetary Health Knowledge Graph
// This file defines the relationship types and their properties

// Event-to-Event Relationships
// Events can influence other events, precede them chronologically, etc.
MATCH (e1:Event), (e2:Event)
WHERE e1.id <> e2.id AND e1.year < e2.year
CREATE (e1)-[r:INFLUENCES {
  id: randomUUID(),
  strength: 3,
  description: "Example influence relationship",
  created_at: datetime()
}]->(e2);

// Actor-to-Event Relationships
// Actors participate in events, organize them, etc.
MATCH (a:Actor), (e:Event)
CREATE (a)-[r:PARTICIPATES_IN {
  id: randomUUID(),
  role: "Organizer",
  description: "Example participation relationship",
  created_at: datetime()
}]->(e);

// Location-to-Event Relationships
// Events take place at locations
MATCH (l:Location), (e:Event)
CREATE (e)-[r:TAKES_PLACE_AT {
  id: randomUUID(),
  description: "Example location relationship",
  created_at: datetime()
}]->(l);

// Concept-to-Event Relationships
// Events may introduce, develop, or apply concepts
MATCH (c:Concept), (e:Event)
CREATE (e)-[r:INTRODUCES {
  id: randomUUID(),
  description: "Example concept introduction relationship",
  created_at: datetime()
}]->(c);

// Publication-to-Event Relationships
// Events may result in publications or be documented by them
MATCH (p:Publication), (e:Event)
CREATE (p)-[r:DOCUMENTS {
  id: randomUUID(),
  description: "Example documentation relationship",
  created_at: datetime()
}]->(e);

// Actor-to-Actor Relationships
// Actors collaborate with, influence, or are affiliated with other actors
MATCH (a1:Actor), (a2:Actor)
WHERE a1.id <> a2.id
CREATE (a1)-[r:COLLABORATES_WITH {
  id: randomUUID(),
  start_date: date('2020-01-01'),
  description: "Example collaboration relationship",
  created_at: datetime()
}]->(a2);

// Actor-to-Concept Relationships
// Actors develop, advocate for, or criticize concepts
MATCH (a:Actor), (c:Concept)
CREATE (a)-[r:DEVELOPS {
  id: randomUUID(),
  description: "Example concept development relationship",
  created_at: datetime()
}]->(c);

// Actor-to-Publication Relationships
// Actors author or contribute to publications
MATCH (a:Actor), (p:Publication)
CREATE (a)-[r:AUTHORS {
  id: randomUUID(),
  role: "Lead Author",
  description: "Example authorship relationship",
  created_at: datetime()
}]->(p);

// Actor-to-Location Relationships
// Actors are based in or associated with locations
MATCH (a:Actor), (l:Location)
CREATE (a)-[r:BASED_IN {
  id: randomUUID(),
  start_date: date('2015-01-01'),
  description: "Example location association",
  created_at: datetime()
}]->(l);

// Concept-to-Concept Relationships
// Concepts relate to, build upon, or contradict other concepts
MATCH (c1:Concept), (c2:Concept)
WHERE c1.id <> c2.id
CREATE (c1)-[r:RELATES_TO {
  id: randomUUID(),
  relationship_type: "Builds Upon",
  description: "Example concept relationship",
  created_at: datetime()
}]->(c2);

// Publication-to-Publication Relationships
// Publications cite or build upon other publications
MATCH (p1:Publication), (p2:Publication)
WHERE p1.id <> p2.id AND p1.year > p2.year
CREATE (p1)-[r:CITES {
  id: randomUUID(),
  description: "Example citation relationship",
  created_at: datetime()
}]->(p2);

// Publication-to-Concept Relationships
// Publications discuss, introduce, or apply concepts
MATCH (p:Publication), (c:Concept)
CREATE (p)-[r:DISCUSSES {
  id: randomUUID(),
  significance: 4,
  description: "Example concept discussion relationship",
  created_at: datetime()
}]->(c);

// Location-to-Location Relationships
// Locations can contain other locations (e.g., a city is in a country)
MATCH (l1:Location), (l2:Location)
WHERE l1.id <> l2.id AND l1.type = 'Country' AND l2.type = 'City'
CREATE (l1)-[r:CONTAINS {
  id: randomUUID(),
  description: "Example location hierarchy relationship",
  created_at: datetime()
}]->(l2);

// Note: The above are example relationship creation statements
// In a real implementation, you would:
// 1. Not create relationships blindly between all matching nodes
// 2. Use actual data to determine which relationships should exist
// 3. Implement proper data loading procedures

// Relationship Type Summary (for reference):
// Event-Event: INFLUENCES, PRECEDES, FOLLOWS
// Actor-Event: PARTICIPATES_IN, ORGANIZES, ATTENDS
// Location-Event: TAKES_PLACE_AT
// Concept-Event: INTRODUCES, IS_APPLIED_IN
// Publication-Event: DOCUMENTS, RESULTS_FROM
// Actor-Actor: COLLABORATES_WITH, INFLUENCES, IS_AFFILIATED_WITH
// Actor-Concept: DEVELOPS, ADVOCATES_FOR, CRITICIZES
// Actor-Publication: AUTHORS, CONTRIBUTES_TO
// Actor-Location: BASED_IN, WORKS_IN
// Concept-Concept: RELATES_TO, BUILDS_UPON, CONTRADICTS
// Publication-Publication: CITES, BUILDS_UPON
// Publication-Concept: DISCUSSES, INTRODUCES, APPLIES
// Location-Location: CONTAINS, IS_PART_OF
