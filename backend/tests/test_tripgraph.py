"""Tests that run without Neo4j. From the backend folder:

    python -m unittest discover -s tests -v

The Cypher queries are checked against your database with the "Pre-demo check" button in the app.
"""
import itertools
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from core import catalog, recommend  # noqa: E402
from core.routing import RouteGraph  # noqa: E402
from core.scripts import parse_steps  # noqa: E402
from data import tourism as T  # noqa: E402


def graph():
    dests = [{"name": n, "state": s, "lat": la, "lon": lo} for n, s, la, lo, _m, _d in T.DESTINATIONS]
    routes = [{"from": a, "to": b, "mode": m, "distanceKm": km, "hours": h, "costInr": c} for a, b, m, km, h, c in T.ROUTES]
    return RouteGraph(dests, routes)


def brute_force_best(g, src, dst, metric, modes, max_legs=7):
    """Cheapest loop-free path by trying every path (for checking Dijkstra)."""
    best = float("inf")

    def walk(v, seen, cost, legs):
        nonlocal best
        if cost >= best or legs > max_legs:
            return
        if v == dst:
            best = cost
            return
        for w, e in g.edges[v]:
            if w not in seen and e["mode"] in modes:
                walk(w, seen | {w}, cost + e[metric], legs + 1)
    walk(src, {src}, 0, 0)
    return best


class DataTests(unittest.TestCase):
    def test_references(self):
        dest = {d[0] for d in T.DESTINATIONS}
        self.assertTrue(all(a in dest and b in dest and a != b for a, b, *_ in T.ROUTES))
        self.assertTrue(all(a[2] in dest and set(a[3]) <= set(T.CATEGORIES) for a in T.ATTRACTIONS))
        self.assertTrue(all(h[2] in dest for h in T.HOTELS))
        attractions, hotels, tourists = {a[0] for a in T.ATTRACTIONS}, {h[0] for h in T.HOTELS}, {t[0] for t in T.TOURISTS}
        self.assertTrue(all(t in tourists and a in attractions for t, a, *_ in T.VISITS))
        self.assertTrue(all(t in tourists and h in hotels for t, h, *_ in T.STAYS))
        self.assertTrue(all(t in tourists and d in dest for t, d, _ in T.WISHLIST))
        self.assertTrue(all(set(t[6]) <= set(T.CATEGORIES) and t[3] in dest for t in T.TOURISTS))

    def test_unique_keys_and_pairs(self):
        self.assertEqual(len({a[0] for a in T.ATTRACTIONS}), len(T.ATTRACTIONS))
        self.assertEqual(len({a[1] for a in T.ATTRACTIONS}), len(T.ATTRACTIONS))   # names are used as parameters
        self.assertEqual(len({(t, a) for t, a, *_ in T.VISITS}), len(T.VISITS))
        self.assertEqual(len({(a, b, m) for a, b, m, *_ in T.ROUTES}), len(T.ROUTES))

    def test_data_is_deterministic(self):
        visits, stays, wishes = T._generate_visits()
        self.assertEqual(visits, T.VISITS)
        self.assertEqual(stays, T.STAYS)
        self.assertEqual(wishes, T.WISHLIST)

    def test_everyone_has_enough_visits(self):
        counts = {t[0]: 0 for t in T.TOURISTS}
        for t, *_ in T.VISITS:
            counts[t] += 1
        self.assertTrue(all(c >= 4 for c in counts.values()))


class ScriptTests(unittest.TestCase):
    def test_steps(self):
        steps = parse_steps(os.path.join(config.NEO4J_SCRIPTS_DIR, "02_sample_data.cypher"))
        self.assertEqual([s["number"] for s in steps], list(range(1, 10)))
        self.assertEqual(sum(len(s["statements"]) for s in steps), 11)

    def test_comments_have_no_semicolons(self):
        for name in os.listdir(config.NEO4J_SCRIPTS_DIR):
            with open(os.path.join(config.NEO4J_SCRIPTS_DIR, name), encoding="utf-8") as fh:
                for ln in fh:
                    if ln.strip().startswith("//"):
                        self.assertNotIn(";", ln, f"{name}: {ln}")

    def test_no_python_reprs_in_scripts(self):
        """Nested maps and lists must be Cypher literals, never Python text such as '{'cat': ...}'."""
        with open(os.path.join(config.NEO4J_SCRIPTS_DIR, "02_sample_data.cypher"), encoding="utf-8") as fh:
            text = fh.read()
        for bad in ("'{", "'[", "\\'cat\\'", "None", "True", "False"):
            self.assertNotIn(bad, text, bad)
        self.assertIn("interests: [{cat: 'Beach', w: 3}", text)

    def test_queries_file_needs_no_parameters(self):
        """03_queries.cypher must run in Neo4j Browser without :param, so no $name outside comments."""
        with open(os.path.join(config.NEO4J_SCRIPTS_DIR, "03_queries.cypher"), encoding="utf-8") as fh:
            code = [ln for ln in fh if not ln.strip().startswith("//")]
        self.assertFalse([ln for ln in code if "$" in ln])
        steps = parse_steps(os.path.join(config.NEO4J_SCRIPTS_DIR, "03_queries.cypher"))
        self.assertEqual(len(steps), len(catalog.QUERIES))
        self.assertTrue(all(len(st["statements"]) == 1 for st in steps))

    def test_scripts_up_to_date(self):
        import subprocess

        def read(n):
            with open(os.path.join(config.NEO4J_SCRIPTS_DIR, n), encoding="utf-8") as fh:
                return fh.read()
        before = {n: read(n) for n in ("02_sample_data.cypher", "03_queries.cypher")}
        subprocess.run([sys.executable, os.path.join(config.BASE_DIR, "tools", "generate_cypher.py")], check=True, capture_output=True)
        for n, text in before.items():
            self.assertEqual(text, read(n), n)


class CatalogTests(unittest.TestCase):
    def test_well_formed(self):
        for q in catalog.QUERIES:
            for variant in (False, True):
                text = catalog.render(q["id"], 5, "distanceKm", graph=variant)
                self.assertNotIn("{maxHops}", text)
                self.assertNotIn("{metric}", text)
                for ch_open, ch_close in ("()", "[]", "{}"):
                    self.assertEqual(text.count(ch_open), text.count(ch_close), (q["id"], variant))
            text = catalog.render(q["id"])
            for p in q["params"]:
                if p not in ("maxHops", "metric"):
                    self.assertIn("$" + p, text, q["id"])

    def test_render_guards(self):
        with self.assertRaises(ValueError):
            catalog.render("best_routes", 9)
        with self.assertRaises(ValueError):
            catalog.render("best_routes", 3, "rating")


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.g = graph()

    def test_dijkstra_matches_brute_force(self):
        pairs = [("Chennai", "Munnar"), ("Hampi", "Kanyakumari"), ("Ooty", "Rameswaram"), ("Tirupati", "Varkala")]
        for metric in ("hours", "distanceKm", "costInr"):
            for modes in (("road", "rail", "flight"), ("road",), ("road", "rail")):
                for a, b in pairs:
                    p = self.g.path(a, b, metric, modes)
                    best = brute_force_best(self.g, a, b, metric, modes, max_legs=12)
                    if p is None:
                        self.assertEqual(best, float("inf"))
                    else:
                        self.assertAlmostEqual(p[metric], best, places=6, msg=(a, b, metric, modes))

    def test_yen_alternatives(self):
        routes = self.g.k_shortest("Chennai", "Munnar", 5, "hours")
        self.assertGreaterEqual(len(routes), 3)
        totals = [r["hours"] for r in routes]
        self.assertEqual(totals, sorted(totals))
        self.assertEqual(len({tuple(r["stops"]) for r in routes}), len(routes))
        for r in routes:
            self.assertEqual(len(r["stops"]), len(set(r["stops"])))          # loop-free
            self.assertEqual(r["stops"][0], "Chennai")
            self.assertEqual(r["stops"][-1], "Munnar")

    def test_itinerary_is_optimal(self):
        stops = ["Madurai", "Munnar", "Kochi", "Ooty"]
        res = self.g.itinerary("Chennai", stops, "distanceKm")
        best = min(sum(self.g.path(x, y, "distanceKm")["distanceKm"] for x, y in zip(seq, seq[1:]))
                   for seq in (["Chennai", *o] for o in itertools.permutations(stops)))
        self.assertAlmostEqual(res["cost"], best)
        self.assertEqual(res["ordersTried"], 24)
        self.assertLessEqual(res["cost"], res["asEnteredCost"])

    def test_mode_filter(self):
        rail = self.g.path("Chennai", "Bengaluru", "hours", ("rail",))
        self.assertEqual(rail["modes"], ["rail"])
        self.assertIsNone(self.g.path("Chennai", "Munnar", "hours", ("flight",)))

    def test_hubs_and_connectivity(self):
        h = self.g.hubs()
        self.assertEqual(len(h["components"]), 1)
        self.assertTrue(all(0 <= x["betweenness"] <= 1 for x in h["hubs"]))
        reach = self.g.reachable("Chennai", 4)
        self.assertTrue(all(r["hours"] <= 4 for r in reach))
        self.assertIn("Mahabalipuram", [r["destination"] for r in reach])


class RecommendTests(unittest.TestCase):
    def test_rrf(self):
        a = [{"id": "x", "attraction": "X", "destination": "D"}, {"id": "y", "attraction": "Y", "destination": "D"}]
        b = [{"id": "y", "attraction": "Y", "destination": "D"}, {"id": "z", "attraction": "Z", "destination": "D"}]
        fused = recommend.rrf({"content": a, "collaborative": b})
        self.assertEqual(fused[0]["id"], "y")                       # in both lists
        self.assertEqual(fused[0]["ranks"], {"content": 2, "collaborative": 1})

    def test_metrics(self):
        res = [{"hidden": "a", "ranking": ["a", "b"]}, {"hidden": "c", "ranking": ["b", "x", "y", "z", "w", "c"]},
               {"hidden": "d", "ranking": ["b"]}]
        m = recommend.metrics(res, n_items=10)
        self.assertAlmostEqual(m["hit@5"], 1 / 3)
        self.assertAlmostEqual(m["hit@10"], 2 / 3)
        self.assertAlmostEqual(m["mrr@10"], (1 + 1 / 6) / 3)
        self.assertAlmostEqual(m["coverage"], 0.7)


class AppTests(unittest.TestCase):
    def test_offline_endpoints(self):
        from app import WRITE_RE, _strip, app
        c = app.test_client()
        self.assertEqual(c.get("/api/meta").status_code, 200)
        self.assertEqual(len(c.get("/api/setup/steps").get_json()["sample"]), 9)
        self.assertTrue(WRITE_RE.search(_strip("MATCH (n) DETACH DELETE n")))
        self.assertFalse(WRITE_RE.search(_strip("MATCH (a:Attraction {name: 'Create Set'}) RETURN a // merge")))


if __name__ == "__main__":
    unittest.main()


class LiveTests(unittest.TestCase):
    """Pure logic behind the interactive pages (the Cypher runs in the pre-demo check)."""

    def test_explore_score(self):
        from core.live import explore_score
        great = {"matching": 4, "rating": 4.6, "inSeason": True, "hotels": 2}
        poor = {"matching": 0, "rating": 0.0, "inSeason": False, "hotels": 0}
        self.assertGreater(explore_score(great, True), explore_score(poor, True))
        self.assertEqual(explore_score(poor, True), 0.0)
        self.assertLessEqual(explore_score(great, True), 10.5)

    def test_clean_weights(self):
        from core.live import clean_weights
        self.assertEqual(clean_weights({"Beach": 3, "Temple": 0}), [{"cat": "Beach", "weight": 3.0}])
        for bad in ({"Beach": 9}, {"Beach": "x"}, ["Beach"]):
            with self.assertRaises(ValueError):
                clean_weights(bad)

    def test_destination_ranking(self):
        from core.live import destination_ranking
        content = [{"destination": "Munnar", "attraction": "Tea", "score": 9.0, "matched": ["Nature"]},
                   {"destination": "Munnar", "attraction": "Park", "score": 8.0, "matched": ["Wildlife"]},
                   {"destination": "Hampi", "attraction": "Temple", "score": 9.0, "matched": ["Heritage"]}]
        out = destination_ranking(content, {"Munnar"}, {"Munnar": 5.0, "Hampi": 6.5})
        self.assertEqual(out[0]["destination"], "Munnar")
        self.assertEqual(out[0]["because"], ["Nature", "Wildlife"])
        self.assertTrue(out[0]["inSeason"])

    def test_save_scenario_validation(self):
        from core import live

        class Counters:
            properties_set = 1
            relationships_created = 0

        class Neo:
            def __init__(self):
                self.calls = []

            def write_rows(self, cypher, params=None):
                self.calls.append(params)
                return [], Counters()

        neo = Neo()
        res = live.save_scenario(neo, {"closed": [{"from": "Kochi", "to": "Munnar", "mode": "road"}],
                                       "traffic": [{"from": "Chennai", "to": "Mahabalipuram", "mode": "road", "factor": 2}],
                                       "added": [{"from": "Kochi", "to": "Madurai", "mode": "road", "distanceKm": 260, "hours": 5.2, "costInr": 2900}]})
        self.assertEqual(len(res["steps"]), len(live.SAVE_SCENARIO))
        self.assertEqual(neo.calls[0]["closed"][0]["to"], "Munnar")
        for bad in ({"traffic": [{"from": "a", "to": "b", "mode": "road", "factor": 9}]},
                    {"added": [{"from": "a", "to": "a", "mode": "road", "distanceKm": 1, "hours": 1}]},
                    {"closed": [{"from": "a"}]}):
            with self.assertRaises(ValueError):
                live.save_scenario(neo, bad)

    def test_verify_renders_valid_cypher(self):
        from core import live

        class Neo:
            def run(self, cypher, params=None, max_rows=5):
                self.cypher, self.params = cypher, params
                return {"columns": [], "rows": [], "timing": {"serverMs": 1}}

        neo = Neo()
        live.verify(neo, "dijkstra", "Chennai", "Munnar", "distanceKm", ("road",), ["Kochi|Munnar|road"], [{"key": "x", "factor": 2}])
        self.assertNotIn("{metric}", neo.cypher)
        self.assertNotIn("{maxHops}", neo.cypher)
        self.assertIn("r.distanceKm", neo.cypher)
        self.assertEqual(neo.params["traffic"], [])          # traffic only changes hours
        for o, c in ("()", "[]", "{}"):
            self.assertEqual(neo.cypher.count(o), neo.cypher.count(c))
        live.verify(neo, "bfs", "Chennai", "Munnar", "hours", ("road",), [], [])
        self.assertIn("shortestPath", neo.cypher)
        with self.assertRaises(ValueError):
            live.verify(neo, "dijkstra", "Chennai", "Chennai", "hours", ("road",), [], [])

    def test_route_queries_respect_closures(self):
        for qid in ("fewest_stops", "all_fewest_stops", "best_routes", "avoid_route", "via_route", "reachable", "wishlist_routes"):
            self.assertIn("coalesce(r.closed, false)", catalog.render(qid), qid)

    def test_frontend_vendor_files(self):
        root = os.path.join(config.FRONTEND_DIR)
        for f in ("vendor/three.module.min.js", "vendor/OrbitControls.js", "vendor/CSS2DRenderer.js", "js/app.js", "js/scene.js"):
            self.assertTrue(os.path.exists(os.path.join(root, f)), f)
