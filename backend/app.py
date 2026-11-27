"""TripGraph Live: interactive Tourism Recommendation System using Neo4j.

Run:  python app.py      then open http://127.0.0.1:5000
"""
import re
import time

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

import config
from core import catalog, live, recommend
from core.neo4j_service import Neo4jService
from core.routing import METRICS, MODES, RouteGraph
from core.scripts import parse_steps, script_path
from data import tourism as T

app = Flask(__name__, static_folder=config.FRONTEND_DIR, static_url_path="")
app.json.sort_keys = False
neo = Neo4jService(config.NEO4J_URI, config.NEO4J_USER, config.NEO4J_PASSWORD, config.NEO4J_DATABASE)

SCRIPTS = {"constraints": "01_constraints.cypher", "sample": "02_sample_data.cypher", "reset": "99_reset.cypher"}
SAMPLE = {k: v for k, v in catalog.SAMPLE_PARAMS.items() if k != "hidden"}


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def body():
    data = request.get_json(silent=True)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("The request body must be a JSON object.")
    return data


def need_db():
    if not neo.is_available(force=True):
        raise ApiError("Neo4j is not connected. Start the database and check NEO4J_PASSWORD in backend/.env. "
                       f"Details: {neo.last_error}", 503)


def neo_error(exc):
    msg = getattr(exc, "message", None) or str(exc)
    code = getattr(exc, "code", None)
    return msg + (f"  [{code}]" if code else "")


@app.errorhandler(ValueError)
def on_value_error(err):
    return jsonify({"error": str(err)}), 400


@app.errorhandler(ApiError)
def on_api_error(err):
    return jsonify({"error": str(err)}), err.status


@app.errorhandler(Exception)
def on_error(err):
    if isinstance(err, HTTPException):
        return jsonify({"error": err.description}), err.code
    if err.__class__.__module__.startswith("neo4j"):
        return jsonify({"error": "Neo4j: " + neo_error(err)}), 400
    app.logger.exception("Unhandled error")
    return jsonify({"error": f"Internal error: {err}"}), 500


@app.get("/")
def index():
    return app.send_static_file("index.html")


# ---- status ------------------------------------------------------------------------------------
@app.get("/api/health")
def api_health():
    up = neo.is_available(force=True)
    return jsonify({"neo4j": up, "neo4jError": None if up else neo.last_error, "neo4jUri": config.NEO4J_URI,
                    "allowWrite": config.ALLOW_WRITE_PLAYGROUND, "allowReset": config.ALLOW_RESET})


@app.get("/api/meta")
def api_meta():
    return jsonify({"scenario": T.SCENARIO, "model": T.MODEL, "queries": catalog.QUERIES, "categories": T.CATEGORIES,
                    "modes": MODES, "metrics": METRICS, "sample": SAMPLE, "methods": recommend.METHODS})


@app.get("/api/overview")
def api_overview():
    if not neo.is_available():
        return jsonify({"connected": False})
    labels = neo.scalar_rows("MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count ORDER BY count DESC")
    types = neo.scalar_rows("MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count ORDER BY count DESC")
    return jsonify({"connected": True, "labels": labels, "types": types,
                    "loaded": any(r["label"] == "Tourist" for r in labels)})


@app.get("/api/lists")
def api_lists():
    need_db()
    return jsonify({
        "destinations": [r["name"] for r in neo.scalar_rows("MATCH (d:Destination) RETURN d.name AS name ORDER BY name")],
        "tourists": neo.scalar_rows("""MATCH (t:Tourist) OPTIONAL MATCH (t)-[:LIVES_IN]->(h:Destination)
                                       RETURN t.touristId AS id, t.name AS name, h.name AS home, t.travelStyle AS style
                                       ORDER BY id"""),
        "categories": [r["name"] for r in neo.scalar_rows("MATCH (c:Category) RETURN c.name AS name ORDER BY name")],
        "attractions": [r["name"] for r in neo.scalar_rows("MATCH (a:Attraction) RETURN a.name AS name ORDER BY name")],
    })


# ---- data population ------------------------------------------------------------------------------
@app.get("/api/setup/steps")
def api_steps():
    return jsonify({k: parse_steps(script_path(config.NEO4J_SCRIPTS_DIR, f)) for k, f in SCRIPTS.items()})


@app.post("/api/setup/run")
def api_run_step():
    need_db()
    p = body()
    script = p.get("script")
    if script not in SCRIPTS:
        raise ValueError("Unknown script.")
    if script == "reset" and not config.ALLOW_RESET:
        raise ApiError("Reset is disabled (ALLOW_RESET=false in backend/.env).", 403)
    steps = parse_steps(script_path(config.NEO4J_SCRIPTS_DIR, SCRIPTS[script]))
    wanted = steps if p.get("step") in (None, "all") else [s for s in steps if s["number"] == int(p["step"])]
    if not wanted:
        raise ValueError("Unknown step.")
    report = []
    for st in wanted:
        for stmt in st["statements"]:
            try:
                r = neo.run(stmt, write=True, max_rows=50)
            except Exception as exc:  # noqa: BLE001
                return jsonify({"error": f"Step {st['number']} failed: {neo_error(exc)}", "report": report}), 400
            report.append({"step": st["number"], "title": st["title"], "statement": stmt[:120],
                           "counters": r["counters"], "columns": r["columns"], "rows": r["rows"][:20],
                           "ms": r["timing"]["wallMs"]})
    return jsonify({"report": report})


@app.get("/api/graph")
def api_graph():
    need_db()
    r = neo.run("""MATCH (n)
OPTIONAL MATCH (n)-[r]->(m)
RETURN n, r, m""", max_rows=5000)
    return jsonify({"graph": r["graph"], "truncated": r["truncated"]})


# ---- catalogue queries ---------------------------------------------------------------------------------
def _params_for(q, given, text):
    p = {}
    for name in q["params"]:
        if name in ("maxHops", "metric"):
            continue
        v = given.get(name)
        if name == "month":
            v = int(v) if v not in (None, "") else 0
            if not 1 <= v <= 12:
                raise ValueError("Choose a month from 1 to 12.")
        elif name == "limit":
            v = int(v or 10)
            if not 1 <= v <= 25:
                raise ValueError("Limit must be between 1 and 25.")
        elif name == "maxHours":
            v = float(v or 0)
            if not 0.5 <= v <= 48:
                raise ValueError("Hours must be between 0.5 and 48.")
        elif name == "modes":
            v = [m for m in (v or []) if m in MODES]
            if not v:
                raise ValueError("Choose at least one travel mode.")
        elif name == "budget":
            v = v if v in ("any", "budget", "mid", "luxury") else "any"
        else:
            v = str(v or "").strip()
            if not v:
                raise ValueError(f"Choose a value for {name}.")
        p[name] = v
    if "$hidden" in text:
        p["hidden"] = None
    names = [p.get(k) for k in ("from", "via", "to", "avoid") if p.get(k)]
    if len(names) != len(set(names)):
        raise ValueError("From, to, via and avoid must all be different destinations.")
    return p


@app.post("/api/query/<qid>")
def api_query(qid):
    need_db()
    if qid not in catalog.QUERY_BY_ID:
        raise ApiError(f"Unknown query '{qid}'.", 404)
    q = catalog.QUERY_BY_ID[qid]
    g = body()
    hops, metric = int(g.get("maxHops", 5)), g.get("metric", "hours")
    cypher = catalog.render(qid, hops, metric)
    params = _params_for(q, g, cypher)
    result = neo.run(cypher, params, profile=bool(g.get("profile")), max_rows=300)
    graph, graph_cypher = result["graph"], None
    if q.get("graph"):
        graph_cypher = catalog.render(qid, hops, metric, graph=True)
        graph = neo.run(graph_cypher, {k: v for k, v in params.items()}, max_rows=300)["graph"]
    shown = {k: v for k, v in params.items() if k != "hidden"}
    return jsonify({"id": qid, "title": q["title"], "cypher": cypher, "graphCypher": graph_cypher, "params": shown,
                    **{k: v for k, v in result.items() if k != "graph"}, "graph": graph})


WRITE_RE = re.compile(r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|FOREACH|LOAD\s+CSV|ALTER|GRANT|REVOKE|DENY)\b", re.I)


def _strip(text):
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"//[^\n]*", " ", text)
    return re.sub(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|`[^`]*`", "''", text)


@app.post("/api/playground")
def api_playground():
    need_db()
    p = body()
    cypher = str(p.get("cypher") or "").strip().rstrip(";").strip()
    if not cypher:
        raise ValueError("Type a Cypher query.")
    if ";" in _strip(cypher):
        raise ValueError("Run one statement at a time.")
    params = p.get("params") or {}
    if not isinstance(params, dict):
        raise ValueError('Parameters must be a JSON object, e.g. {"tourist": "t01"}.')
    write = bool(p.get("write")) and config.ALLOW_WRITE_PLAYGROUND
    if WRITE_RE.search(_strip(cypher)) and not write:
        raise ApiError("This query changes data and the playground is read-only"
                       + (". Tick 'Allow changes' to run it." if config.ALLOW_WRITE_PLAYGROUND
                          else " (set ALLOW_WRITE_PLAYGROUND=true in backend/.env to allow it)."), 403)
    profile = bool(p.get("profile")) and not cypher.upper().startswith(("PROFILE", "EXPLAIN", "SHOW", "CALL"))
    result = neo.run(cypher, params, write=write, profile=profile, max_rows=500)
    result["cypher"] = cypher
    return jsonify(result)


# ---- route planner (Python algorithms on the Neo4j route graph) -------------------------------------------
def _modes(v):
    m = [x for x in (v or MODES) if x in MODES]
    if not m:
        raise ValueError("Choose at least one travel mode.")
    return tuple(m)


def _metric(v):
    if v not in METRICS:
        raise ValueError(f"metric must be one of {', '.join(METRICS)}.")
    return v


@app.get("/api/routes/map")
def api_route_map():
    need_db()
    return jsonify(RouteGraph.from_neo4j(neo).map_data())


@app.post("/api/routes/plan")
def api_route_plan():
    need_db()
    p = body()
    g = RouteGraph.from_neo4j(neo)
    src, dst = p.get("from"), p.get("to")
    g.check(src, dst)
    if src == dst:
        raise ValueError("Choose two different destinations.")
    metric, modes = _metric(p.get("metric", "hours")), _modes(p.get("modes"))
    k = max(1, min(int(p.get("k", 4)), 8))
    t0 = time.perf_counter()
    routes = g.k_shortest(src, dst, k, metric, modes)
    return jsonify({"from": src, "to": dst, "metric": metric, "modes": modes, "routes": routes,
                    "algorithm": "Dijkstra for the best route, Yen's algorithm for the alternatives",
                    "ms": (time.perf_counter() - t0) * 1000})


@app.post("/api/routes/itinerary")
def api_itinerary():
    need_db()
    p = body()
    g = RouteGraph.from_neo4j(neo)
    stops = p.get("stops") or []
    if not isinstance(stops, list):
        raise ValueError("stops must be a list of destinations.")
    t0 = time.perf_counter()
    res = g.itinerary(p.get("start"), stops, _metric(p.get("metric", "hours")), _modes(p.get("modes")),
                      bool(p.get("returnHome")))
    res["ms"] = (time.perf_counter() - t0) * 1000
    return jsonify(res)


@app.get("/api/routes/hubs")
def api_hubs():
    need_db()
    return jsonify(RouteGraph.from_neo4j(neo).hubs())


# ---- recommendations ---------------------------------------------------------------------------------------
@app.post("/api/recommend/hybrid")
def api_hybrid():
    need_db()
    p = body()
    tourist = str(p.get("tourist") or "")
    if not neo.scalar_rows("MATCH (t:Tourist {touristId: $t}) RETURN t.touristId AS id", {"t": tourist}):
        raise ValueError("Choose a tourist.")
    lists = {m: recommend.ranked(neo, m, tourist, None, 20) for m in ("content", "collaborative")}
    return jsonify({"fused": recommend.rrf(lists, limit=int(p.get("limit", 10))), "lists": lists, "k": recommend.RRF_K})


@app.post("/api/evaluate")
def api_evaluate():
    need_db()
    t0 = time.perf_counter()
    res = recommend.evaluate(neo)
    res["seconds"] = time.perf_counter() - t0
    return jsonify(res)


# ---- interactive pages ---------------------------------------------------------------------------------------
@app.get("/api/network")
def api_network():
    need_db()
    return jsonify(live.network(neo))


@app.post("/api/explore")
def api_explore():
    need_db()
    p = body()
    cats = [c for c in (p.get("categories") or []) if isinstance(c, str)]
    month = int(p.get("month") or 1)
    if not 1 <= month <= 12:
        raise ValueError("Month must be 1 to 12.")
    budget = p.get("budget") if p.get("budget") in ("any", "budget", "mid", "luxury") else "any"
    return jsonify(live.explore(neo, cats, month, budget))


@app.get("/api/destination/<name>")
def api_destination(name):
    need_db()
    return jsonify(live.destination(neo, name))


@app.get("/api/tourist/<tid>")
def api_tourist(tid):
    need_db()
    return jsonify(live.tourist(neo, tid))


@app.post("/api/recommend/live")
def api_live_recommend():
    need_db()
    p = body()
    month = int(p.get("month") or 1)
    if not 1 <= month <= 12:
        raise ValueError("Month must be 1 to 12.")
    return jsonify(live.live_recommend(neo, str(p.get("tourist") or ""), p.get("weights") or {}, month,
                                       RouteGraph.from_neo4j(neo)))


@app.post("/api/recommend/explain")
def api_explain():
    need_db()
    p = body()
    return jsonify(live.explain(neo, str(p.get("tourist") or ""), str(p.get("attraction") or "")))


@app.post("/api/visits")
def api_add_visit():
    need_db()
    p = body()
    return jsonify(live.add_visit(neo, str(p.get("tourist") or ""), str(p.get("attraction") or ""), p.get("rating", 5)))


@app.post("/api/visits/reset")
def api_reset_visits():
    need_db()
    return jsonify(live.remove_demo_visits(neo, str(body().get("tourist") or "")))


@app.post("/api/scenario/save")
def api_save_scenario():
    need_db()
    return jsonify(live.save_scenario(neo, body()))


@app.post("/api/scenario/restore")
def api_restore_scenario():
    need_db()
    return jsonify(live.restore_network(neo))


@app.post("/api/verify")
def api_verify():
    need_db()
    p = body()
    traffic = [{"key": str(t["key"]), "factor": float(t["factor"])} for t in (p.get("traffic") or []) if "key" in t]
    return jsonify(live.verify(neo, p.get("algorithm", "dijkstra"), p.get("from"), p.get("to"), p.get("metric", "hours"),
                               _modes(p.get("modes")), [str(k) for k in (p.get("closed") or [])], traffic))


@app.get("/api/evaluate/cases")
def api_eval_cases():
    need_db()
    return jsonify({"cases": live.evaluation_cases(neo), "methods": recommend.METHODS,
                    "attractions": neo.scalar_rows("MATCH (a:Attraction) RETURN count(a) AS n")[0]["n"]})


@app.post("/api/evaluate/one")
def api_eval_one():
    need_db()
    p = body()
    tid, hidden = str(p.get("tourist") or ""), str(p.get("hidden") or "")
    out = {}
    for m in recommend.METHODS:
        ranking = recommend.ranked(neo, m, tid, hidden, 10)
        ids = [r["id"] for r in ranking]
        out[m] = {"rank": ids.index(hidden) + 1 if hidden in ids else None, "ranking": ids,
                  "top": [r["attraction"] for r in ranking[:5]]}
    return jsonify({"tourist": tid, "hidden": hidden, "results": out})


# ---- pre-demo self check ------------------------------------------------------------------------------------
@app.post("/api/selfcheck")
def api_selfcheck():
    need_db()
    checks = []

    def check(name, fn):
        t0 = time.perf_counter()
        try:
            detail = fn()
            checks.append({"name": name, "ok": True, "detail": detail, "ms": (time.perf_counter() - t0) * 1000})
        except Exception as exc:  # noqa: BLE001
            checks.append({"name": name, "ok": False, "detail": neo_error(exc), "ms": (time.perf_counter() - t0) * 1000})

    def expect(cond, msg):
        if not cond:
            raise ValueError(msg)
        return "ok"

    check("Connection", lambda: f"Connected to {config.NEO4J_URI}")
    check("Sample data loaded", lambda: expect(neo.scalar_rows("MATCH (t:Tourist) RETURN count(t) AS n")[0]["n"] >= 20,
                                               "Run script 02 on the Data & model page."))
    check("Constraints", lambda: f"{len(neo.run('SHOW CONSTRAINTS YIELD name RETURN name')['rows'])} constraints")
    for q in catalog.QUERIES:
        def run_q(q=q, graph=False):
            text = catalog.render(q["id"], 5, "hours", graph=graph)
            params = _params_for(q, SAMPLE, text)
            r = neo.run(text, params)
            return f"{len(r['graph']['nodes'])} nodes" if graph else f"{r['rowCount']} rows"
        check(f"{q['section']}: {q['title']}", run_q)
        if q.get("graph"):
            check(f"{q['section']}: {q['title']} (graph view)", lambda q=q: run_q(q, True))
    check("Route planner (Dijkstra + Yen)", lambda: f"{len(RouteGraph.from_neo4j(neo).k_shortest('Chennai', 'Munnar', 3))} routes")
    check("Itinerary optimiser", lambda: " → ".join(RouteGraph.from_neo4j(neo).itinerary('Chennai', ['Madurai', 'Munnar', 'Kochi'])["order"]))
    check("Transport hubs", lambda: RouteGraph.from_neo4j(neo).hubs()["hubs"][0]["destination"])
    check("Hybrid recommendations", lambda: f"{len(recommend.ranked(neo, 'hybrid', 't01'))} recommendations")
    check("3D network", lambda: f"{len(live.network(neo)['routes'])} routes")
    check("Live explore", lambda: live.explore(neo, ["Beach", "Wildlife"], 12, "mid")["rows"][0]["destination"])
    check("Destination details", lambda: f"{len(live.destination(neo, 'Munnar')['attractions'])} attractions in Munnar")
    check("Live recommendations", lambda: f"{len(live.live_recommend(neo, 't01', {'Beach': 3, 'Nature': 1}, 12, RouteGraph.from_neo4j(neo))['fused'])} items")
    check("Explanation paths", lambda: f"{len(live.explain(neo, 't01', 'a54')['graph']['nodes'])} nodes")
    check("Verify route in Cypher (BFS)", lambda: f"{len(live.verify(neo, 'bfs', 'Chennai', 'Munnar', 'hours', MODES, [], [])['rows'])} row(s)")
    check("Verify route in Cypher (weighted)", lambda: f"{len(live.verify(neo, 'dijkstra', 'Chennai', 'Munnar', 'hours', MODES, ['Chennai|Kochi|flight'], [{'key': 'Kochi|Munnar|road', 'factor': 2.0}])['rows'])} row(s)")
    check("Evaluation cases", lambda: f"{len(live.evaluation_cases(neo))} tourists")
    check("Evaluation (leave-one-out)", lambda: f"hybrid hit@10 = {recommend.evaluate(neo)['summary'][3]['hit@10']:.2f}")
    return jsonify({"checks": checks, "passed": sum(c["ok"] for c in checks), "total": len(checks)})


if __name__ == "__main__":
    up = neo.is_available(force=True)
    print("=" * 64)
    print(" TripGraph Live - interactive Tourism Recommendation System (Neo4j)")
    print(f" Open:   http://localhost:{config.FLASK_PORT}")
    if config.FLASK_HOST == "0.0.0.0":
        print(f"         Others: http://<this computer's IP address>:{config.FLASK_PORT}")
    print(f" Neo4j:  {'connected' if up else 'NOT connected'} ({config.NEO4J_URI})")
    if not up:
        print(f"         {neo.last_error}")
    print("=" * 64)
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=config.FLASK_DEBUG, threaded=True)
