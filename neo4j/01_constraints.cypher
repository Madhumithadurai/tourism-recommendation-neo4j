// =====================================================================
// TripGraph - Tourism Recommendation System using Neo4j
// Script 01: uniqueness constraints and indexes (Neo4j 5.x). Safe to run again.
// =====================================================================

// STEP 1: Uniqueness constraints
// One unique key per label. Each constraint also creates an index used by MATCH and MERGE.
CREATE CONSTRAINT tourist_id IF NOT EXISTS FOR (t:Tourist) REQUIRE t.touristId IS UNIQUE;
CREATE CONSTRAINT destination_name IF NOT EXISTS FOR (d:Destination) REQUIRE d.name IS UNIQUE;
CREATE CONSTRAINT attraction_id IF NOT EXISTS FOR (a:Attraction) REQUIRE a.attractionId IS UNIQUE;
CREATE CONSTRAINT category_name IF NOT EXISTS FOR (c:Category) REQUIRE c.name IS UNIQUE;
CREATE CONSTRAINT hotel_id IF NOT EXISTS FOR (h:Hotel) REQUIRE h.hotelId IS UNIQUE;

// STEP 2: Extra indexes for lookups by name
CREATE INDEX attraction_name IF NOT EXISTS FOR (a:Attraction) ON (a.name);
CREATE INDEX hotel_band IF NOT EXISTS FOR (h:Hotel) ON (h.priceBand);
