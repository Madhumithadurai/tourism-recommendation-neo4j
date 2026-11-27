/* Route-finding algorithms written as generators: every yield is one visible step
   (push into the frontier, pop/expand, relax an edge), so the 3D map can animate the search.
   The graph is built from the Neo4j network, minus closed routes, with traffic applied to hours. */
import { haversine } from './util.js';

export const routeKey = (r) => `${r.from}|${r.to}|${r.mode}`;

export function buildGraph(destinations, routes, { modes, closed, traffic, metric }) {
  const nodes = new Map(destinations.map((d) => [d.name, d]));
  const adj = new Map(destinations.map((d) => [d.name, []]));
  for (const r of routes) {
    const key = routeKey(r);
    if (!modes.includes(r.mode) || closed.has(key) || !adj.has(r.from) || !adj.has(r.to)) continue;
    const hours = r.hours * (traffic.get(key) || 1);
    const w = metric === 'hours' ? hours : r[metric];
    const leg = { key, route: r, mode: r.mode, hours, distanceKm: r.distanceKm, costInr: r.costInr, w };
    adj.get(r.from).push({ ...leg, to: r.to });
    adj.get(r.to).push({ ...leg, to: r.from });
  }
  // admissible A* bound: no leg covers straight-line distance faster than the best ratio seen in the data
  let ratio = 0;
  for (const [a, edges] of adj) for (const e of edges) if (e.w > 0) ratio = Math.max(ratio, haversine(nodes.get(a), nodes.get(e.to)) / e.w);
  return { nodes, adj, metric, ratio: ratio || 1 };
}

export const heuristic = (g, node, goal) => haversine(g.nodes.get(node), g.nodes.get(goal)) / g.ratio;

class Heap {
  constructor() { this.a = []; }
  get size() { return this.a.length; }
  push(x) { const a = this.a; a.push(x); let i = a.length - 1; while (i > 0) { const p = (i - 1) >> 1; if (a[p].f <= a[i].f) break; [a[p], a[i]] = [a[i], a[p]]; i = p; } }
  pop() {
    const a = this.a, top = a[0], last = a.pop();
    if (a.length) { a[0] = last; let i = 0; for (;;) { const l = 2 * i + 1, r = l + 1; let m = i; if (l < a.length && a[l].f < a[m].f) m = l; if (r < a.length && a[r].f < a[m].f) m = r; if (m === i) break; [a[m], a[i]] = [a[i], a[m]]; i = m; } }
    return top;
  }
  top(k) { return [...this.a].sort((x, y) => x.f - y.f).slice(0, k); }
}

function pathFrom(prev, start, goal, metric) {
  const legs = [];
  let v = goal;
  while (v !== start) { const e = prev.get(v); legs.push({ ...e, from: e.fromNode, to: v }); v = e.fromNode; }
  legs.reverse();
  const totals = { hours: 0, distanceKm: 0, costInr: 0 };
  legs.forEach((l) => { totals.hours += l.hours; totals.distanceKm += l.distanceKm; totals.costInr += l.costInr; });
  return { nodes: [start, ...legs.map((l) => l.to)], legs, totals, cost: totals[metric] };
}

/* Dijkstra, A* and greedy best-first differ only in the priority f. */
export function* bestFirst(g, start, goal, kind, banned = {}) {
  const h = (n) => (kind === 'dijkstra' ? 0 : heuristic(g, n, goal));
  const prio = (gv, n) => (kind === 'greedy' ? h(n) : gv + h(n));
  const dist = new Map([[start, 0]]), prev = new Map(), done = new Set();
  const heap = new Heap();
  const snap = () => {
    const seen = new Set();
    return heap.top(40).filter((x) => !done.has(x.node) && x.g <= dist.get(x.node) + 1e-9 && !seen.has(x.node) && seen.add(x.node)).slice(0, 6).map((x) => ({ node: x.node, f: x.f, g: x.g }));
  };
  heap.push({ node: start, g: 0, f: prio(0, start) });
  yield { t: 'push', node: start, g: 0, f: prio(0, start), frontier: snap(), size: heap.size };
  while (heap.size) {
    const cur = heap.pop();
    if (done.has(cur.node) || cur.g > dist.get(cur.node) + 1e-9) continue;
    done.add(cur.node);
    yield { t: 'pop', node: cur.node, g: cur.g, f: cur.f, frontier: snap(), size: heap.size };
    if (cur.node === goal) { yield { t: 'found', path: pathFrom(prev, start, goal, g.metric) }; return; }
    for (const e of g.adj.get(cur.node)) {
      if (done.has(e.to) || (banned.nodes && banned.nodes.has(e.to)) || (banned.edges && banned.edges.has(e.key))) continue;
      const nd = cur.g + e.w;
      const improved = nd < (dist.has(e.to) ? dist.get(e.to) : Infinity) - 1e-9;
      yield { t: 'relax', key: e.key, from: cur.node, to: e.to, g: nd, improved };
      if (improved) {
        dist.set(e.to, nd);
        prev.set(e.to, { ...e, fromNode: cur.node });
        heap.push({ node: e.to, g: nd, f: prio(nd, e.to) });
        yield { t: 'push', node: e.to, g: nd, f: prio(nd, e.to), frontier: snap(), size: heap.size };
      }
    }
  }
  yield { t: 'fail' };
}

/* Breadth-first search: fewest legs, ignores weights. */
export function* bfs(g, start, goal) {
  const prev = new Map(), seen = new Set([start]), depth = new Map([[start, 0]]);
  const queue = [start];
  const snap = () => queue.slice(0, 6).map((n) => ({ node: n, f: depth.get(n), g: depth.get(n) }));
  yield { t: 'push', node: start, g: 0, f: 0, frontier: snap(), size: queue.length };
  while (queue.length) {
    const u = queue.shift();
    yield { t: 'pop', node: u, g: depth.get(u), f: depth.get(u), frontier: snap(), size: queue.length };
    if (u === goal) { yield { t: 'found', path: pathFrom(prev, start, goal, g.metric) }; return; }
    for (const e of g.adj.get(u)) {
      const fresh = !seen.has(e.to);
      yield { t: 'relax', key: e.key, from: u, to: e.to, g: depth.get(u) + 1, improved: fresh };
      if (fresh) {
        seen.add(e.to);
        depth.set(e.to, depth.get(u) + 1);
        prev.set(e.to, { ...e, fromNode: u });
        queue.push(e.to);
        yield { t: 'push', node: e.to, g: depth.get(e.to), f: depth.get(e.to), frontier: snap(), size: queue.length };
      }
    }
  }
  yield { t: 'fail' };
}

export function search(kind, g, start, goal, banned) {
  return kind === 'bfs' ? bfs(g, start, goal) : bestFirst(g, start, goal, kind, banned);
}

/* Run a search to the end. Returns the path (or null) and the work done. */
export function solve(kind, g, start, goal, banned) {
  const stats = { expanded: 0, relaxed: 0, pushes: 0 };
  for (const ev of search(kind, g, start, goal, banned)) {
    if (ev.t === 'pop') stats.expanded++;
    else if (ev.t === 'relax') stats.relaxed++;
    else if (ev.t === 'push') stats.pushes++;
    else if (ev.t === 'found') return { path: ev.path, stats };
  }
  return { path: null, stats };
}

/* Yen's k shortest loop-free paths (alternatives) on top of Dijkstra. */
export function yen(g, start, goal, k = 3) {
  const first = solve('dijkstra', g, start, goal).path;
  if (!first) return [];
  const found = [first], cands = [];
  const seen = new Set([first.nodes.join('>')]);
  for (let i = 1; i < k; i++) {
    const last = found[found.length - 1];
    for (let j = 0; j < last.nodes.length - 1; j++) {
      const spur = last.nodes[j], root = last.nodes.slice(0, j + 1);
      const edges = new Set(), nodes = new Set(root.slice(0, -1));
      for (const p of found) if (p.nodes.slice(0, j + 1).join('>') === root.join('>') && p.legs[j]) edges.add(p.legs[j].key);
      const sp = solve('dijkstra', g, spur, goal, { edges, nodes }).path;
      if (!sp) continue;
      const legs = [...last.legs.slice(0, j), ...sp.legs];
      const ids = [...root.slice(0, -1), ...sp.nodes].join('>');
      if (seen.has(ids)) continue;
      seen.add(ids);
      const totals = { hours: 0, distanceKm: 0, costInr: 0 };
      legs.forEach((l) => { totals.hours += l.hours; totals.distanceKm += l.distanceKm; totals.costInr += l.costInr; });
      cands.push({ nodes: [...root.slice(0, -1), ...sp.nodes], legs, totals, cost: totals[g.metric] });
    }
    if (!cands.length) break;
    cands.sort((a, b) => a.cost - b.cost);
    found.push(cands.shift());
  }
  return found;
}

/* Fastest hours from one town to every other (for the reachable-area view). */
export function reach(g, start) {
  const dist = new Map([[start, 0]]);
  for (const ev of bestFirst(g, start, null, 'dijkstra')) if (ev.t === 'pop') dist.set(ev.node, ev.g);
  return dist;
}
