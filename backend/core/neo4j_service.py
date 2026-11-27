"""Neo4j access for the lab.

* Read queries run with READ access mode, so the database itself refuses writes.
* Results are converted into (a) a table for display and (b) a graph (nodes + relationships)
  extracted from any Node, Relationship or Path values, for the visual graph view.
* PROFILE plans are summarised (operators, rows, database hits) for the evaluation exercise.
"""
import logging
import time

logging.getLogger("neo4j").setLevel(logging.ERROR)

try:
    from neo4j import GraphDatabase, Query, READ_ACCESS, WRITE_ACCESS
    from neo4j.graph import Node, Path, Relationship
except ImportError:  # pragma: no cover
    GraphDatabase = Query = None
    Node = Path = Relationship = ()
    READ_ACCESS, WRITE_ACCESS = "READ", "WRITE"


# ---- value conversion ---------------------------------------------------------------------
def _props(entity):
    return {k: plain(v) for k, v in dict(entity).items()}


def plain(v):
    """Convert driver values into JSON-friendly Python values."""
    if isinstance(v, Path):
        return {"_path": [node_label(n) for n in v.nodes], "length": len(v.relationships)}
    if isinstance(v, Node):
        return {"_node": node_label(v), "labels": sorted(v.labels), "properties": _props(v)}
    if isinstance(v, Relationship):
        return {"_rel": v.type, "properties": _props(v)}
    if isinstance(v, list):
        return [plain(x) for x in v]
    if isinstance(v, dict):
        return {k: plain(x) for k, x in v.items()}
    if hasattr(v, "iso_format"):                    # neo4j.time Date / DateTime / Duration
        return v.iso_format()
    if isinstance(v, float) and v != v:             # NaN
        return None
    return v


def node_label(n):
    p = dict(n)
    return str(p.get("name") or p.get("title") or p.get("text") or p.get("userId") or next(iter(sorted(n.labels)), "node"))


class GraphCollector:
    """Collect nodes and relationships found anywhere in a result."""

    def __init__(self):
        self.nodes, self.rels = {}, {}

    def add(self, v):
        if isinstance(v, Path):
            for n in v.nodes:
                self.add(n)
            for r in v.relationships:
                self.add(r)
        elif isinstance(v, Node):
            if v.element_id not in self.nodes:
                self.nodes[v.element_id] = {"id": v.element_id, "labels": sorted(v.labels),
                                            "caption": node_label(v), "properties": _props(v)}
        elif isinstance(v, Relationship):
            if v.element_id not in self.rels:
                for end in (v.start_node, v.end_node):
                    if end is not None:
                        self.add(end)
                self.rels[v.element_id] = {"id": v.element_id, "type": v.type,
                                           "source": v.start_node.element_id, "target": v.end_node.element_id,
                                           "properties": _props(v)}
        elif isinstance(v, (list, tuple)):
            for x in v:
                self.add(x)
        elif isinstance(v, dict):
            for x in v.values():
                self.add(x)

    def result(self):
        rels = [r for r in self.rels.values() if r["source"] in self.nodes and r["target"] in self.nodes]
        return {"nodes": list(self.nodes.values()), "relationships": rels}


def summarise_plan(plan):
    """Flatten a PROFILE/EXPLAIN plan into rows: depth, operator, rows, dbHits, details."""
    if not plan:
        return None, 0
    out = []

    def get(d, *keys, default=None):
        for k in keys:
            if isinstance(d, dict) and k in d:
                return d[k]
            if hasattr(d, k):
                return getattr(d, k)
        return default

    def walk(p, depth):
        args = get(p, "args", "arguments", default={}) or {}
        hits = get(p, "dbHits", "db_hits", default=None)
        if hits is None:
            hits = args.get("DbHits")
        rows = get(p, "rows", default=None)
        if rows is None:
            rows = args.get("Rows")
        out.append({"depth": depth, "operator": str(get(p, "operatorType", "operator_type", default="?")).split("@")[0],
                    "rows": rows, "dbHits": hits, "details": str(args.get("Details", ""))[:160]})
        for c in get(p, "children", default=[]) or []:
            walk(c, depth + 1)

    walk(plan, 0)
    total = sum(r["dbHits"] or 0 for r in out)
    return out, total


class Neo4jService:
    RETRY_SECONDS = 10

    def __init__(self, uri, user, password, database):
        self.uri, self.user, self.password, self.database = uri, user, password, database
        self._driver = None
        self._available = False
        self._checked = 0.0
        self.last_error = None

    def _get_driver(self):
        if GraphDatabase is None:
            raise RuntimeError("The 'neo4j' package is not installed (pip install -r requirements.txt).")
        if self._driver is None:
            self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password), connection_timeout=4.0)
        return self._driver

    def is_available(self, force=False):
        now = time.monotonic()
        if not force and now - self._checked < self.RETRY_SECONDS:
            return self._available
        self._checked = now
        try:
            self._get_driver().verify_connectivity()
            self._available, self.last_error = True, None
        except Exception as exc:  # noqa: BLE001
            self._available, self.last_error = False, str(exc) or exc.__class__.__name__
            self.close()
        return self._available

    def close(self):
        if self._driver is not None:
            try:
                self._driver.close()
            except Exception:  # noqa: BLE001
                pass
            self._driver = None

    # ---- running queries ---------------------------------------------------------------------
    def run(self, cypher, params=None, write=False, profile=False, max_rows=500, timeout=20):
        """Run one statement. Returns columns, rows, graph, counters, timing and an optional plan."""
        text = ("PROFILE " + cypher) if profile else cypher
        mode = WRITE_ACCESS if write else READ_ACCESS
        t0 = time.perf_counter()
        with self._get_driver().session(database=self.database, default_access_mode=mode) as session:
            # a Query object carries the timeout; extra keyword arguments to run() would be parameters
            result = session.run(Query(text, timeout=timeout), params or {})
            keys = list(result.keys())
            rows, collector, truncated = [], GraphCollector(), False
            for i, record in enumerate(result):
                if i >= max_rows:
                    truncated = True
                    continue                       # keep consuming so the summary is complete
                values = list(record.values())
                collector.add(values)
                rows.append([plain(v) for v in values])
            summary = result.consume()
        wall = (time.perf_counter() - t0) * 1000
        plan, hits = summarise_plan(summary.profile if profile else None)
        c = summary.counters
        counters = {k: getattr(c, k) for k in ("nodes_created", "nodes_deleted", "relationships_created",
                                                "relationships_deleted", "properties_set", "labels_added",
                                                "constraints_added", "indexes_added") if getattr(c, k, 0)}
        return {
            "columns": keys, "rows": rows, "rowCount": len(rows), "truncated": truncated,
            "graph": collector.result(), "counters": counters,
            "timing": {"wallMs": wall, "serverMs": (summary.result_available_after or 0) + (summary.result_consumed_after or 0)},
            "plan": plan, "dbHits": hits if profile else None,
        }

    def scalar_rows(self, cypher, params=None):
        with self._get_driver().session(database=self.database, default_access_mode=READ_ACCESS) as session:
            return [r.data() for r in session.run(cypher, params or {})]

    def write_rows(self, cypher, params=None):
        with self._get_driver().session(database=self.database, default_access_mode=WRITE_ACCESS) as session:
            result = session.run(cypher, params or {})
            data = [r.data() for r in result]
            return data, result.consume().counters
