// =====================================================================
// TripGraph - delete ALL data. Constraints and indexes are kept.
// Run 02_sample_data.cypher again afterwards.
// =====================================================================

// STEP 1: Delete every node of the project and its relationships
MATCH (n)
WHERE n:Tourist OR n:Destination OR n:Attraction OR n:Category OR n:Hotel
DETACH DELETE n;
