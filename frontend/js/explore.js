/* Explore: toggle interests, slide the month, pick a budget: towers grow and glow by match score (live Cypher).
   Reachable mode: slide the hours and watch the reachable area spread from a town. */
import * as THREE from 'three';
import { $, esc, post, get, toast, debounce, cypherBlock, MONTHS, CAT_ICON, flip } from './util.js';
import { buildGraph, reach, routeKey } from './algorithms.js';

const C0 = new THREE.Color(0x334155), C1 = new THREE.Color(0xf59e0b), C2 = new THREE.Color(0xfde68a);
const heat = (t) => (t < 0.6 ? C0.clone().lerp(C1, t / 0.6) : C1.clone().lerp(C2, (t - 0.6) / 0.4));
const R0 = new THREE.Color(0x0ea5e9), R1 = new THREE.Color(0xa5f3fc);

export class Explore {
  constructor(scene, store) {
    this.scene = scene; this.store = store;
    this.mode = 'match'; this.active = false;
    this.cats = new Set(['Nature', 'Wildlife']);
    this.budget = 'mid';
    $('exMonth').value = new Date().getMonth() + 1;
    this.refreshSoon = debounce(() => this.refresh(), 220);
    this.bind();
  }

  bind() {
    const cats = (this.store.meta && this.store.meta.categories) || Object.keys(CAT_ICON);
    $('exCats').innerHTML = cats.map((c) => `<button class="chip${this.cats.has(c) ? ' on' : ''}" data-c="${esc(c)}">${CAT_ICON[c] || ''} ${esc(c)}</button>`).join('');
    $('exCats').querySelectorAll('.chip').forEach((b) => b.onclick = () => {
      b.classList.toggle('on');
      if (b.classList.contains('on')) this.cats.add(b.dataset.c); else this.cats.delete(b.dataset.c);
      this.refreshSoon();
    });
    const month = () => { $('exMonthOut').textContent = MONTHS[+$('exMonth').value - 1]; };
    month();
    $('exMonth').oninput = () => { month(); this.refreshSoon(); };
    $('exBudget').querySelectorAll('button').forEach((b) => b.onclick = () => {
      $('exBudget').querySelectorAll('button').forEach((x) => x.classList.toggle('on', x === b));
      this.budget = b.dataset.b; this.refreshSoon();
    });
    $('exMode').querySelectorAll('button').forEach((b) => b.onclick = () => {
      $('exMode').querySelectorAll('button').forEach((x) => x.classList.toggle('on', x === b));
      this.mode = b.dataset.mode;
      $('exMatchCard').hidden = this.mode !== 'match';
      $('exReachCard').hidden = this.mode !== 'reach';
      this.paint();
    });
    $('exFrom').onchange = () => this.reachView();
    $('exHours').oninput = () => { $('exHoursOut').textContent = `${$('exHours').value} h`; this.reachView(); };
    document.querySelectorAll('#exModes .tog').forEach((b) => b.onclick = () => { b.classList.toggle('on'); this.reachView(); });
  }

  onNetwork(net) {
    const sel = $('exFrom'), keep = sel.value || 'Chennai';
    sel.innerHTML = net.destinations.map((d) => `<option>${esc(d.name)}</option>`).join('');
    if (net.destinations.some((d) => d.name === keep)) sel.value = keep;
    if (this.active) this.paint();
  }

  enter() { this.active = true; this.paint(); }
  leave() { this.active = false; this.scene.clearBeams(); }

  paint() {
    const s = this.scene;
    s.resetNodes(); s.clearOverlay(); s.syncRoutes(this.store.network.routes);
    document.querySelector('#stage-explore .hint').innerHTML = this.mode === 'match'
      ? 'Tower height and colour = match score · <b>click a destination for details</b>'
      : 'Blue towers = reachable in time · <b>slide the hours and watch the area grow</b>';
    if (this.mode === 'match') this.refresh(); else this.reachView();
  }

  legend(html) { $('exLegend').innerHTML = html; }

  async refresh() {
    if (!this.store.network.destinations.length) return;
    let d;
    try { d = await post('/api/explore', { categories: [...this.cats], month: +$('exMonth').value, budget: this.budget }); } catch (e) { toast(e.message, 'error'); return; }
    if (this.mode !== 'match' || !this.active) return;
    const s = this.scene;
    s.routes.forEach((e, k) => s.setRouteState(k, 'dim'));
    d.rows.forEach((r) => {
      const t = Math.min(1, r.score / 10);
      s.setNodeLook(r.destination, { color: heat(t).getHex(), height: 0.35 + r.score * 0.9, glow: 0.2 + t * 0.9, sub: r.score.toFixed(1), dim: r.score < 2 });
    });
    const top = d.rows.slice(0, 10);
    s.setBeams(top.slice(0, 3).map((r) => ({ name: r.destination, strength: r.score / 10, color: 0xfbbf24 })));
    const max = Math.max(...top.map((r) => r.score), 1);
    flip($('exRank'), () => {
      $('exRank').innerHTML = top.map((r, i) => `<div class="rank-item" data-key="${esc(r.destination)}" data-d="${esc(r.destination)}">
        <span class="n">${i + 1}</span>
        <div class="t"><b>${esc(r.destination)}</b>
          <div class="sub">${r.matched.map((c) => `${CAT_ICON[c] || ''}${esc(c)}`).join(' · ') || 'no matching attractions'}</div>
          <div class="bar" style="width:${(r.score / max) * 100}%"></div>
          <div class="sub">${r.inSeason ? '<span class="tag good">in season</span>' : '<span class="tag">off season</span>'}<span class="tag">${r.hotels} hotel${r.hotels === 1 ? '' : 's'} in budget</span>${r.rating ? `<span class="tag">★ ${r.rating}</span>` : ''}</div></div>
        <span class="v">${r.score.toFixed(1)}</span></div>`).join('');
    });
    $('exRank').querySelectorAll('.rank-item').forEach((el) => el.onclick = () => this.pickNode(el.dataset.d));
    this.legend(`<span>score</span><span class="grad"></span><span>low → high · beams = top 3</span>`);
    $('exCypher').innerHTML = cypherBlock(d.cypher) + `<p class="small muted">params = ${esc(JSON.stringify(d.params))}</p><p class="small muted">score = interest match (0–6) + 2 in season + 1 hotel in budget (−2 if none) + rating bonus</p>`;
  }

  reachView() {
    if (this.mode !== 'reach' || !this.active || !this.store.network.destinations.length) return;
    const s = this.scene, net = this.store.network;
    const modes = [...document.querySelectorAll('#exModes .tog.on')].map((b) => b.dataset.mode);
    const closed = new Set(net.routes.filter((r) => r.closed).map(routeKey));
    const traffic = new Map(net.routes.filter((r) => (r.traffic || 1) > 1).map((r) => [routeKey(r), r.traffic]));
    const g = buildGraph(net.destinations, net.routes, { modes, closed, traffic, metric: 'hours' });
    const from = $('exFrom').value, max = +$('exHours').value;
    const dist = reach(g, from);
    s.clearBeams();
    net.destinations.forEach((d) => {
      const h = dist.get(d.name);
      if (d.name === from) { s.setNodeLook(d.name, { color: 0x4ade80, height: 3.2, glow: 1, sub: 'start', dim: false }); s.setMarker(d.name, 'home'); return; }
      s.setMarker(d.name, null);
      if (h !== undefined && h <= max) {
        const t = 1 - h / max;
        s.setNodeLook(d.name, { color: R0.clone().lerp(R1, t).getHex(), height: 0.8 + t * 3, glow: 0.5 + t * 0.6, sub: `${h.toFixed(1)} h`, dim: false });
      } else s.setNodeLook(d.name, { color: 0x1e293b, height: 0.3, glow: 0.05, sub: h === undefined ? 'unreachable' : `${h.toFixed(1)} h`, dim: true });
    });
    s.routes.forEach((e, k) => {
      const a = dist.get(e.r.from), b = dist.get(e.r.to);
      s.setRouteState(k, a !== undefined && b !== undefined && a <= max && b <= max && modes.includes(e.r.mode) && !e.r.closed ? 'explored' : 'dim');
    });
    const inside = [...dist].filter(([n, h]) => n !== from && h <= max).sort((a, b) => a[1] - b[1]);
    flip($('exReachList'), () => {
      $('exReachList').innerHTML = `<p class="small muted" style="margin:.2rem 0">${inside.length} of ${net.destinations.length - 1} destinations within ${max} h</p>` +
        inside.map(([n, h], i) => `<div class="rank-item" data-key="${esc(n)}" data-d="${esc(n)}"><span class="n">${i + 1}</span><div class="t"><b>${esc(n)}</b><div class="bar" style="width:${(1 - h / max) * 100}%;background:linear-gradient(90deg,#0ea5e9,#a5f3fc)"></div></div><span class="v">${h.toFixed(1)} h</span></div>`).join('');
    });
    $('exReachList').querySelectorAll('.rank-item').forEach((el) => el.onclick = () => this.pickNode(el.dataset.d));
    this.legend('<span style="color:#a5f3fc">● close</span><span style="color:#0ea5e9">● far</span><span class="muted">● out of reach</span><span>Dijkstra in the browser on the Neo4j route graph</span>');
  }

  async pickNode(name) {
    this.scene.flyTo(name);
    this.scene.ripple(name, 0xfbbf24);
    let d;
    try { d = await get('/api/destination/' + encodeURIComponent(name)); } catch (e) { toast(e.message, 'error'); return; }
    const stars = (r) => '★'.repeat(Math.round(r)) + '☆'.repeat(5 - Math.round(r));
    $('exDetail').innerHTML = `<div class="card-title">${esc(d.name.toUpperCase())} <span class="right muted">${esc(d.state)}</span></div>
      <p class="small muted" style="margin-top:0">${esc(d.description)}</p>
      <div class="chips">${MONTHS.map((m, i) => `<span class="chip${d.bestMonths.includes(i + 1) ? ' on' : ''}" style="cursor:default;padding:.1rem .45rem">${m.slice(0, 3)}</span>`).join('')}</div>
      <div class="rank">${d.attractions.map((a) => `<div class="rank-item" style="cursor:default"><span class="n">${CAT_ICON[a.categories[0]] || '📍'}</span>
        <div class="t"><b>${esc(a.name)}</b><div class="sub">${a.categories.map(esc).join(' · ')} · ${a.hours} h · ${a.fee ? '₹' + a.fee : 'free'} · ${a.visits} visits</div></div>
        <span class="v stars">${stars(a.rating)}</span></div>`).join('')}</div>
      <p class="small" style="margin:.6rem 0 .3rem"><b>Hotels</b></p>
      ${d.hotels.map((h) => `<div class="visit"><span>${esc(h.name)} ${'★'.repeat(h.stars)}</span><span class="muted">${esc(h.band)} · ₹${h.price.toLocaleString('en-IN')}</span></div>`).join('')}
      <details class="drawer"><summary>Cypher</summary>${cypherBlock(d.cypher)}</details>`;
  }

  nodeTip(name) {
    const el = this.scene.nodes.get(name);
    const sub = el && el.lbl.element.querySelector('small').textContent;
    return sub ? `<br><b>${this.mode === 'match' ? 'score' : 'travel time'}: ${esc(sub)}</b>` : '';
  }
}
