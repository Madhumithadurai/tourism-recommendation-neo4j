"""All Cypher queries used by the app, grouped by section.

Parameters ($name) are passed to Neo4j. Two placeholders are written into the text after validation,
because Cypher cannot take them as parameters:
  {maxHops}  the upper bound of a variable-length pattern (*1..k), 1-6
  {metric}   the ROUTE property to optimise: hours, distanceKm or costInr
$hidden is used only by the evaluation (leave-one-out): that one visit is treated as unknown.
neo4j/03_queries.cypher is generated from this file.
"""

QUERIES = [
    # =========================================================== Model & data
    {"id": "schema", "section": "model", "title": "How the labels are connected", "params": [], "concept": "Schema",
     "cypher": """MATCH (a)-[r]->(b)
RETURN labels(a)[0] AS fromLabel, type(r) AS relationship, labels(b)[0] AS toLabel, count(*) AS count
ORDER BY count DESC""",
     "explain": ["Groups every relationship by the labels at both ends: the schema the data really has."]},
    {"id": "counts", "section": "model", "title": "Nodes per label", "params": [], "concept": "Labels",
     "cypher": """MATCH (n)
RETURN labels(n)[0] AS label, count(*) AS nodes
ORDER BY nodes DESC""",
     "explain": ["A quick check after loading the sample data."]},

    # =========================================================== Destination discovery
    {"id": "by_category", "section": "discover", "title": "Destinations for an interest", "params": ["category"], "concept": "2-hop pattern",
     "cypher": """MATCH (c:Category {name: $category})<-[:HAS_CATEGORY]-(a:Attraction)-[:LOCATED_IN]->(d:Destination)
RETURN d.name AS destination, d.state AS state, count(a) AS attractions,
       collect(a.name) AS examples, round(avg(a.rating), 2) AS avgRating
ORDER BY attractions DESC, avgRating DESC""",
     "graph": """MATCH p = (c:Category {name: $category})<-[:HAS_CATEGORY]-(:Attraction)-[:LOCATED_IN]->(:Destination)
RETURN p""",
     "explain": ["Start at the Category node and walk to attractions, then to their destinations.",
                 "count() and avg() summarise each destination."]},
    {"id": "two_categories", "section": "discover", "title": "Destinations that offer two interests at once", "params": ["category", "category2"], "concept": "Pattern intersection",
     "cypher": """MATCH (d:Destination)<-[:LOCATED_IN]-(a1:Attraction)-[:HAS_CATEGORY]->(:Category {name: $category})
MATCH (d)<-[:LOCATED_IN]-(a2:Attraction)-[:HAS_CATEGORY]->(:Category {name: $category2})
RETURN d.name AS destination, collect(DISTINCT a1.name) AS forFirstInterest,
       collect(DISTINCT a2.name) AS forSecondInterest""",
     "graph": """MATCH p1 = (d:Destination)<-[:LOCATED_IN]-(:Attraction)-[:HAS_CATEGORY]->(:Category {name: $category})
MATCH p2 = (d)<-[:LOCATED_IN]-(:Attraction)-[:HAS_CATEGORY]->(:Category {name: $category2})
RETURN p1, p2""",
     "explain": ["Two MATCH clauses share the variable d, so a destination must satisfy both patterns."]},
    {"id": "in_season", "section": "discover", "title": "Destinations in season for a month", "params": ["month"], "concept": "List property",
     "cypher": """MATCH (d:Destination)
WHERE $month IN d.bestMonths
OPTIONAL MATCH (a:Attraction)-[:LOCATED_IN]->(d)
RETURN d.name AS destination, d.state AS state, count(a) AS attractions,
       round(avg(a.rating), 2) AS avgRating
ORDER BY avgRating DESC, attractions DESC""",
     "explain": ["bestMonths is a list property, and IN tests membership.",
                 "OPTIONAL MATCH keeps destinations even without attractions."]},
    {"id": "destination_profile", "section": "discover", "title": "Attractions in a destination", "params": ["destination"], "concept": "Neighbourhood",
     "cypher": """MATCH (a:Attraction)-[:LOCATED_IN]->(d:Destination {name: $destination})
OPTIONAL MATCH (a)-[:HAS_CATEGORY]->(c:Category)
RETURN a.name AS attraction, collect(c.name) AS categories, a.rating AS rating,
       a.entryFeeInr AS entryFeeInr, a.visitHours AS visitHours
ORDER BY rating DESC""",
     "graph": """MATCH p = (:Category)<-[:HAS_CATEGORY]-(:Attraction)-[:LOCATED_IN]->(d:Destination {name: $destination})
RETURN p""",
     "explain": ["collect() gathers all categories of an attraction into one list."]},
    {"id": "hotels", "section": "discover", "title": "Hotels in a destination for a budget", "params": ["destination", "budget"], "concept": "Filtering",
     "cypher": """MATCH (h:Hotel)-[:LOCATED_IN]->(d:Destination {name: $destination})
WHERE $budget = 'any' OR h.priceBand = $budget
OPTIONAL MATCH (h)<-[s:STAYED_AT]-(:Tourist)
RETURN h.name AS hotel, h.stars AS stars, h.priceBand AS band, h.pricePerNight AS pricePerNight,
       h.rating AS rating, count(s) AS stays, round(avg(s.rating), 1) AS guestRating
ORDER BY rating DESC""",
     "explain": ["The WHERE clause makes the budget filter optional ('any')."]},
    {"id": "top_in_category", "section": "discover", "title": "Top attractions for an interest", "params": ["category"], "concept": "Ranking",
     "cypher": """MATCH (a:Attraction)-[:HAS_CATEGORY]->(:Category {name: $category})
MATCH (a)-[:LOCATED_IN]->(d:Destination)
OPTIONAL MATCH (a)<-[v:VISITED]-(:Tourist)
RETURN a.name AS attraction, d.name AS destination, a.rating AS rating,
       count(v) AS visits, round(avg(v.rating), 1) AS touristRating
ORDER BY rating DESC, visits DESC
LIMIT 10""",
     "explain": ["Combines the published rating with how often tourists visited and how they rated it."]},
    {"id": "hidden_gems", "section": "discover", "title": "Hidden gems: highly rated, rarely visited", "params": [], "concept": "Filter on aggregate",
     "cypher": """MATCH (a:Attraction)-[:LOCATED_IN]->(d:Destination)
OPTIONAL MATCH (a)<-[v:VISITED]-(:Tourist)
WITH a, d, count(v) AS visits
WHERE a.rating >= 4.4 AND visits <= 1
RETURN a.name AS attraction, d.name AS destination, a.rating AS rating, visits
ORDER BY rating DESC, attraction""",
     "explain": ["WITH ... WHERE filters on an aggregated value (like HAVING in SQL)."]},

    # =========================================================== Routes and connections
    {"id": "direct_routes", "section": "routes", "title": "Direct connections from a destination", "params": ["from"], "concept": "1 hop, parallel relationships",
     "cypher": """MATCH (a:Destination {name: $from})-[r:ROUTE]-(b:Destination)
RETURN b.name AS to, r.mode AS mode, r.distanceKm AS km, r.hours AS hours, r.costInr AS costInr,
       coalesce(r.closed, false) AS closed, coalesce(r.trafficFactor, 1.0) AS trafficFactor
ORDER BY hours""",
     "graph": """MATCH p = (a:Destination {name: $from})-[:ROUTE]-(:Destination)
RETURN p""",
     "explain": ["ROUTE is stored once and matched without an arrow, so it works in both directions.",
                 "closed and trafficFactor are set by the Route Lab when a scenario is saved to Neo4j.",
                 "Two places can be joined by several ROUTEs, one per mode (road, rail, flight)."]},
    {"id": "fewest_stops", "section": "routes", "title": "Route with the fewest stops", "params": ["from", "to"], "concept": "shortestPath",
     "cypher": """MATCH (a:Destination {name: $from}), (b:Destination {name: $to})
MATCH p = shortestPath((a)-[:ROUTE*..12]-(b))
WHERE all(r IN relationships(p) WHERE NOT coalesce(r.closed, false))
RETURN [n IN nodes(p) | n.name] AS stops, length(p) AS legs,
       [r IN relationships(p) | r.mode] AS modes,
       reduce(h = 0.0, r IN relationships(p) | h + r.hours * coalesce(r.trafficFactor, 1.0)) AS hours,
       reduce(k = 0, r IN relationships(p) | k + r.distanceKm) AS km""",
     "graph": """MATCH (a:Destination {name: $from}), (b:Destination {name: $to})
MATCH p = shortestPath((a)-[:ROUTE*..12]-(b))
WHERE all(r IN relationships(p) WHERE NOT coalesce(r.closed, false))
RETURN p""",
     "explain": ["shortestPath() minimises the number of legs (breadth-first search), not the hours.",
                 "reduce() adds up hours and kilometres along the path."]},
    {"id": "all_fewest_stops", "section": "routes", "title": "All routes with the fewest stops", "params": ["from", "to"], "concept": "allShortestPaths",
     "cypher": """MATCH (a:Destination {name: $from}), (b:Destination {name: $to})
MATCH p = allShortestPaths((a)-[:ROUTE*..12]-(b))
WHERE all(r IN relationships(p) WHERE NOT coalesce(r.closed, false))
RETURN [n IN nodes(p) | n.name] AS stops, [r IN relationships(p) | r.mode] AS modes,
       reduce(h = 0.0, r IN relationships(p) | h + r.hours * coalesce(r.trafficFactor, 1.0)) AS hours
ORDER BY hours""",
     "graph": """MATCH (a:Destination {name: $from}), (b:Destination {name: $to})
MATCH p = allShortestPaths((a)-[:ROUTE*..12]-(b))
WHERE all(r IN relationships(p) WHERE NOT coalesce(r.closed, false))
RETURN p""",
     "explain": ["Every path of the minimum length is returned, including the same towns by a different mode."]},
    {"id": "best_routes", "section": "routes", "title": "Best alternative routes by hours, distance or cost", "params": ["from", "to", "maxHops", "metric", "modes"], "concept": "Weighted paths",
     "cypher": """MATCH p = (a:Destination {name: $from})-[:ROUTE*1..{maxHops}]-(b:Destination {name: $to})
WHERE all(n IN nodes(p) WHERE single(m IN nodes(p) WHERE m = n))
  AND all(r IN relationships(p) WHERE r.mode IN $modes AND NOT coalesce(r.closed, false))
WITH p, reduce(t = 0.0, r IN relationships(p) | t + r.{metric} * CASE WHEN '{metric}' = 'hours' THEN coalesce(r.trafficFactor, 1.0) ELSE 1.0 END) AS total
RETURN [n IN nodes(p) | n.name] AS stops, [r IN relationships(p) | r.mode] AS modes,
       length(p) AS legs, round(total, 2) AS total,
       reduce(h = 0.0, r IN relationships(p) | h + r.hours * coalesce(r.trafficFactor, 1.0)) AS hours,
       reduce(k = 0, r IN relationships(p) | k + r.distanceKm) AS km,
       reduce(c = 0, r IN relationships(p) | c + r.costInr) AS costInr
ORDER BY total ASC
LIMIT 5""",
     "graph": """MATCH p = (a:Destination {name: $from})-[:ROUTE*1..{maxHops}]-(b:Destination {name: $to})
WHERE all(n IN nodes(p) WHERE single(m IN nodes(p) WHERE m = n))
  AND all(r IN relationships(p) WHERE r.mode IN $modes AND NOT coalesce(r.closed, false))
WITH p, reduce(t = 0.0, r IN relationships(p) | t + r.{metric} * CASE WHEN '{metric}' = 'hours' THEN coalesce(r.trafficFactor, 1.0) ELSE 1.0 END) AS total
RETURN p ORDER BY total ASC LIMIT 5""",
     "explain": ["Enumerates loop-free paths of up to k legs (single() forbids revisiting a town).",
                 "The mode filter can exclude flights, or allow rail only.",
                 "The five cheapest totals are the main route plus four alternatives."]},
    {"id": "avoid_route", "section": "routes", "title": "Fastest route that avoids a destination", "params": ["from", "to", "avoid", "maxHops"], "concept": "Path predicates",
     "cypher": """MATCH p = (a:Destination {name: $from})-[:ROUTE*1..{maxHops}]-(b:Destination {name: $to})
WHERE all(n IN nodes(p) WHERE single(m IN nodes(p) WHERE m = n))
  AND none(n IN nodes(p) WHERE n.name = $avoid)
  AND all(r IN relationships(p) WHERE NOT coalesce(r.closed, false))
WITH p, reduce(h = 0.0, r IN relationships(p) | h + r.hours * coalesce(r.trafficFactor, 1.0)) AS hours
RETURN [n IN nodes(p) | n.name] AS stops, [r IN relationships(p) | r.mode] AS modes, round(hours, 2) AS hours
ORDER BY hours ASC
LIMIT 3""",
     "graph": """MATCH p = (a:Destination {name: $from})-[:ROUTE*1..{maxHops}]-(b:Destination {name: $to})
WHERE all(n IN nodes(p) WHERE single(m IN nodes(p) WHERE m = n))
  AND none(n IN nodes(p) WHERE n.name = $avoid)
  AND all(r IN relationships(p) WHERE NOT coalesce(r.closed, false))
WITH p, reduce(h = 0.0, r IN relationships(p) | h + r.hours * coalesce(r.trafficFactor, 1.0)) AS hours
RETURN p ORDER BY hours ASC LIMIT 1""",
     "explain": ["none() rejects any path that passes through the avoided destination (e.g. a flooded town)."]},
    {"id": "via_route", "section": "routes", "title": "Route through a must-visit stop", "params": ["from", "via", "to"], "concept": "Path concatenation",
     "cypher": """MATCH (a:Destination {name: $from}), (v:Destination {name: $via}), (b:Destination {name: $to})
MATCH p1 = shortestPath((a)-[:ROUTE*..12]-(v))
WHERE all(r IN relationships(p1) WHERE NOT coalesce(r.closed, false))
MATCH p2 = shortestPath((v)-[:ROUTE*..12]-(b))
WHERE all(r IN relationships(p2) WHERE NOT coalesce(r.closed, false))
RETURN [n IN nodes(p1) | n.name] + tail([n IN nodes(p2) | n.name]) AS stops,
       length(p1) + length(p2) AS legs,
       reduce(h = 0.0, r IN relationships(p1) + relationships(p2) | h + r.hours * coalesce(r.trafficFactor, 1.0)) AS hours""",
     "graph": """MATCH (a:Destination {name: $from}), (v:Destination {name: $via}), (b:Destination {name: $to})
MATCH p1 = shortestPath((a)-[:ROUTE*..12]-(v))
WHERE all(r IN relationships(p1) WHERE NOT coalesce(r.closed, false))
MATCH p2 = shortestPath((v)-[:ROUTE*..12]-(b))
WHERE all(r IN relationships(p2) WHERE NOT coalesce(r.closed, false))
RETURN p1, p2""",
     "explain": ["Two shortest paths joined at the stop, and tail() drops the duplicated middle town."]},
    {"id": "reachable", "section": "routes", "title": "Destinations reachable within N hours", "params": ["from", "maxHours", "modes"], "concept": "Connected destinations",
     "cypher": """MATCH p = (a:Destination {name: $from})-[:ROUTE*1..4]-(b:Destination)
WHERE b <> a AND all(r IN relationships(p) WHERE r.mode IN $modes AND NOT coalesce(r.closed, false))
WITH b, min(reduce(t = 0.0, r IN relationships(p) | t + r.hours * coalesce(r.trafficFactor, 1.0))) AS fastestHours
WHERE fastestHours <= $maxHours
RETURN b.name AS destination, round(fastestHours, 1) AS fastestHours
ORDER BY fastestHours""",
     "explain": ["min() over all paths of up to 4 legs gives the fastest time to each destination.",
                 "Change the hour limit and the travel modes to see the reachable area grow or shrink."]},
    {"id": "hubs", "section": "routes", "title": "Transport hubs (most connected destinations)", "params": [], "concept": "Degree",
     "cypher": """MATCH (d:Destination)
OPTIONAL MATCH (d)-[r:ROUTE]-(n:Destination)
RETURN d.name AS destination, count(DISTINCT n) AS connectedDestinations,
       count(r) AS routes, collect(DISTINCT r.mode) AS modes
ORDER BY connectedDestinations DESC, destination""",
     "explain": ["Degree counts neighbours, while routes counts relationships (parallel modes counted separately)."]},

    # =========================================================== Recommendations
    {"id": "profile", "section": "recommend", "title": "Tourist profile", "params": ["tourist"], "concept": "Profile",
     "cypher": """MATCH (t:Tourist {touristId: $tourist})-[:LIVES_IN]->(home:Destination)
OPTIONAL MATCH (t)-[i:INTERESTED_IN]->(c:Category)
WITH t, home, collect(c.name + ' (' + toString(i.weight) + ')') AS interests
OPTIONAL MATCH (t)-[v:VISITED]->(:Attraction)
RETURN t.name AS tourist, t.age AS age, t.budget AS budget, home.name AS home, interests,
       count(v) AS visits, round(avg(v.rating), 2) AS avgRating""",
     "graph": """MATCH p = (t:Tourist {touristId: $tourist})-[:INTERESTED_IN|LIVES_IN|WISHLISTED|VISITED]->()
RETURN p""",
     "explain": ["Interests, home and visits are the inputs for every recommender below."]},
    {"id": "content", "section": "recommend", "title": "Content-based: attractions that match the tourist's interests", "params": ["tourist", "limit"], "concept": "Content-based filtering",
     "cypher": """MATCH (t:Tourist {touristId: $tourist})-[i:INTERESTED_IN]->(c:Category)<-[:HAS_CATEGORY]-(a:Attraction)
WHERE NOT EXISTS { MATCH (t)-[:VISITED]->(a) WHERE a.attractionId <> coalesce($hidden, '') }
WITH a, sum(i.weight) AS interestScore, collect(DISTINCT c.name) AS matched
MATCH (a)-[:LOCATED_IN]->(d:Destination)
RETURN a.attractionId AS id, a.name AS attraction, d.name AS destination, matched,
       interestScore, a.rating AS rating, round(interestScore * a.rating, 2) AS score
ORDER BY score DESC, rating DESC, attraction
LIMIT $limit""",
     "graph": """MATCH (t:Tourist {touristId: $tourist})-[i:INTERESTED_IN]->(c:Category)<-[:HAS_CATEGORY]-(a:Attraction)
WHERE NOT EXISTS { MATCH (t)-[:VISITED]->(a) }
WITH t, a, sum(i.weight * a.rating) AS score ORDER BY score DESC LIMIT 5
MATCH p = (t)-[:INTERESTED_IN]->(:Category)<-[:HAS_CATEGORY]-(a)
RETURN p""",
     "explain": ["Score = sum of interest weights of the matching categories x attraction rating.",
                 "Already-visited attractions are excluded with NOT EXISTS { }."]},
    {"id": "similar_tourists", "section": "recommend", "title": "Similar tourists (Jaccard similarity of visits)", "params": ["tourist"], "concept": "Similarity",
     "cypher": """MATCH (t:Tourist {touristId: $tourist})-[:VISITED]->(a:Attraction)<-[:VISITED]-(o:Tourist)
WITH t, o, count(DISTINCT a) AS shared, collect(DISTINCT a.name) AS sharedAttractions
MATCH (t)-[:VISITED]->(x:Attraction)
WITH t, o, shared, sharedAttractions, count(DISTINCT x) AS mine
MATCH (o)-[:VISITED]->(y:Attraction)
WITH o, shared, sharedAttractions, mine, count(DISTINCT y) AS theirs
RETURN o.name AS tourist, shared, round(toFloat(shared) / (mine + theirs - shared), 3) AS jaccard,
       sharedAttractions
ORDER BY jaccard DESC
LIMIT 8""",
     "graph": """MATCH p = (t:Tourist {touristId: $tourist})-[:VISITED]->(:Attraction)<-[:VISITED]-(:Tourist)
RETURN p""",
     "explain": ["Jaccard = shared visits / all distinct visits of the two tourists (0 to 1)."]},
    {"id": "collaborative", "section": "recommend", "title": "Collaborative: attractions loved by similar tourists", "params": ["tourist", "limit"], "concept": "Collaborative filtering",
     "cypher": """MATCH (t:Tourist {touristId: $tourist})-[:VISITED]->(a:Attraction)<-[:VISITED]-(o:Tourist)
WHERE a.attractionId <> coalesce($hidden, '')
WITH t, o, count(DISTINCT a) AS shared
MATCH (t)-[:VISITED]->(x:Attraction)
WHERE x.attractionId <> coalesce($hidden, '')
WITH t, o, shared, count(DISTINCT x) AS mine
MATCH (o)-[:VISITED]->(y:Attraction)
WITH t, o, shared, mine, count(DISTINCT y) AS theirs
WITH t, o, toFloat(shared) / (mine + theirs - shared) AS similarity
ORDER BY similarity DESC
LIMIT 5
MATCH (o)-[r:VISITED]->(rec:Attraction)
WHERE r.rating >= 4
  AND NOT EXISTS { MATCH (t)-[:VISITED]->(rec) WHERE rec.attractionId <> coalesce($hidden, '') }
WITH rec, sum(similarity * r.rating) AS score, collect(DISTINCT o.name) AS lovedBy
MATCH (rec)-[:LOCATED_IN]->(d:Destination)
RETURN rec.attractionId AS id, rec.name AS attraction, d.name AS destination, lovedBy, round(score, 3) AS score
ORDER BY score DESC, attraction
LIMIT $limit""",
     "graph": """MATCH (t:Tourist {touristId: $tourist})-[:VISITED]->(:Attraction)<-[:VISITED]-(o:Tourist)
WITH t, o, count(*) AS shared ORDER BY shared DESC LIMIT 3
MATCH p = (o)-[r:VISITED]->(rec:Attraction)
WHERE r.rating >= 4 AND NOT EXISTS { MATCH (t)-[:VISITED]->(rec) }
RETURN p""",
     "explain": ["Find the 5 most similar tourists, then recommend what they rated 4 or 5 that this tourist has not visited.",
                 "Each recommendation is weighted by how similar the neighbour is."]},
    {"id": "popular", "section": "recommend", "title": "Baseline: most popular attractions not yet visited", "params": ["tourist", "limit"], "concept": "Popularity baseline",
     "cypher": """MATCH (t:Tourist {touristId: $tourist})
MATCH (a:Attraction)<-[v:VISITED]-(o:Tourist)
WHERE o <> t
  AND NOT EXISTS { MATCH (t)-[:VISITED]->(a) WHERE a.attractionId <> coalesce($hidden, '') }
WITH a, count(v) AS visits, avg(v.rating) AS avgRating
MATCH (a)-[:LOCATED_IN]->(d:Destination)
RETURN a.attractionId AS id, a.name AS attraction, d.name AS destination, visits,
       round(avgRating, 2) AS avgRating
ORDER BY visits DESC, avgRating DESC, attraction
LIMIT $limit""",
     "explain": ["Not personalised: a baseline that any recommender should beat."]},
    {"id": "destinations_for_me", "section": "recommend", "title": "Personalised destinations (interests + season + budget + travel time)", "params": ["tourist", "month", "limit"], "concept": "Hybrid scoring",
     "cypher": """MATCH (t:Tourist {touristId: $tourist})-[:LIVES_IN]->(home:Destination)
MATCH (t)-[i:INTERESTED_IN]->(c:Category)<-[:HAS_CATEGORY]-(a:Attraction)-[:LOCATED_IN]->(d:Destination)
WHERE d <> home
WITH t, home, d, sum(i.weight * a.rating) AS interest, collect(DISTINCT c.name) AS because
OPTIONAL MATCH (t)-[:VISITED]->(seen:Attraction)-[:LOCATED_IN]->(d)
WITH t, home, d, interest, because, count(seen) AS alreadySeen
OPTIONAL MATCH (h:Hotel)-[:LOCATED_IN]->(d)
WHERE h.priceBand = t.budget
WITH t, home, d, interest, because, alreadySeen, count(h) AS hotelsInBudget
OPTIONAL MATCH p = (home)-[:ROUTE*1..4]-(d)
WHERE all(r IN relationships(p) WHERE NOT coalesce(r.closed, false))
WITH d, interest, because, alreadySeen, hotelsInBudget,
     min(reduce(s = 0.0, r IN relationships(p) | s + r.hours * coalesce(r.trafficFactor, 1.0))) AS hours
WITH d, interest, because, alreadySeen, hotelsInBudget, hours,
     CASE WHEN $month IN d.bestMonths THEN 1 ELSE 0 END AS inSeason
RETURN d.name AS destination, because, round(interest, 1) AS interestScore, inSeason = 1 AS goodInMonth,
       hotelsInBudget, round(hours, 1) AS travelHours, alreadySeen,
       round(interest + 3 * inSeason + 2 * sign(hotelsInBudget) - 0.4 * coalesce(hours, 20) - 2 * alreadySeen, 2) AS score
ORDER BY score DESC
LIMIT $limit""",
     "explain": ["interest = sum of interest weight x rating over matching attractions at the destination.",
                 "+3 if the month is in season, +2 if a hotel matches the budget, -0.4 per travel hour from home "
                 "(fastest route of up to 4 legs), -2 per attraction already visited there.",
                 "Every factor comes from a different part of the graph: the explanation is the path."]},
    {"id": "hotels_for_me", "section": "recommend", "title": "Hotels for this tourist in a destination", "params": ["tourist", "destination"], "concept": "Social proof",
     "cypher": """MATCH (t:Tourist {touristId: $tourist})
MATCH (h:Hotel)-[:LOCATED_IN]->(:Destination {name: $destination})
OPTIONAL MATCH (t)-[:VISITED]->(:Attraction)<-[:VISITED]-(peer:Tourist)-[s:STAYED_AT]->(h)
WHERE peer <> t
WITH t, h, count(DISTINCT peer) AS similarGuests, avg(s.rating) AS peerRating
RETURN h.name AS hotel, h.stars AS stars, h.priceBand AS band, h.pricePerNight AS pricePerNight,
       h.rating AS rating, h.priceBand = t.budget AS inBudget, similarGuests, round(peerRating, 1) AS peerRating,
       round(h.rating + CASE WHEN h.priceBand = t.budget THEN 2 ELSE 0 END + 0.5 * similarGuests, 2) AS score
ORDER BY score DESC""",
     "explain": ["Peers are tourists who visited at least one of the same attractions.",
                 "A hotel scores higher when it fits the budget and peers stayed there."]},
    {"id": "also_visited", "section": "recommend", "title": "Tourists who visited this attraction also visited", "params": ["attraction"], "concept": "Co-occurrence",
     "cypher": """MATCH (a:Attraction {name: $attraction})<-[:VISITED]-(t:Tourist)-[:VISITED]->(other:Attraction)
WHERE other <> a
MATCH (other)-[:LOCATED_IN]->(d:Destination)
RETURN other.name AS attraction, d.name AS destination, count(DISTINCT t) AS tourists
ORDER BY tourists DESC, attraction
LIMIT 10""",
     "graph": """MATCH p = (a:Attraction {name: $attraction})<-[:VISITED]-(:Tourist)-[:VISITED]->(:Attraction)
RETURN p LIMIT 80""",
     "explain": ["The classic 'customers who bought this also bought' pattern, two hops through tourists."]},
    {"id": "wishlist_routes", "section": "recommend", "title": "How to reach each wishlisted destination from home", "params": ["tourist"], "concept": "Paths from the profile",
     "cypher": """MATCH (t:Tourist {touristId: $tourist})-[:LIVES_IN]->(home:Destination)
MATCH (t)-[:WISHLISTED]->(w:Destination)
WHERE w <> home
MATCH p = shortestPath((home)-[:ROUTE*..12]-(w))
WHERE all(r IN relationships(p) WHERE NOT coalesce(r.closed, false))
RETURN w.name AS wishlisted, [n IN nodes(p) | n.name] AS stops, length(p) AS legs,
       reduce(h = 0.0, r IN relationships(p) | h + r.hours * coalesce(r.trafficFactor, 1.0)) AS hours""",
     "graph": """MATCH (t:Tourist {touristId: $tourist})-[:LIVES_IN]->(home:Destination)
MATCH (t)-[:WISHLISTED]->(w:Destination)
WHERE w <> home
MATCH p = shortestPath((home)-[:ROUTE*..12]-(w))
WHERE all(r IN relationships(p) WHERE NOT coalesce(r.closed, false))
RETURN p""",
     "explain": ["Joins the tourist's profile (home, wishlist) with route finding in a single query."]},
]

QUERY_BY_ID = {q["id"]: q for q in QUERIES}

# Sample values: used by the pre-demo check and written into neo4j/03_queries.cypher
SAMPLE_PARAMS = {"tourist": "t01", "destination": "Munnar", "from": "Chennai", "to": "Munnar", "via": "Madurai",
                 "avoid": "Coimbatore", "category": "Beach", "category2": "Heritage", "month": 12, "budget": "mid",
                 "attraction": "Meenakshi Amman Temple", "maxHours": 6.0, "modes": ["road", "rail", "flight"],
                 "limit": 10, "hidden": None}
METRICS = ("hours", "distanceKm", "costInr")


def render(query_id, max_hops=5, metric="hours", graph=False):
    q = QUERY_BY_ID[query_id]
    text = q["graph"] if (graph and q.get("graph")) else q["cypher"]
    if "{maxHops}" in text:
        k = int(max_hops)
        if not 1 <= k <= 6:
            raise ValueError("Maximum legs must be between 1 and 6.")
        text = text.replace("{maxHops}", str(k))
    if "{metric}" in text:
        if metric not in METRICS:
            raise ValueError(f"metric must be one of {', '.join(METRICS)}.")
        text = text.replace("{metric}", metric)
    return text
