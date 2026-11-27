"""Backend for the interactive pages: network for the 3D map, live exploration scores,
destination details, live recommendations with adjustable interests, demo visits, scenario saving
and route verification in Cypher.

Every function returns the Cypher it ran, so the UI can show it next to the live result.
"""
from .catalog import render
from .recommend import rrf

# ---------------------------------------------------------------- network for the 3D map
NETWORK_DESTINATIONS = """MATCH (d:Destination)
OPTIONAL MATCH (a:Attraction)-[:LOCATED_IN]->(d)
RETURN d.name AS name, d.state AS state, d.lat AS lat, d.lon AS lon, d.bestMonths AS bestMonths,
       d.description AS description, count(a) AS attractions
ORDER BY name"""

NETWORK_ROUTES = """MATCH (a:Destination)-[r:ROUTE]->(b:Destination)
RETURN a.name AS from, b.name AS to, r.mode AS mode, r.distanceKm AS distanceKm, r.hours AS hours,
       r.costInr AS costInr, coalesce(r.closed, false) AS closed,
       coalesce(r.trafficFactor, 1.0) AS traffic, coalesce(r.added, false) AS added
ORDER BY from, to, mode"""


def network(neo):
    return {"destinations": neo.scalar_rows(NETWORK_DESTINATIONS), "routes": neo.scalar_rows(NETWORK_ROUTES),
            "cypher": NETWORK_DESTINATIONS + ";\n\n" + NETWORK_ROUTES + ";"}


# ---------------------------------------------------------------- live exploration
EXPLORE = """MATCH (d:Destination)
OPTIONAL MATCH (d)<-[:LOCATED_IN]-(a:Attraction)-[:HAS_CATEGORY]->(c:Category)
WHERE c.name IN $categories
WITH d, count(DISTINCT a) AS matching, collect(DISTINCT c.name) AS matched, avg(a.rating) AS rating
OPTIONAL MATCH (h:Hotel)-[:LOCATED_IN]->(d)
WHERE $budget = 'any' OR h.priceBand = $budget
WITH d, matching, matched, rating, count(h) AS hotels
RETURN d.name AS destination, matching, matched, round(coalesce(rating, 0.0), 2) AS rating, hotels,
       $month IN d.bestMonths AS inSeason
ORDER BY destination"""


def explore_score(row, any_category):
    """0-10 score: interest match, season and hotel availability."""
    interest = min(row["matching"], 4) / 4 * 6 if any_category else 3.0
    quality = (row["rating"] - 4.0) * 2 if row["rating"] else 0.0
    return round(max(0.0, interest + (2.0 if row["inSeason"] else 0.0) + (1.0 if row["hotels"] else -2.0) + quality), 2)


def explore(neo, categories, month, budget):
    rows = neo.scalar_rows(EXPLORE, {"categories": categories, "month": month, "budget": budget})
    for r in rows:
        r["score"] = explore_score(r, bool(categories))
    rows.sort(key=lambda r: (-r["score"], r["destination"]))
    return {"rows": rows, "cypher": EXPLORE, "params": {"categories": categories, "month": month, "budget": budget}}


DEST_ATTRACTIONS = """MATCH (a:Attraction)-[:LOCATED_IN]->(d:Destination {name: $name})
OPTIONAL MATCH (a)-[:HAS_CATEGORY]->(c:Category)
OPTIONAL MATCH (a)<-[v:VISITED]-(:Tourist)
RETURN a.attractionId AS id, a.name AS name, collect(DISTINCT c.name) AS categories, a.rating AS rating,
       a.entryFeeInr AS fee, a.visitHours AS hours, count(DISTINCT v) AS visits
ORDER BY rating DESC"""

DEST_HOTELS = """MATCH (h:Hotel)-[:LOCATED_IN]->(:Destination {name: $name})
RETURN h.name AS name, h.stars AS stars, h.priceBand AS band, h.pricePerNight AS price, h.rating AS rating
ORDER BY price"""


def destination(neo, name):
    info = neo.scalar_rows("MATCH (d:Destination {name: $name}) RETURN d.name AS name, d.state AS state, "
                           "d.description AS description, d.bestMonths AS bestMonths", {"name": name})
    if not info:
        raise ValueError(f"Unknown destination '{name}'.")
    return {**info[0], "attractions": neo.scalar_rows(DEST_ATTRACTIONS, {"name": name}),
            "hotels": neo.scalar_rows(DEST_HOTELS, {"name": name}),
            "cypher": DEST_ATTRACTIONS + ";\n\n" + DEST_HOTELS + ";"}


# ---------------------------------------------------------------- live recommendations
TOURIST = """MATCH (t:Tourist {touristId: $tourist})-[:LIVES_IN]->(home:Destination)
OPTIONAL MATCH (t)-[i:INTERESTED_IN]->(c:Category)
WITH t, home, collect({cat: c.name, weight: i.weight}) AS interests
OPTIONAL MATCH (t)-[v:VISITED]->(a:Attraction)-[:LOCATED_IN]->(d:Destination)
RETURN t.touristId AS id, t.name AS name, t.age AS age, t.budget AS budget, t.travelStyle AS style,
       home.name AS home, interests,
       collect(CASE WHEN a IS NULL THEN null ELSE {id: a.attractionId, name: a.name, destination: d.name,
               rating: v.rating, date: toString(v.date), demo: coalesce(v.demo, false)} END) AS visits"""

LIVE_CONTENT = """UNWIND $weights AS w
MATCH (c:Category {name: w.cat})<-[:HAS_CATEGORY]-(a:Attraction)
WHERE w.weight > 0
  AND NOT EXISTS { MATCH (:Tourist {touristId: $tourist})-[:VISITED]->(a) }
WITH a, sum(w.weight) AS interest, collect(c.name) AS matched
MATCH (a)-[:LOCATED_IN]->(d:Destination)
RETURN a.attractionId AS id, a.name AS attraction, d.name AS destination, matched,
       interest, a.rating AS rating, round(interest * a.rating, 2) AS score
ORDER BY score DESC, attraction
LIMIT $limit"""


def tourist(neo, tid):
    rows = neo.scalar_rows(TOURIST, {"tourist": tid})
    if not rows:
        raise ValueError(f"Unknown tourist '{tid}'.")
    t = rows[0]
    t["interests"] = [i for i in t["interests"] if i.get("cat")]
    t["visits"] = sorted([v for v in t["visits"] if v], key=lambda v: v["date"] or "")
    return t


def clean_weights(weights):
    if not isinstance(weights, dict):
        raise ValueError("weights must be an object such as {\"Beach\": 3}.")
    out = []
    for cat, w in weights.items():
        try:
            w = float(w)
        except (TypeError, ValueError):
            raise ValueError(f"Weight for {cat} must be a number.")
        if not 0 <= w <= 3:
            raise ValueError("Weights must be between 0 and 3.")
        if w > 0:
            out.append({"cat": str(cat), "weight": w})
    return out


def destination_ranking(content, month_ok, travel_hours):
    """Aggregate attraction scores into destinations, then add season and travel time."""
    agg = {}
    for r in content:
        d = agg.setdefault(r["destination"], {"destination": r["destination"], "interest": 0.0, "items": [], "because": set()})
        d["interest"] += r["score"]
        d["items"].append(r["attraction"])
        d["because"].update(r["matched"])
    out = []
    for d in agg.values():
        hours = travel_hours.get(d["destination"])
        season = d["destination"] in month_ok
        score = d["interest"] + (3 if season else 0) - 0.4 * (hours if hours is not None else 20)
        out.append({"destination": d["destination"], "score": round(score, 2), "interest": round(d["interest"], 1),
                    "inSeason": season, "travelHours": None if hours is None else round(hours, 1),
                    "because": sorted(d["because"]), "attractions": d["items"][:3]})
    out.sort(key=lambda x: (-x["score"], x["destination"]))
    return out[:6]


def live_recommend(neo, tid, weights, month, route_graph):
    t = tourist(neo, tid)
    w = clean_weights(weights)
    content = neo.run(LIVE_CONTENT, {"weights": w, "tourist": tid, "limit": 25})
    idx = {c: i for i, c in enumerate(content["columns"])}
    content_rows = [{k: r[i] for k, i in idx.items()} for r in content["rows"]]
    collab = neo.run(render("collaborative"), {"tourist": tid, "hidden": None, "limit": 20})
    cidx = {c: i for i, c in enumerate(collab["columns"])}
    collab_rows = [{k: r[i] for k, i in cidx.items()} for r in collab["rows"]]
    fused = rrf({"content": content_rows[:20], "collaborative": collab_rows}, limit=10)
    in_month = {r["name"] for r in neo.scalar_rows(
        "MATCH (d:Destination) WHERE $month IN d.bestMonths RETURN d.name AS name", {"month": month})}
    dist, _ = route_graph.dijkstra(t["home"], "hours")
    dests = [d for d in destination_ranking(content_rows, in_month, dist) if d["destination"] != t["home"]]
    return {"tourist": t, "weights": w, "content": content_rows[:10], "collaborative": collab_rows[:10], "fused": fused,
            "destinations": dests, "cypher": {"content": LIVE_CONTENT, "collaborative": render("collaborative")}}


EXPLAIN = """MATCH (t:Tourist {touristId: $tourist}), (a:Attraction {attractionId: $attraction})
OPTIONAL MATCH p1 = (t)-[:INTERESTED_IN]->(:Category)<-[:HAS_CATEGORY]-(a)
OPTIONAL MATCH p2 = (t)-[:VISITED]->(:Attraction)<-[:VISITED]-(:Tourist)-[v:VISITED]->(a)
WHERE v.rating >= 4
OPTIONAL MATCH p3 = (a)-[:LOCATED_IN]->(:Destination)
RETURN collect(DISTINCT p1) AS interestPaths, collect(DISTINCT p2)[0..6] AS peerPaths, collect(DISTINCT p3) AS place"""


def explain(neo, tid, attraction_id):
    r = neo.run(EXPLAIN, {"tourist": tid, "attraction": attraction_id}, max_rows=5)
    row = dict(zip(r["columns"], r["rows"][0])) if r["rows"] else {}
    return {"graph": r["graph"], "interestPaths": len(row.get("interestPaths") or []),
            "peerPaths": len(row.get("peerPaths") or []), "cypher": EXPLAIN}


ADD_VISIT = """MATCH (t:Tourist {touristId: $tourist}), (a:Attraction {attractionId: $attraction})
MERGE (t)-[v:VISITED]->(a)
ON CREATE SET v.date = date(), v.rating = $rating, v.demo = true
RETURN t.name AS tourist, a.name AS attraction, v.rating AS rating"""

REMOVE_DEMO_VISITS = """MATCH (:Tourist {touristId: $tourist})-[v:VISITED {demo: true}]->(:Attraction)
DELETE v
RETURN count(*) AS removed"""


def add_visit(neo, tid, attraction_id, rating):
    rating = int(rating)
    if not 1 <= rating <= 5:
        raise ValueError("Rating must be 1 to 5.")
    rows, counters = neo.write_rows(ADD_VISIT, {"tourist": tid, "attraction": attraction_id, "rating": rating})
    if not rows:
        raise ValueError("Tourist or attraction not found.")
    return {"row": rows[0], "created": counters.relationships_created, "cypher": ADD_VISIT}


def remove_demo_visits(neo, tid):
    rows, _ = neo.write_rows(REMOVE_DEMO_VISITS, {"tourist": tid})
    return {"removed": rows[0]["removed"] if rows else 0, "cypher": REMOVE_DEMO_VISITS}


# ---------------------------------------------------------------- Route Lab scenarios
SAVE_SCENARIO = [
    ("Reset closures and traffic on every route", """MATCH ()-[r:ROUTE]->()
REMOVE r.closed, r.trafficFactor"""),
    ("Close routes", """UNWIND $closed AS c
MATCH (a:Destination {name: c.from})-[r:ROUTE {mode: c.mode}]->(b:Destination {name: c.to})
SET r.closed = true"""),
    ("Set traffic factors", """UNWIND $traffic AS t
MATCH (a:Destination {name: t.from})-[r:ROUTE {mode: t.mode}]->(b:Destination {name: t.to})
SET r.trafficFactor = t.factor"""),
    ("Add new routes", """UNWIND $added AS n
MATCH (a:Destination {name: n.from}), (b:Destination {name: n.to})
MERGE (a)-[r:ROUTE {mode: n.mode}]->(b)
ON CREATE SET r.distanceKm = n.distanceKm, r.hours = n.hours, r.costInr = n.costInr, r.added = true"""),
]

RESTORE = [
    ("Delete routes added in the Route Lab", """MATCH ()-[r:ROUTE {added: true}]->()
DELETE r"""),
    ("Remove closures and traffic", """MATCH ()-[r:ROUTE]->()
REMOVE r.closed, r.trafficFactor
RETURN count(r) AS routes"""),
]


def _route_list(items, with_factor=False):
    out = []
    for it in items or []:
        if not isinstance(it, dict) or not all(k in it for k in ("from", "to", "mode")):
            raise ValueError("Each route needs from, to and mode.")
        e = {"from": str(it["from"]), "to": str(it["to"]), "mode": str(it["mode"])}
        if with_factor:
            f = float(it.get("factor", 1))
            if not 1 <= f <= 5:
                raise ValueError("Traffic factor must be between 1 and 5.")
            e["factor"] = f
        out.append(e)
    return out


def save_scenario(neo, changes):
    closed = _route_list(changes.get("closed"))
    traffic = _route_list(changes.get("traffic"), with_factor=True)
    added = []
    for n in changes.get("added") or []:
        e = _route_list([n])[0]
        if e["mode"] not in ("road", "rail", "flight") or e["from"] == e["to"]:
            raise ValueError("A new route needs two different destinations and a valid mode.")
        e.update({"distanceKm": int(n.get("distanceKm", 0)), "hours": float(n.get("hours", 0)), "costInr": int(n.get("costInr", 0))})
        if e["hours"] <= 0 or e["distanceKm"] <= 0:
            raise ValueError("A new route needs positive distance and hours.")
        added.append(e)
    params = {"closed": closed, "traffic": traffic, "added": added}
    ran = []
    for title, cypher in SAVE_SCENARIO:
        _, counters = neo.write_rows(cypher, params)
        ran.append({"title": title, "cypher": cypher, "propertiesSet": counters.properties_set,
                    "relationshipsCreated": counters.relationships_created})
    return {"steps": ran, "params": params}


def restore_network(neo):
    _, c1 = neo.write_rows(RESTORE[0][1])
    rows, _ = neo.write_rows(RESTORE[1][1])
    return {"routes": rows[0]["routes"] if rows else 0, "deleted": c1.relationships_deleted,
            "cypher": ";\n\n".join(c for _, c in RESTORE) + ";"}


VERIFY_FEWEST = """MATCH (a:Destination {name: $from}), (b:Destination {name: $to})
MATCH p = shortestPath((a)-[:ROUTE*..12]-(b))
WHERE all(r IN relationships(p) WHERE r.mode IN $modes
          AND NOT (startNode(r).name + '|' + endNode(r).name + '|' + r.mode) IN $closed)
RETURN [n IN nodes(p) | n.name] AS stops, length(p) AS legs"""

VERIFY_BEST = """MATCH p = (a:Destination {name: $from})-[:ROUTE*1..{maxHops}]-(b:Destination {name: $to})
WHERE all(n IN nodes(p) WHERE single(m IN nodes(p) WHERE m = n))
  AND all(r IN relationships(p) WHERE r.mode IN $modes
          AND NOT (startNode(r).name + '|' + endNode(r).name + '|' + r.mode) IN $closed)
WITH p, reduce(total = 0.0, r IN relationships(p) |
       total + r.{metric} * coalesce(head([t IN $traffic
         WHERE t.key = startNode(r).name + '|' + endNode(r).name + '|' + r.mode | t.factor]), 1.0)) AS total
RETURN [n IN nodes(p) | n.name] AS stops, length(p) AS legs, round(total, 2) AS total
ORDER BY total ASC
LIMIT 3"""


def verify(neo, algorithm, src, dst, metric, modes, closed_keys, traffic, max_hops=6):
    if src == dst:
        raise ValueError("Choose two different destinations.")
    if metric not in ("hours", "distanceKm", "costInr"):
        raise ValueError("Unknown metric.")
    params = {"from": src, "to": dst, "modes": list(modes), "closed": list(closed_keys)}
    if algorithm == "bfs":
        cypher = VERIFY_FEWEST
    else:
        cypher = VERIFY_BEST.replace("{maxHops}", str(int(max_hops))).replace("{metric}", metric)
        # traffic only changes hours
        params["traffic"] = [t for t in traffic if metric == "hours"]
    r = neo.run(cypher, params, max_rows=5)
    return {"columns": r["columns"], "rows": r["rows"], "cypher": cypher, "params": params, "timing": r["timing"]}


def evaluation_cases(neo, min_visits=4):
    visits = neo.scalar_rows("""
        MATCH (t:Tourist)-[v:VISITED]->(a:Attraction)
        WHERE NOT coalesce(v.demo, false)
        RETURN t.touristId AS tourist, t.name AS name, a.attractionId AS id, a.name AS attraction, v.date AS date
        ORDER BY tourist, date, id""")
    by_t = {}
    for v in visits:
        by_t.setdefault(v["tourist"], []).append(v)
    return [{"tourist": t, "name": vs[-1]["name"], "hidden": vs[-1]["id"], "hiddenName": vs[-1]["attraction"],
             "visits": len(vs)} for t, vs in by_t.items() if len(vs) >= min_visits]
