"""Hybrid recommendations and offline evaluation.

Hybrid = Reciprocal Rank Fusion (Cormack et al., 2009) of the content-based and collaborative Cypher
recommenders: score(item) = sum over lists of 1 / (60 + rank). Items found by both lists rise to the top.

Evaluation = leave-one-out. For every tourist with at least 4 visits, the most recent visit is hidden
($hidden in the Cypher queries treats it as unknown). Each recommender then produces a top-10 list and we
check whether the hidden attraction appears:
* HitRate@k : share of tourists whose hidden attraction is in the top k
* MRR@10    : mean of 1 / rank of the hidden attraction (0 if absent)
* Coverage  : share of all attractions that appear in at least one top-10 list
The SAME Cypher queries shown in the app are evaluated, not a separate re-implementation.
"""
from .catalog import render

RRF_K = 60
METHODS = {"popular": "Popularity (baseline)", "content": "Content-based", "collaborative": "Collaborative filtering",
           "hybrid": "Hybrid (rank fusion)"}


def rrf(lists, k=RRF_K, limit=10):
    """lists: {name: [rows with 'id']} -> fused rows with score and the ranks in each list."""
    fused = {}
    for name, rows in lists.items():
        for rank, row in enumerate(rows, 1):
            item = fused.setdefault(row["id"], {"id": row["id"], "attraction": row["attraction"],
                                                 "destination": row["destination"], "score": 0.0, "ranks": {}})
            item["score"] += 1.0 / (k + rank)
            item["ranks"][name] = rank
    out = sorted(fused.values(), key=lambda r: (-r["score"], r["attraction"]))
    for r in out:
        r["score"] = round(r["score"], 5)
    return out[:limit]


def ranked(neo, method, tourist, hidden=None, limit=10):
    if method == "hybrid":
        lists = {m: ranked(neo, m, tourist, hidden, 20) for m in ("content", "collaborative")}
        return rrf(lists, limit=limit)
    res = neo.run(render(method), {"tourist": tourist, "hidden": hidden, "limit": limit})
    idx = {c: i for i, c in enumerate(res["columns"])}
    return [{"id": r[idx["id"]], "attraction": r[idx["attraction"]], "destination": r[idx["destination"]]} for r in res["rows"]]


def metrics(results, n_items, ks=(5, 10)):
    """results: [{"hidden": id, "ranking": [ids]}] -> HitRate@k, MRR@10 and coverage."""
    out = {}
    n = len(results) or 1
    for k in ks:
        out[f"hit@{k}"] = sum(1 for r in results if r["hidden"] in r["ranking"][:k]) / n
    mrr = 0.0
    for r in results:
        if r["hidden"] in r["ranking"][:10]:
            mrr += 1.0 / (r["ranking"].index(r["hidden"]) + 1)
    out["mrr@10"] = mrr / n
    shown = {i for r in results for i in r["ranking"][:10]}
    out["coverage"] = len(shown) / n_items if n_items else 0.0
    return out


def evaluate(neo, min_visits=4):
    visits = neo.scalar_rows("""
        MATCH (t:Tourist)-[v:VISITED]->(a:Attraction)
        RETURN t.touristId AS tourist, t.name AS name, a.attractionId AS id, a.name AS attraction, v.date AS date
        ORDER BY tourist, date, id""")
    n_items = neo.scalar_rows("MATCH (a:Attraction) RETURN count(a) AS n")[0]["n"]
    by_t = {}
    for v in visits:
        by_t.setdefault(v["tourist"], []).append(v)
    cases = [(t, vs[-1]) for t, vs in by_t.items() if len(vs) >= min_visits]
    if not cases:
        raise ValueError("No tourists with enough visits. Load the sample data first.")
    per_method = {m: [] for m in METHODS}
    rows = []
    for tid, hidden in cases:
        row = {"tourist": hidden["name"], "hidden": hidden["attraction"], "ranks": {}}
        for m in METHODS:
            ranking = [r["id"] for r in ranked(neo, m, tid, hidden["id"], 10)]
            per_method[m].append({"hidden": hidden["id"], "ranking": ranking})
            row["ranks"][m] = ranking.index(hidden["id"]) + 1 if hidden["id"] in ranking else None
        rows.append(row)
    summary = [{"method": m, "label": METHODS[m], **metrics(per_method[m], n_items)} for m in METHODS]
    return {"tourists": len(cases), "attractions": n_items, "summary": summary, "rows": rows,
            "protocol": "Leave-one-out: each tourist's most recent visit is hidden and must be predicted in the top 10."}
