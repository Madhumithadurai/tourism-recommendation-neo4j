"""Route planning on the ROUTE graph read from Neo4j.

Cypher answers route questions by enumerating paths (shortestPath for fewest stops; variable-length
patterns + reduce() for fastest / shortest / cheapest within k legs). Weighted shortest paths over
the whole graph and multi-stop itineraries need classic algorithms, which Neo4j offers in the Graph
Data Science plugin. To stay plugin-free they are implemented here and their answers are compared
with the Cypher results in the app:

* Dijkstra (1959)            optimal route for one metric (hours, distanceKm or costInr), mode filters
* Yen (1971)                 k shortest loop-free paths: genuine alternative routes
* Itinerary optimisation     best visiting order for up to 7 stops (exact, tries every order)
* Brandes betweenness        transport hubs that many fastest routes pass through
"""
import heapq
import itertools
from collections import deque

METRICS = {"hours": "hours", "distanceKm": "km", "costInr": "INR"}
MODES = ("road", "rail", "flight")


class RouteGraph:
    def __init__(self, destinations, routes):
        """destinations: [{name, lat, lon, state}], routes: [{from, to, mode, distanceKm, hours, costInr}]"""
        self.dest = {d["name"]: d for d in destinations}
        self.edges = {n: [] for n in self.dest}
        for r in routes:
            a, b = r["from"], r["to"]
            if a in self.edges and b in self.edges:
                e = {k: r[k] for k in ("mode", "distanceKm", "hours", "costInr")}
                self.edges[a].append((b, e))
                self.edges[b].append((a, e))
        self.routes = routes

    @classmethod
    def from_neo4j(cls, neo):
        dests = neo.scalar_rows("""MATCH (d:Destination)
            RETURN d.name AS name, d.state AS state, d.lat AS lat, d.lon AS lon ORDER BY name""")
        routes = neo.scalar_rows("""MATCH (a:Destination)-[r:ROUTE]->(b:Destination)
            WHERE NOT coalesce(r.closed, false)
            RETURN a.name AS from, b.name AS to, r.mode AS mode, r.distanceKm AS distanceKm,
                   r.hours * coalesce(r.trafficFactor, 1.0) AS hours, r.costInr AS costInr""")
        return cls(dests, routes)

    def check(self, *names):
        for n in names:
            if n not in self.dest:
                raise ValueError(f"Unknown destination '{n}'.")

    def best_edge(self, a, b, metric, modes, banned=frozenset()):
        best = None
        for nb, e in self.edges[a]:
            if nb == b and e["mode"] in modes and (a, b) not in banned and (b, a) not in banned:
                if best is None or e[metric] < best[metric]:
                    best = e
        return best

    # ---- Dijkstra ------------------------------------------------------------------------------
    def dijkstra(self, src, metric="hours", modes=MODES, banned_nodes=frozenset(), banned_edges=frozenset()):
        dist, prev = {src: 0.0}, {src: None}
        heap = [(0.0, src)]
        done = set()
        while heap:
            d, v = heapq.heappop(heap)
            if v in done:
                continue
            done.add(v)
            for w, e in self.edges[v]:
                if e["mode"] not in modes or w in banned_nodes:
                    continue
                if (v, w) in banned_edges or (w, v) in banned_edges:
                    continue
                nd = d + e[metric]
                if nd < dist.get(w, float("inf")):
                    dist[w], prev[w] = nd, (v, e)
                    heapq.heappush(heap, (nd, w))
        return dist, prev

    def path(self, src, dst, metric="hours", modes=MODES, banned_nodes=frozenset(), banned_edges=frozenset()):
        dist, prev = self.dijkstra(src, metric, modes, banned_nodes, banned_edges)
        if dst not in dist:
            return None
        legs, v = [], dst
        while prev[v] is not None:
            u, e = prev[v]
            legs.append({"from": u, "to": v, **e})
            v = u
        legs.reverse()
        return self._summary([src] + [l["to"] for l in legs], legs)

    def _summary(self, stops, legs):
        return {"stops": stops, "legs": legs, "hops": len(legs),
                "hours": round(sum(l["hours"] for l in legs), 2),
                "distanceKm": sum(l["distanceKm"] for l in legs),
                "costInr": sum(l["costInr"] for l in legs),
                "modes": sorted({l["mode"] for l in legs})}

    # ---- Yen's k shortest loop-free paths --------------------------------------------------------
    def k_shortest(self, src, dst, k=4, metric="hours", modes=MODES):
        self.check(src, dst)
        first = self.path(src, dst, metric, modes)
        if not first:
            return []
        found, candidates = [first], []
        seen = {tuple(first["stops"])}
        for _ in range(1, k):
            last = found[-1]
            for i in range(len(last["stops"]) - 1):
                spur, root = last["stops"][i], last["stops"][:i + 1]
                banned_edges = set()
                for p in found:
                    if p["stops"][:i + 1] == root and len(p["stops"]) > i + 1:
                        banned_edges.add((p["stops"][i], p["stops"][i + 1]))
                banned_nodes = frozenset(root[:-1])
                spur_path = self.path(spur, dst, metric, modes, banned_nodes, frozenset(banned_edges))
                if not spur_path:
                    continue
                stops = root[:-1] + spur_path["stops"]
                if tuple(stops) in seen:
                    continue
                legs = []
                for a, b in zip(stops, stops[1:]):
                    e = self.best_edge(a, b, metric, modes)
                    legs.append({"from": a, "to": b, **e})
                cand = self._summary(stops, legs)
                seen.add(tuple(stops))
                heapq.heappush(candidates, (cand[metric], len(stops), next(_counter), cand))
            if not candidates:
                break
            found.append(heapq.heappop(candidates)[3])
        return found

    # ---- itinerary ---------------------------------------------------------------------------------
    def itinerary(self, start, stops, metric="hours", modes=MODES, return_home=False):
        stops = [s for s in dict.fromkeys(stops) if s != start]
        self.check(start, *stops)
        if not stops:
            raise ValueError("Choose at least one place to visit.")
        if len(stops) > 7:
            raise ValueError("At most 7 stops (7! = 5,040 orders are checked exactly).")
        pts = [start] + stops
        table = {}
        for a in pts:
            dist, _ = self.dijkstra(a, metric, modes)
            for b in pts:
                table[(a, b)] = dist.get(b, float("inf"))
        best, best_cost, tried = None, float("inf"), 0
        for order in itertools.permutations(stops):
            seq = [start, *order] + ([start] if return_home else [])
            cost = sum(table[(x, y)] for x, y in zip(seq, seq[1:]))
            tried += 1
            if cost < best_cost:
                best, best_cost = seq, cost
        if best is None or best_cost == float("inf"):
            raise ValueError("Some stops cannot be reached with the selected travel modes.")
        naive = [start, *stops] + ([start] if return_home else [])
        naive_cost = sum(table[(x, y)] for x, y in zip(naive, naive[1:]))
        legs = []
        for x, y in zip(best, best[1:]):
            p = self.path(x, y, metric, modes)
            legs.append(p)
        return {"order": best, "cost": round(best_cost, 2), "metric": metric, "ordersTried": tried,
                "asEnteredOrder": naive, "asEnteredCost": round(naive_cost, 2) if naive_cost != float("inf") else None,
                "segments": legs,
                "totals": {"hours": round(sum(p["hours"] for p in legs), 2), "distanceKm": sum(p["distanceKm"] for p in legs),
                           "costInr": sum(p["costInr"] for p in legs)}}

    # ---- connectivity ---------------------------------------------------------------------------------
    def reachable(self, src, max_value, metric="hours", modes=MODES):
        self.check(src)
        dist, _ = self.dijkstra(src, metric, modes)
        return sorted([{"destination": d, metric: round(v, 2)} for d, v in dist.items() if d != src and v <= max_value],
                      key=lambda r: r[metric])

    def hubs(self):
        """Degree and betweenness on the fastest-route graph (hours, all modes)."""
        names = sorted(self.dest)
        bc = dict.fromkeys(names, 0.0)
        for s in names:
            dist, sigma, preds, order = {s: 0.0}, {s: 1.0}, {s: []}, []
            heap, done = [(0.0, s)], set()
            while heap:
                d, v = heapq.heappop(heap)
                if v in done:
                    continue
                done.add(v)
                order.append(v)
                for w, e in self.edges[v]:
                    nd = d + e["hours"]
                    if nd < dist.get(w, float("inf")) - 1e-9:
                        dist[w], sigma[w], preds[w] = nd, 0.0, []
                        heapq.heappush(heap, (nd, w))
                    if abs(nd - dist.get(w, float("inf"))) < 1e-9:
                        sigma[w] += sigma[v]
                        preds[w].append(v)
            delta = dict.fromkeys(order, 0.0)
            for w in reversed(order):
                for v in preds[w]:
                    delta[v] += sigma[v] / sigma[w] * (1 + delta[w])
                if w != s:
                    bc[w] += delta[w]
        n = len(names)
        scale = 1 / ((n - 1) * (n - 2)) if n > 2 else 1
        degree = {d: len({w for w, _ in self.edges[d]}) for d in names}
        comps, seen = [], set()
        for d in names:
            if d in seen:
                continue
            q, comp = deque([d]), []
            seen.add(d)
            while q:
                v = q.popleft()
                comp.append(v)
                for w, _ in self.edges[v]:
                    if w not in seen:
                        seen.add(w)
                        q.append(w)
            comps.append(sorted(comp))
        return {"hubs": sorted([{"destination": d, "connections": degree[d], "routes": len(self.edges[d]),
                                 "betweenness": round(bc[d] * scale, 4)} for d in names], key=lambda r: -r["betweenness"]),
                "components": comps}

    def map_data(self):
        return {"destinations": list(self.dest.values()), "routes": self.routes}


_counter = itertools.count()
