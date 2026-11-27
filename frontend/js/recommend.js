/* Recommend: choose a tourist, drag interest sliders, change the month: recommendations re-rank live
   (content-based Cypher with your weights + collaborative Cypher + rank fusion). Mark a visit and watch it update. */
import { $, esc, get, post, toast, debounce, cypherBlock, MONTHS, CAT_ICON, flip } from './util.js';
import { buildGraph, solve, routeKey } from './algorithms.js';
import { Graph2D } from './graph2d.js';

const STYLE_COLOR = { beach: '#38bdf8', heritage: '#f59e0b', spiritual: '#f472b6', nature: '#4ade80', wildlife: '#a3e635', mixed: '#a78bfa' };

export class Recommend {
  constructor(scene, store) {
    this.scene = scene; this.store = store;
    this.tid = 't01'; this.weights = {}; this.tourist = null; this.last = null; this.active = false;
    $('recMonth').value = new Date().getMonth() + 1;
    const month = () => { $('recMonthOut').textContent = MONTHS[+$('recMonth').value - 1]; };
    month();
    $('recMonth').oninput = () => { month(); this.soon(); };
    $('recResetW').onclick = () => { this.weightsFromProfile(); this.sliders(); this.soon(); };
    $('recUndo').onclick = () => this.undo();
    this.soon = debounce(() => this.recommend(), 260);
  }

  onLists(lists) {
    if (!lists) return;
    $('recPeople').innerHTML = lists.tourists.map((t) => {
      const ini = t.name.split(' ').map((w) => w[0]).join('').slice(0, 2);
      return `<div class="person${t.id === this.tid ? ' on' : ''}" data-id="${t.id}" title="${esc(t.name)} · ${esc(t.home)} · ${esc(t.style)}">
        <div class="av" style="background:${STYLE_COLOR[t.style] || '#8396b3'}">${esc(ini)}</div>${esc(t.name.split(' ')[0])}</div>`;
    }).join('');
    $('recPeople').querySelectorAll('.person').forEach((p) => p.onclick = () => {
      $('recPeople').querySelectorAll('.person').forEach((x) => x.classList.toggle('on', x === p));
      this.load(p.dataset.id);
    });
    if (this.active) this.load(this.tid);
  }

  enter() {
    this.active = true;
    this.scene.resetNodes(); this.scene.clearOverlay(); this.scene.syncRoutes(this.store.network.routes);
    if (this.store.lists) this.load(this.tid);
  }
  leave() { this.active = false; this.scene.clearBeams(); }

  weightsFromProfile() {
    this.weights = {};
    (this.store.meta.categories || []).forEach((c) => { this.weights[c] = 0; });
    this.tourist.interests.forEach((i) => { this.weights[i.cat] = i.weight; });
  }

  async load(tid) {
    this.tid = tid;
    try { this.tourist = await get('/api/tourist/' + tid); } catch (e) { toast(e.message, 'error'); return; }
    this.weightsFromProfile();
    this.sliders();
    this.profile();
    await this.recommend();
  }

  profile() {
    const t = this.tourist;
    $('recProfile').innerHTML = `<b style="color:var(--ink)">${esc(t.name)}</b>, ${t.age} · lives in <b style="color:var(--ink)">${esc(t.home)}</b> · ${esc(t.budget)} budget · ${esc(t.style)} traveller · ${t.visits.length} visits`;
    $('recVisits').innerHTML = t.visits.length ? t.visits.slice().reverse().map((v) => `<div class="visit"><span>${esc(v.name)} <span class="muted">${esc(v.destination)}</span>${v.demo ? ' <span class="tag good">demo</span>' : ''}</span><span class="stars">${'★'.repeat(v.rating)}</span></div>`).join('') : '<p class="muted">No visits yet.</p>';
  }

  sliders() {
    $('recSliders').innerHTML = Object.entries(this.weights).map(([c, w]) => `<div class="wrow${w ? '' : ' zero'}">
      <span>${CAT_ICON[c] || ''} ${esc(c)}</span><input type="range" min="0" max="3" step="1" value="${w}" data-c="${esc(c)}"><output>${w}</output></div>`).join('');
    $('recSliders').querySelectorAll('input').forEach((inp) => inp.oninput = () => {
      this.weights[inp.dataset.c] = +inp.value;
      inp.nextElementSibling.textContent = inp.value;
      inp.parentElement.classList.toggle('zero', +inp.value === 0);
      this.soon();
    });
  }

  async recommend() {
    if (!this.tourist) return;
    const t0 = performance.now();
    let d;
    try { d = await post('/api/recommend/live', { tourist: this.tid, weights: this.weights, month: +$('recMonth').value }); } catch (e) { toast(e.message, 'error'); return; }
    this.last = d;
    $('recTiming').textContent = `${Math.round(performance.now() - t0)} ms round trip`;
    this.renderDest(d);
    this.renderItems(d);
    if (this.active) this.paintMap(d);
  }

  renderDest(d) {
    const max = Math.max(...d.destinations.map((x) => x.score), 1);
    flip($('recDest'), () => {
      $('recDest').innerHTML = d.destinations.length ? d.destinations.map((x, i) => `<div class="rank-item" data-key="${esc(x.destination)}" data-d="${esc(x.destination)}">
        <span class="n">${i + 1}</span>
        <div class="t"><b>${esc(x.destination)}</b>
          <div class="sub">${x.because.map((c) => `${CAT_ICON[c] || ''}${esc(c)}`).join(' · ')}</div>
          <div class="bar" style="width:${Math.max(4, (x.score / max) * 100)}%"></div>
          <div class="sub">${x.inSeason ? '<span class="tag good">in season</span>' : '<span class="tag">off season</span>'}<span class="tag">${x.travelHours ?? '—'} h from ${esc(this.tourist.home)}</span></div></div>
        <span class="v">${x.score.toFixed(1)}</span></div>`).join('') : '<p class="muted small">Raise at least one interest slider.</p>';
    });
    $('recDest').querySelectorAll('.rank-item').forEach((el) => el.onclick = () => this.routeTo(el.dataset.d));
  }

  renderItems(d) {
    const contentBy = new Map(d.content.map((r) => [r.id, r])), collabBy = new Map(d.collaborative.map((r) => [r.id, r]));
    flip($('recItems'), () => {
      $('recItems').innerHTML = d.fused.length ? d.fused.map((r, i) => `<div class="rank-item" data-key="${r.id}" data-id="${r.id}">
        <span class="n">${i + 1}</span>
        <div class="t"><b>${esc(r.attraction)}</b><div class="sub">${esc(r.destination)}${contentBy.get(r.id) ? ' · ' + contentBy.get(r.id).matched.map((c) => CAT_ICON[c] || c).join('') : ''}${collabBy.get(r.id) ? ` · loved by ${collabBy.get(r.id).lovedBy.length}` : ''}</div></div>
        <span class="v">${r.ranks.content ? `<span class="src c">C${r.ranks.content}</span>` : ''}${r.ranks.collaborative ? `<span class="src f">F${r.ranks.collaborative}</span>` : ''}</span></div>`).join('') : '<p class="muted small">No recommendations.</p>';
    });
    $('recItems').querySelectorAll('.rank-item').forEach((el) => el.onclick = () => this.why(el.dataset.id));
  }

  graph() {
    const net = this.store.network;
    return buildGraph(net.destinations, net.routes, { modes: ['road', 'rail', 'flight'], closed: new Set(net.routes.filter((r) => r.closed).map(routeKey)),
      traffic: new Map(net.routes.filter((r) => (r.traffic || 1) > 1).map((r) => [routeKey(r), r.traffic])), metric: 'hours' });
  }

  paintMap(d) {
    const s = this.scene, home = this.tourist.home;
    s.resetNodes(); s.clearOverlay(); s.syncRoutes(this.store.network.routes);
    const top = new Map(d.destinations.map((x, i) => [x.destination, i]));
    const visited = new Set(this.tourist.visits.map((v) => v.destination));
    s.nodes.forEach((n, name) => {
      if (name === home) s.setNodeLook(name, { color: 0x4ade80, glow: 1, sub: 'home' });
      else if (top.has(name)) s.setNodeLook(name, { color: 0xfbbf24, glow: 0.9, height: 4.2 - top.get(name) * 0.5, sub: `#${top.get(name) + 1}` });
      else s.setNodeLook(name, { color: visited.has(name) ? 0x14b8a6 : 0x1e293b, glow: 0.15, dim: true, sub: visited.has(name) ? 'visited' : '' });
    });
    s.setMarker(home, 'home');
    s.routes.forEach((e, k) => s.setRouteState(k, 'dim'));
    const maxScore = Math.max(...d.destinations.map((x) => x.score), 1);
    s.setBeams(d.destinations.map((x) => ({ name: x.destination, strength: Math.max(0.15, x.score / maxScore) })));
    if (d.destinations[0]) this.routeTo(d.destinations[0].destination, true);
  }

  routeTo(dest, quiet) {
    const p = solve('dijkstra', this.graph(), this.tourist.home, dest).path;
    this.scene.clearOverlay();
    if (p) this.scene.drawPath(p.legs);
    this.scene.flyTo(dest);
    if (!quiet && p) toast(`${this.tourist.home} → ${dest}: ${p.nodes.join(' → ')} (${p.totals.hours.toFixed(1)} h)`);
  }

  async why(id) {
    const d = this.last;
    const item = d.fused.find((r) => r.id === id);
    const c = d.content.find((r) => r.id === id), f = d.collaborative.find((r) => r.id === id);
    const box = $('recWhy');
    box.hidden = false;
    box.innerHTML = `<div class="card-title">WHY ${esc(item.attraction.toUpperCase())}?</div>
      <p class="small" style="margin-top:0">${c ? `Matches your interests: <b>${c.matched.map(esc).join(', ')}</b> (score ${c.score}).` : 'Not from your interest sliders.'}<br>
      ${f ? `Rated 4–5 by similar tourists: <b>${f.lovedBy.map(esc).join(', ')}</b>.` : 'No similar tourist recommends it.'}</p>
      <div id="whyGraph" class="graph2d" style="height:250px"></div>
      <div class="why-actions"><span class="small muted">I visited it:</span>${[1, 2, 3, 4, 5].map((n) => `<button class="btn" data-r="${n}">${n}★</button>`).join('')}</div>
      <details class="drawer"><summary>Cypher</summary><div id="whyCypher"></div></details>`;
    box.querySelectorAll('[data-r]').forEach((b) => b.onclick = () => this.visit(id, +b.dataset.r, item.attraction));
    box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    try {
      const e = await post('/api/recommend/explain', { tourist: this.tid, attraction: id });
      const focus = (e.graph.nodes.find((n) => n.labels[0] === 'Attraction' && n.caption === item.attraction) || {}).id;
      new Graph2D($('whyGraph'), { empty: 'No connecting paths.' }).setData(e.graph, focus);
      $('whyCypher').innerHTML = cypherBlock(e.cypher) + cypherBlock(d.cypher.content);
    } catch (err) { toast(err.message, 'error'); }
  }

  async visit(id, rating, name) {
    try {
      const r = await post('/api/visits', { tourist: this.tid, attraction: id, rating });
      toast(r.created ? `Saved in Neo4j: ${this.tourist.name} visited ${name} (${rating}★). Recommendations updated.` : 'Already visited.');
      $('recWhy').hidden = true;
      await this.load(this.tid);
    } catch (e) { toast(e.message, 'error'); }
  }

  async undo() {
    try {
      const r = await post('/api/visits/reset', { tourist: this.tid });
      toast(`Removed ${r.removed} demo visit(s).`);
      await this.load(this.tid);
    } catch (e) { toast(e.message, 'error'); }
  }
}
