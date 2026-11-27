/* Route Lab: pick two towns, watch the search expand step by step, then a traveller drives the route.
   Close roads or add traffic at any time: the traveller re-plans from the next town. */
import { $, esc, post, toast, busy, cypherBlock, haversine, fmtMetric, MODE_ICON, num } from './util.js';
import { buildGraph, search, solve, yen, routeKey } from './algorithms.js';

const PRESETS = {
  normal: () => ({ closed: [], traffic: [] }),
  monsoon: (rs) => ({ closed: rs.filter((r) => r.mode === 'road' && ['Munnar', 'Kodaikanal', 'Ooty', 'Wayanad', 'Coorg', 'Thekkady', 'Yercaud'].some((t) => r.from === t || r.to === t)).map(routeKey), traffic: [] }),
  rail: (rs) => ({ closed: rs.filter((r) => r.mode === 'rail').map(routeKey), traffic: [] }),
  flights: (rs) => ({ closed: rs.filter((r) => r.mode === 'flight').map(routeKey), traffic: [] }),
  festival: (rs) => ({ closed: [], traffic: rs.filter((r) => r.mode === 'road' && ['Chennai', 'Madurai', 'Bengaluru'].some((t) => r.from === t || r.to === t)).map((r) => [routeKey(r), 2]) }),
  cyclone: (rs) => ({ closed: rs.filter((r) => r.mode === 'road' && ['Rameswaram', 'Mahabalipuram', 'Puducherry', 'Kanyakumari'].some((t) => r.from === t || r.to === t)).map(routeKey), traffic: [] }),
};
const TOOL_HINT = {
  route: 'click a destination to set the start, then the goal',
  close: 'click a route to close or reopen it',
  traffic: 'click a route to add traffic (×2, ×3, clear)',
  add: 'click two destinations to build a new route',
  erase: 'click a route to clear closures, traffic or a new route',
};

export class RouteLab {
  constructor(scene, store, hooks = {}) {
    this.scene = scene; this.store = store; this.hooks = hooks;
    this.start = null; this.goal = null; this.tool = 'route';
    this.closed = new Set(); this.traffic = new Map(); this.routes = []; this.added = [];
    this.timer = null; this.gen = null; this.path = null; this.addFirst = null;
    this.stats = { expanded: 0, relaxed: 0, frontier: 0 };
    this.journey = { hours: 0, km: 0, cost: 0, reroutes: 0, total: 0, done: 0 };
    this.bind();
  }

  get modes() { return [...document.querySelectorAll('#labModes .tog.on')].map((b) => b.dataset.mode); }
  get metric() { return $('labMetric').value; }
  get algo() { return $('labAlgo').value; }
  graph() { return buildGraph(this.store.network.destinations, this.routes, { modes: this.modes, closed: this.closed, traffic: this.traffic, metric: this.metric }); }

  bind() {
    $('labRun').onclick = () => this.run();
    $('labStep').onclick = () => this.step();
    $('labInstant').onclick = () => this.instant();
    $('labReset').onclick = () => { this.stopTravel(); this.resetSearch(); this.setEnds(null, null); };
    $('labSpeed').oninput = () => { $('labSpeedOut').textContent = `${$('labSpeed').value} steps/s`; if (this.timer) { clearInterval(this.timer); this.timer = setInterval(() => this.tick(), 1000 / +$('labSpeed').value); } };
    $('travelSpeed').oninput = () => { $('travelOut').textContent = `${+$('travelSpeed').value / 2}×`; };
    $('travelOut').textContent = `${+$('travelSpeed').value / 2}×`;
    document.querySelectorAll('#labModes .tog').forEach((b) => b.onclick = () => { b.classList.toggle('on'); this.envChanged(); });
    $('labMetric').onchange = () => { $('pqKey').textContent = this.pqLabel(); this.envChanged(); };
    $('labAlgo').onchange = () => { $('pqKey').textContent = this.pqLabel(); };
    document.querySelectorAll('#labTools .tool').forEach((b) => b.onclick = () => this.setTool(b.dataset.tool));
    $('labPreset').onchange = () => this.applyPreset($('labPreset').value);
    $('labVerify').onclick = () => busy($('labVerify'), 'Verifying…', () => this.verify());
    $('labSave').onclick = () => busy($('labSave'), 'Saving…', () => this.save());
    $('labRestore').onclick = () => busy($('labRestore'), 'Restoring…', () => this.restore());
    $('labCompare').onclick = () => this.compare();
    $('labAlt').onclick = () => this.alternatives();
  }

  pqLabel() { return { dijkstra: 'g (cost so far)', astar: 'f = g + h', greedy: 'h (estimate)', bfs: 'legs' }[this.algo]; }

  // ------------------------------------------------------------ network & page
  onNetwork(net) {
    this.routes = net.routes.map((r) => ({ ...r }));
    this.closed = new Set(this.routes.filter((r) => r.closed).map(routeKey));
    this.traffic = new Map(this.routes.filter((r) => (r.traffic || 1) > 1).map((r) => [routeKey(r), r.traffic]));
    this.added = [];
    this.stopTravel();
    this.resetSearch();
    if (this.start && !net.destinations.find((d) => d.name === this.start)) this.setEnds(null, null);
    this.summary();
  }

  enter() { this.repaint(); }
  leave() { if (this.timer) { clearInterval(this.timer); this.timer = null; } this.stopTravel(); }

  repaint() {
    const s = this.scene;
    s.resetNodes(); s.clearOverlay();
    s.syncRoutes(this.routes.map((r) => ({ ...r, closed: this.closed.has(routeKey(r)), traffic: this.traffic.get(routeKey(r)) || 1 })));
    this.setEnds(this.start, this.goal);
    if (this.path) { s.drawPath(this.path.legs); this.path.nodes.forEach((n) => { if (n !== this.start && n !== this.goal) s.setNodeState(n, 'path'); }); }
  }

  log(text, cls = '') {
    const box = $('labLog');
    const div = document.createElement('div');
    div.className = cls;
    div.textContent = text;
    box.appendChild(div);
    while (box.children.length > 7) box.removeChild(box.firstChild);
  }

  badge(id, text, cls) { const b = $(id); b.textContent = text; b.className = 'badge ' + (cls || ''); }

  // ------------------------------------------------------------ picking
  setTool(tool) {
    this.tool = tool;
    this.addFirst = null;
    document.querySelectorAll('#labTools .tool').forEach((b) => b.classList.toggle('on', b.dataset.tool === tool));
    $('addOpts').hidden = tool !== 'add';
    $('toolHint').textContent = TOOL_HINT[tool];
  }

  setEnds(start, goal) {
    const s = this.scene;
    [this.start, this.goal].forEach((n) => { if (n) { s.setMarker(n, null); s.setNodeState(n, 'idle'); } });
    this.start = start; this.goal = goal;
    if (start) { s.setMarker(start, 'start'); s.setNodeState(start, 'start'); }
    if (goal) { s.setMarker(goal, 'goal'); s.setNodeState(goal, 'goal'); }
    $('labStart').textContent = start || '—';
    $('labGoal').textContent = goal || '—';
    $('labPick').textContent = !start ? 'click the start town' : !goal ? 'now click the goal' : 'ready';
  }

  pickNode(name) {
    if (this.tool === 'add') return this.addRoutePick(name);
    if (this.tool !== 'route') { this.scene.flyTo(name); return; }
    this.stopTravel();
    if (!this.start || (this.start && this.goal)) { this.resetSearch(); this.setEnds(name, null); this.log(`Start: ${name}`); return; }
    if (name === this.start) return;
    this.setEnds(this.start, name);
    this.log(`Goal: ${name}`);
    this.run();
  }

  pickRoute(key, r) {
    const wr = this.routes.find((x) => routeKey(x) === key);
    if (!wr) return;
    if (this.tool === 'close') {
      if (this.closed.has(key)) { this.closed.delete(key); this.log(`Reopened ${r.from} – ${r.to} (${r.mode})`, 'ok'); }
      else { this.closed.add(key); this.log(`Closed ${r.from} – ${r.to} (${r.mode})`, 'bad'); }
    } else if (this.tool === 'traffic') {
      const f = this.traffic.get(key) || 1;
      const nf = f >= 3 ? 1 : f + 1;
      if (nf === 1) this.traffic.delete(key); else this.traffic.set(key, nf);
      this.log(nf === 1 ? `Traffic cleared on ${r.from} – ${r.to}` : `Traffic ×${nf} on ${r.from} – ${r.to}`, 'warn');
    } else if (this.tool === 'erase') {
      if (wr.added && !wr.saved) {
        this.routes = this.routes.filter((x) => x !== wr);
        this.added = this.added.filter((x) => x !== wr);
        this.scene.syncRoutes(this.routes.map((x) => ({ ...x, closed: this.closed.has(routeKey(x)), traffic: this.traffic.get(routeKey(x)) || 1 })));
        this.log(`Removed new route ${r.from} – ${r.to}`);
      } else { this.closed.delete(key); this.traffic.delete(key); this.log(`Cleared ${r.from} – ${r.to}`); }
    } else { toast(`${r.from} – ${r.to}: ${r.mode}, ${r.distanceKm} km, ${r.hours} h. Choose a tool to change it.`); return; }
    this.scene.updateRouteData(key, { closed: this.closed.has(key), traffic: this.traffic.get(key) || 1 });
    this.envChanged(key);
  }

  addRoutePick(name) {
    if (!this.addFirst) { this.addFirst = name; this.scene.ripple(name, 0xe2e8f0); $('toolHint').textContent = `now click the second town (from ${name})`; return; }
    if (name === this.addFirst) return;
    const mode = $('addMode').value;
    const A = this.store.network.destinations.find((d) => d.name === this.addFirst), B = this.store.network.destinations.find((d) => d.name === name);
    const crow = haversine(A, B);
    const km = Math.round(crow * (mode === 'road' ? 1.25 : mode === 'rail' ? 1.15 : 1));
    const hours = +(mode === 'road' ? km / 50 : mode === 'rail' ? km / 60 : km / 450 + 1).toFixed(1);
    const cost = Math.round(mode === 'road' ? km * 11 : mode === 'rail' ? km * 1.6 : 3000 + km * 4);
    const r = { from: A.name, to: B.name, mode, distanceKm: km, hours, costInr: cost, closed: false, traffic: 1, added: true };
    if (this.routes.some((x) => routeKey(x) === routeKey(r) || (x.from === r.to && x.to === r.from && x.mode === mode))) { toast('That route already exists.', 'error'); this.addFirst = null; return; }
    this.routes.push(r); this.added.push(r);
    if (this.scene.routes.has(routeKey(r))) this.scene.setRouteState(routeKey(r), 'show'); else this.scene.addRoute(r);
    this.log(`New ${mode} route ${A.name} – ${B.name}: ${km} km, ${hours} h, ₹${cost}`, 'ok');
    this.addFirst = null;
    $('toolHint').textContent = TOOL_HINT.add;
    this.envChanged(routeKey(r));
  }

  applyPreset(name) {
    const p = PRESETS[name](this.routes.filter((r) => !r.added));
    this.closed = new Set(p.closed);
    this.traffic = new Map(p.traffic);
    this.routes.forEach((r) => this.scene.updateRouteData(routeKey(r), { closed: this.closed.has(routeKey(r)), traffic: this.traffic.get(routeKey(r)) || 1 }));
    this.log(`Environment: ${$('labPreset').selectedOptions[0].textContent}`, 'warn');
    this.envChanged();
  }

  summary() {
    const added = this.routes.filter((r) => r.added).length;
    const parts = [];
    if (this.closed.size) parts.push(`⛔ ${this.closed.size} closed`);
    if (this.traffic.size) parts.push(`🚦 ${this.traffic.size} with traffic`);
    if (added) parts.push(`🆕 ${added} new${this.added.length ? ` (${this.added.length} unsaved)` : ''}`);
    $('envSummary').textContent = parts.length ? parts.join(' · ') : 'No closures or traffic.';
  }

  envChanged(key) {
    this.summary();
    if (this.scene.traveller) this.replan(key);
    else if (this.path && this.start && this.goal) { $('labMsg').textContent = 'The network changed. Run the search again to see the new best route.'; }
  }

  // ------------------------------------------------------------ search animation
  resetSearch() {
    if (this.timer) { clearInterval(this.timer); this.timer = null; }
    this.gen = null; this.path = null;
    const s = this.scene;
    s.nodes.forEach((n, name) => { if (name !== this.start && name !== this.goal) s.setNodeState(name, 'idle'); });
    s.clearOverlay();
    s.syncRoutes(this.routes.map((r) => ({ ...r, closed: this.closed.has(routeKey(r)), traffic: this.traffic.get(routeKey(r)) || 1 })));
    this.stats = { expanded: 0, relaxed: 0, frontier: 0 };
    this.tiles(null);
    $('pqList').innerHTML = '';
    this.badge('labBadge', 'IDLE');
    $('labMsg').textContent = this.start && this.goal ? 'Ready.' : 'Pick a start and a destination on the map.';
    $('pqKey').textContent = this.pqLabel();
  }

  begin() {
    if (!this.start || !this.goal) { toast('Click a start and a goal destination on the map first.', 'error'); return false; }
    this.stopTravel();
    this.resetSearch();
    this.g = this.graph();
    this.gen = search(this.algo, this.g, this.start, this.goal);
    this.badge('labBadge', 'SEARCHING', 'searching');
    this.log(`${$('labAlgo').selectedOptions[0].textContent}: ${this.start} → ${this.goal}`);
    return true;
  }

  run() {
    if (!this.begin()) return;
    this.timer = setInterval(() => this.tick(), 1000 / +$('labSpeed').value);
  }

  step() {
    if (!this.gen && !this.begin()) return;
    if (this.timer) { clearInterval(this.timer); this.timer = null; }
    // advance to the next visible change (skip pure frontier bookkeeping)
    let ev;
    do { ev = this.tick(); } while (ev && ev.t === 'push');
  }

  instant() {
    if (!this.gen && !this.begin()) return;
    if (this.timer) { clearInterval(this.timer); this.timer = null; }
    let ev;
    do { ev = this.tick(true); } while (ev && ev.t !== 'found' && ev.t !== 'fail');
  }

  tick(quiet = false) {
    if (!this.gen) return null;
    const { value, done } = this.gen.next();
    if (done || !value) { if (this.timer) clearInterval(this.timer); this.timer = null; this.gen = null; return null; }
    this.apply(value, quiet);
    return value;
  }

  apply(ev, quiet) {
    const s = this.scene, m = this.algo === 'bfs' ? null : this.metric;
    const val = (v) => (m ? fmtMetric(m, v) : `${v} legs`);
    if (ev.frontier) { this.stats.frontier = ev.size; this.renderPQ(ev.frontier); }
    if (ev.t === 'push') {
      if (ev.node !== this.start && ev.node !== this.goal) s.setNodeState(ev.node, 'frontier');
    } else if (ev.t === 'pop') {
      this.stats.expanded++;
      s.ripple(ev.node);
      if (ev.node !== this.start && ev.node !== this.goal) {
        s.setNodeState(ev.node, 'current');
        setTimeout(() => { const n = s.nodes.get(ev.node); if (n && n.state === 'current') s.setNodeState(ev.node, 'visited'); }, 260);
      }
      $('labMsg').textContent = `Expanding ${ev.node} (${val(ev.g)} from ${this.start}).`;
      if (!quiet) this.log(`pop  ${ev.node}  g=${val(ev.g)}`);
    } else if (ev.t === 'relax') {
      this.stats.relaxed++;
      s.flashRoute(ev.key);
      if (ev.improved) s.setRouteState(ev.key, 'explored');
      if (!quiet && ev.improved) this.log(`relax ${ev.from} → ${ev.to}: ${val(ev.g)} (better)`, 'ok');
    } else if (ev.t === 'found') {
      this.path = ev.path;
      this.badge('labBadge', 'PATH FOUND', 'found');
      s.drawPath(ev.path.legs);
      ev.path.nodes.forEach((n) => { if (n !== this.start && n !== this.goal) s.setNodeState(n, 'path'); });
      const t = ev.path.totals;
      $('labMsg').innerHTML = `Route: ${ev.path.nodes.map(esc).join(' → ')}<br><span class="muted small">${t.hours.toFixed(1)} h · ${Math.round(t.distanceKm)} km · ₹${Math.round(t.costInr).toLocaleString('en-IN')} · ${ev.path.legs.length} legs</span>`;
      this.log(`Found: ${ev.path.nodes.join(' → ')}`, 'ok');
      this.tiles(ev.path);
      if ($('labAutoTravel').checked) setTimeout(() => this.travel(ev.path), 400);
      return;
    } else if (ev.t === 'fail') {
      this.badge('labBadge', 'NO PATH', 'fail');
      $('labMsg').textContent = 'No route with the current travel modes and closures.';
      this.log('No route found', 'bad');
    }
    this.tiles(null);
  }

  tiles(path) {
    $('tExpanded').textContent = this.stats.expanded;
    $('tFrontier').textContent = this.stats.frontier;
    $('tRelaxed').textContent = this.stats.relaxed;
    $('tCost').textContent = path ? (this.algo === 'bfs' ? `${path.legs.length} legs` : fmtMetric(this.metric, path.cost)) : '—';
  }

  renderPQ(front) {
    const m = this.algo === 'bfs' ? null : this.metric;
    $('pqList').innerHTML = front.map((x) => `<div class="pq-item"><span>${esc(x.node)}</span><span>${m ? (m === 'costInr' ? '₹' + Math.round(x.f) : x.f.toFixed(1)) : x.f}</span></div>`).join('') || '<span class="muted small">empty</span>';
  }

  // ------------------------------------------------------------ journey
  travel(path) {
    if (!path || !path.legs.length) return;
    this.journey = { hours: 0, km: 0, cost: 0, reroutes: 0, total: path.totals.hours, done: 0 };
    this.scene.startTraveller(path.legs, { speed: () => +$('travelSpeed').value / 2 });
    this.badge('tripBadge', 'DRIVING', 'driving');
    this.journeyTiles();
  }

  stopTravel() {
    this.scene.stopTraveller();
    this.badge('tripBadge', 'PARKED');
    $('tripBar').style.width = '0';
  }

  legStart(leg) { $('jLeg').innerHTML = `${esc(leg.from)} → ${esc(leg.to)} <span class="mode ${leg.mode}">${MODE_ICON[leg.mode]} ${leg.mode}</span>`; }

  travelProgress(i, t) {
    const tv = this.scene.traveller;
    if (!tv) return;
    const total = this.journey.done + tv.legs.slice(i).reduce((a, l) => a + l.hours, 0);
    const doneNow = this.journey.done + t * tv.legs[i].hours;
    $('tripBar').style.width = `${Math.min(100, (doneNow / total) * 100)}%`;
  }

  legEnd(leg) {
    this.journey.hours += leg.hours; this.journey.km += leg.distanceKm; this.journey.cost += leg.costInr; this.journey.done += leg.hours;
    this.journeyTiles();
    this.scene.ripple(leg.to, 0x4ade80);
    if (leg.back) this.log(`Back at ${leg.to}`, 'warn');
  }

  arrive(name) {
    if (name !== this.goal) {
      this.badge('tripBadge', 'STUCK', 'stuck');
      $('jLeg').textContent = `Stopped at ${name}: ${this.goal} cannot be reached`;
      this.log(`Stopped at ${name}: no open route to ${this.goal}`, 'bad');
      toast(`Stopped at ${name}: ${this.goal} cannot be reached with the current closures.`, 'error');
      return;
    }
    this.badge('tripBadge', 'ARRIVED', 'arrived');
    $('tripBar').style.width = '100%';
    $('jLeg').textContent = `Arrived at ${name}`;
    this.log(`Arrived at ${name} after ${this.journey.hours.toFixed(1)} h, ${this.journey.reroutes} re-route(s)`, 'ok');
    toast(`Arrived at ${name}: ${this.journey.hours.toFixed(1)} h, ${Math.round(this.journey.km)} km, ₹${Math.round(this.journey.cost).toLocaleString('en-IN')}`);
  }

  journeyTiles() {
    $('jHours').textContent = this.journey.hours.toFixed(1);
    $('jKm').textContent = Math.round(this.journey.km);
    $('jCost').textContent = Math.round(this.journey.cost).toLocaleString('en-IN');
    $('jReroutes').textContent = this.journey.reroutes;
  }

  replan(changedKey) {
    const tv = this.scene.traveller;
    if (!tv) return;
    const g = this.graph();
    const cur = tv.legs[tv.i];
    const remainingKeys = tv.legs.slice(tv.i + 1).map((l) => l.key);
    const curBlocked = !cur.back && this.closed.has(cur.key);
    if (changedKey && !curBlocked && !remainingKeys.includes(changedKey) && !this.added.some((r) => routeKey(r) === changedKey)) return;
    const kind = this.algo === 'bfs' ? 'bfs' : this.algo === 'greedy' ? 'greedy' : 'astar';
    let from = cur.to;
    if (curBlocked) { this.scene.turnBack(); from = cur.from; this.log(`Road ahead closed! Turning back to ${from}`, 'bad'); }
    const res = solve(kind, g, from, this.goal);
    const oldKeys = remainingKeys.join(',');
    if (!res.path) {
      this.scene.replaceRemaining([]);
      this.badge('tripBadge', 'STUCK', 'stuck');
      this.log(`No route from ${from} to ${this.goal}: stopping at ${from}`, 'bad');
      return;
    }
    if (res.path.legs.map((l) => l.key).join(',') === oldKeys && !curBlocked) { this.log('Checked: current route is still the best', ''); return; }
    this.scene.replaceRemaining(res.path.legs);
    this.journey.reroutes++;
    this.journeyTiles();
    this.badge('tripBadge', 'RE-ROUTING', 'reroute');
    setTimeout(() => { if (this.scene.traveller) this.badge('tripBadge', 'DRIVING', 'driving'); }, 1800);
    this.log(`Re-routing from ${from}: ${res.path.nodes.join(' → ')}`, 'warn');
    this.scene.clearOverlay();
    this.scene.drawPath(this.scene.traveller.legs.slice(this.scene.traveller.i));
    const rem = this.scene.traveller.legs.slice(this.scene.traveller.i);
    this.path = { legs: rem, nodes: [rem[0].from, ...rem.map((l) => l.to)], totals: res.path.totals, cost: res.path.cost };
  }

  // ------------------------------------------------------------ compare, alternatives
  compare() {
    if (!this.start || !this.goal) { toast('Pick a start and a goal first.', 'error'); return; }
    const g = this.graph();
    const rows = ['bfs', 'dijkstra', 'astar', 'greedy'].map((k) => ({ k, ...solve(k, g, this.start, this.goal) }));
    if (!rows[1].path) { $('compareOut').innerHTML = '<p class="bad-text small">No route with the current settings.</p>'; return; }
    const best = rows[1].path.cost, maxExp = Math.max(...rows.map((r) => r.stats.expanded));
    const names = { bfs: 'BFS', dijkstra: 'Dijkstra', astar: 'A*', greedy: 'Greedy' };
    $('compareOut').innerHTML = `<p class="small muted" style="margin:.5rem 0 .3rem">${esc(this.start)} → ${esc(this.goal)}, optimising ${this.metric === 'hours' ? 'time' : this.metric === 'distanceKm' ? 'distance' : 'cost'}</p>` + rows.map((r) => `
      <div class="rank-item" style="cursor:default"><span class="n">${names[r.k]}</span>
        <div class="t"><b>${r.path ? fmtMetric(this.metric, r.path.cost) : 'no path'} ${r.path && Math.abs(r.path.cost - best) < 1e-6 ? '<span class="tag good">optimal</span>' : r.path ? `<span class="tag">+${fmtMetric(this.metric, r.path.cost - best)}</span>` : ''}</b>
          <div class="bar" style="width:${(r.stats.expanded / maxExp) * 100}%"></div><div class="sub">${r.stats.expanded} towns expanded · ${r.stats.relaxed} edges relaxed · ${r.path ? r.path.legs.length : 0} legs</div></div>
        <span class="v"></span></div>`).join('');
  }

  alternatives() {
    if (!this.start || !this.goal) { toast('Pick a start and a goal first.', 'error'); return; }
    const alts = yen(this.graph(), this.start, this.goal, 3);
    this.scene.clearOverlay();
    const colors = [0x4ade80, 0xfbbf24, 0xe879f9];
    alts.forEach((p, i) => this.scene.drawPath(p.legs, { color: colors[i], alt: i > 0 }));
    $('compareOut').innerHTML = alts.length ? alts.map((p, i) => `
      <div class="rank-item" data-i="${i}"><span class="n" style="color:#${colors[i].toString(16)}">${i ? '#' + (i + 1) : '★'}</span>
        <div class="t"><b>${p.nodes.map(esc).join(' → ')}</b><div class="sub">${p.totals.hours.toFixed(1)} h · ${Math.round(p.totals.distanceKm)} km · ₹${Math.round(p.totals.costInr).toLocaleString('en-IN')} ${[...new Set(p.legs.map((l) => l.mode))].map((m) => `<span class="mode ${m}">${m}</span>`).join('')}</div></div>
        <span class="v">drive ▶</span></div>`).join('') : '<p class="small bad-text">No route.</p>';
    $('compareOut').querySelectorAll('.rank-item').forEach((el) => el.onclick = () => { const p = alts[+el.dataset.i]; this.path = p; this.travel(p); });
    this.log(`Yen's algorithm: ${alts.length} loop-free alternatives`, 'ok');
  }

  // ------------------------------------------------------------ Neo4j
  async verify() {
    if (!this.start || !this.goal) throw new Error('Pick a start and a goal first.');
    const kind = this.algo === 'bfs' ? 'bfs' : 'dijkstra';
    const g = this.graph();
    const mine = solve(kind, g, this.start, this.goal).path;
    const dbClosed = [...this.closed].filter((k) => !this.added.some((r) => routeKey(r) === k));
    const d = await post('/api/verify', { algorithm: kind, from: this.start, to: this.goal, metric: this.metric, modes: this.modes,
      closed: dbClosed, traffic: [...this.traffic].map(([key, factor]) => ({ key, factor })) });
    const top = d.rows[0];
    let verdict;
    if (!top && !mine) verdict = '<span class="ok-text">✓ Both agree: no route.</span>';
    else if (!top) verdict = '<span class="bad-text">Neo4j found no route within 6 legs.</span>';
    else if (kind === 'bfs') verdict = top[1] === mine.legs.length ? `<span class="ok-text">✓ Same number of legs (${top[1]}).</span>` : `<span class="bad-text">✗ Legs differ: Neo4j ${top[1]}, JavaScript ${mine.legs.length}.</span>`;
    else verdict = Math.abs(top[2] - mine.cost) < 0.06 ? `<span class="ok-text">✓ Same optimal ${fmtMetric(this.metric, mine.cost)} in Neo4j and in the browser.</span>` : `<span class="bad-text">✗ Neo4j ${fmtMetric(this.metric, top[2])} vs browser ${fmtMetric(this.metric, mine.cost)}.</span>`;
    const unsaved = this.added.length ? `<p class="small" style="color:var(--warn)">${this.added.length} new route(s) are not in Neo4j yet: save the scenario to include them.</p>` : '';
    $('verifyOut').innerHTML = `<p class="small">${verdict}</p>${unsaved}<p class="small muted">Neo4j: ${top ? esc(top[0].join(' → ')) : '—'} · ${num(d.timing.serverMs, 1)} ms</p>
      <details class="drawer"><summary>Cypher that was run</summary>${cypherBlock(d.cypher)}<p class="small muted">closed = ${esc(JSON.stringify(d.params.closed))}</p></details>`;
  }

  async save() {
    const keyObj = (k) => { const [from, to, mode] = k.split('|'); return { from, to, mode }; };
    const unsavedKeys = new Set(this.added.map(routeKey));
    const body = {
      closed: [...this.closed].filter((k) => !unsavedKeys.has(k)).map(keyObj),
      traffic: [...this.traffic].filter(([k]) => !unsavedKeys.has(k)).map(([k, f]) => ({ ...keyObj(k), factor: f })),
      added: this.added.map((r) => ({ from: r.from, to: r.to, mode: r.mode, distanceKm: r.distanceKm, hours: r.hours, costInr: r.costInr })),
    };
    const d = await post('/api/scenario/save', body);
    await this.hooks.reloadNetwork();
    this.repaint();
    $('verifyOut').innerHTML = `<p class="small ok-text">Saved to Neo4j. The Cypher console and the Python planner now see these closures and routes.</p>
      <details class="drawer"><summary>Cypher that was run (${d.steps.length} statements)</summary>${d.steps.map((s) => `<p class="small">${esc(s.title)}: ${s.propertiesSet} properties, ${s.relationshipsCreated} new</p>${cypherBlock(s.cypher)}`).join('')}</details>`;
    toast('Scenario saved to Neo4j.');
  }

  async restore() {
    const d = await post('/api/scenario/restore');
    $('labPreset').value = 'normal';
    await this.hooks.reloadNetwork();
    this.repaint();
    $('verifyOut').innerHTML = `<p class="small ok-text">Network restored: ${d.deleted} added route(s) deleted, closures and traffic removed.</p><details class="drawer"><summary>Cypher</summary>${cypherBlock(d.cypher)}</details>`;
    toast('Network restored to the sample data.');
  }

  nodeTip(name) {
    if (name === this.start) return '<br><b style="color:#4ade80">start</b>';
    if (name === this.goal) return '<br><b style="color:#f472b6">goal</b>';
    return '';
  }
}
