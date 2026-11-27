/* Build graph: run the population scripts step by step and watch the 3D graph grow. */
import { $, esc, get, post, toast, busy, cypherBlock, table, ms } from './util.js';
import { LABEL_COLOR } from './graph2d.js';

export class Build {
  constructor(scene, store, hooks) {
    this.scene = scene; this.store = store; this.hooks = hooks; this.steps = null;
    $('buildAll').onclick = () => busy($('buildAll'), 'Building…', () => this.runAll());
    $('buildCheck').onclick = () => busy($('buildCheck'), 'Checking…', () => this.check());
    $('buildReset').onclick = () => this.reset();
    this.load();
    this.model();
  }

  async load() {
    try { this.steps = await get('/api/setup/steps'); } catch (e) { return; }
    const list = [...this.steps.constraints.map((s) => ({ ...s, script: 'constraints', label: 'Constraints' })), ...this.steps.sample.map((s) => ({ ...s, script: 'sample', label: 'Data' }))];
    this.flat = list;
    $('buildSteps').innerHTML = list.map((s, i) => `<div class="step" id="bstep-${i}">
      <div class="step-head"><b><span class="n">${s.script === 'constraints' ? 'C' : ''}${s.number}</span>${esc(s.title)}</b><button class="btn" data-i="${i}">▶</button></div>
      <details><summary>Cypher · ${s.cypher.length.toLocaleString()} characters</summary>${cypherBlock(s.cypher.length > 2500 ? s.cypher.slice(0, 2500) + '\n// … (shortened here; the full statement runs)' : s.cypher)}</details>
      <div class="res"></div></div>`).join('');
    $('buildSteps').querySelectorAll('button[data-i]').forEach((b) => b.onclick = () => busy(b, '…', () => this.run(+b.dataset.i)));
  }

  enter() { this.scene.resetNodes(); this.scene.clearOverlay(); this.scene.syncRoutes(this.store.network.routes); this.counts(); }

  async run(i) {
    const s = this.flat[i], box = $('bstep-' + i);
    box.classList.add('running');
    try {
      const d = await post('/api/setup/run', { script: s.script, step: s.number });
      const tot = {};
      d.report.forEach((r) => Object.entries(r.counters).forEach(([k, v]) => { tot[k] = (tot[k] || 0) + v; }));
      box.querySelector('.res').className = 'res';
      box.querySelector('.res').textContent = '✓ ' + (Object.entries(tot).map(([k, v]) => `${v} ${k.replace(/_/g, ' ')}`).join(', ') || 'already present (MERGE)') + ` · ${ms(d.report.reduce((a, r) => a + r.ms, 0))}`;
      box.classList.add('done');
      const last = d.report[d.report.length - 1];
      if (last && last.rows.length && s.script === 'sample' && s.number === 9) box.querySelector('.res').innerHTML += table(last.columns, last.rows);
    } catch (e) {
      box.querySelector('.res').className = 'res bad';
      box.querySelector('.res').textContent = '✗ ' + e.message;
      throw e;
    } finally { box.classList.remove('running'); }
    if (s.script === 'sample') { await this.hooks.reloadNetwork(); this.enter(); }
    await this.counts();
  }

  async runAll() {
    for (let i = 0; i < this.flat.length; i++) {
      await this.run(i);
      await new Promise((r) => setTimeout(r, 450));
    }
    await this.hooks.reloadLists();
    toast('Graph built. Open the Route Lab and click two towns.');
  }

  async counts() {
    try {
      const d = await get('/api/overview');
      $('buildCounts').innerHTML = d.connected && d.labels.length
        ? d.labels.map((l) => `<span style="color:${LABEL_COLOR[l.label] || '#8396b3'}">${esc(l.label)}<b>${l.count}</b></span>`).join('') + `<span>relationships<b>${d.types.reduce((a, t) => a + t.count, 0)}</b></span>`
        : '<span>The database is empty</span>';
    } catch (e) { $('buildCounts').innerHTML = '<span>Neo4j offline</span>'; }
  }

  async reset() {
    if (!confirm('Delete all TripGraph data from Neo4j? (constraints are kept)')) return;
    try {
      await post('/api/setup/run', { script: 'reset', step: 'all' });
      document.querySelectorAll('#buildSteps .step').forEach((s) => { s.classList.remove('done'); s.querySelector('.res').textContent = ''; });
      await this.hooks.reloadNetwork(); await this.hooks.reloadLists(); await this.counts();
      toast('All data deleted.');
    } catch (e) { toast(e.message, 'error'); }
  }

  async check() {
    const d = await post('/api/selfcheck');
    $('checkOut').innerHTML = `<div class="card"><div class="card-title">PRE-DEMO CHECK <span class="right ${d.passed === d.total ? 'ok-text' : 'bad-text'}">${d.passed} / ${d.total}</span></div>
      <div class="table-wrap" style="max-height:none"><table class="data"><tbody>${d.checks.map((c) => `<tr class="chk-row ${c.ok ? 'ok' : 'bad'}"><td>${esc(c.name)}</td><td class="${c.ok ? 'muted' : 'bad-text'}">${esc(c.detail)}</td></tr>`).join('')}</tbody></table></div></div>`;
    $('checkOut').scrollIntoView({ behavior: 'smooth' });
  }

  model() {
    const M = this.store.meta && this.store.meta.model;
    if (!M) return;
    const P = { Tourist: [70, 160], Category: [200, 40], Attraction: [200, 125], Destination: [330, 160], Hotel: [200, 270] }, R = 30;
    const edges = [];
    M.relationships.forEach((r, idx) => (r.from.includes('/') ? r.from.split(' / ') : [r.from]).forEach((f) => edges.push({ r, idx, from: f, to: r.to })));
    const groups = {};
    edges.forEach((e) => { const k = [e.from, e.to].sort().join('|'); (groups[k] = groups[k] || []).push(e); });
    let s = '<svg viewBox="0 0 400 310"><defs><marker id="mdA" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="md-arrow"/></marker></defs>';
    edges.forEach((e) => {
      let d, lx, ly;
      if (e.from === e.to) { const [x, y] = P[e.from]; d = `M${x + 12},${y - 28} C${x + 45},${y - 95} ${x + 85},${y - 25} ${x + 29},${y - 8}`; lx = x + 58; ly = y - 68; }
      else {
        const g = groups[[e.from, e.to].sort().join('|')], i = g.indexOf(e);
        const [ax, ay] = P[e.from], [bx, by] = P[e.to];
        const dx = bx - ax, dy = by - ay, L = Math.hypot(dx, dy), ux = dx / L, uy = dy / L, nx = -uy, ny = ux, off = (i - (g.length - 1) / 2) * 30;
        const mx = (ax + bx) / 2 + nx * off, my = (ay + by) / 2 + ny * off;
        d = `M${ax + ux * R},${ay + uy * R} Q${mx},${my} ${bx - ux * (R + 2)},${by - uy * (R + 2)}`;
        lx = (ax + bx) / 2 + nx * off * 0.55; ly = (ay + by) / 2 + ny * off * 0.55;
      }
      s += `<g class="md-edge" data-rel="${e.idx}"><path d="${d}" marker-end="url(#mdA)"/><text x="${lx}" y="${ly}" text-anchor="middle">${e.r.type}</text></g>`;
    });
    M.nodes.forEach((n) => { const [x, y] = P[n.label]; s += `<g class="md-node" data-node="${n.label}"><circle cx="${x}" cy="${y}" r="${R}" fill="${LABEL_COLOR[n.label]}"/><text x="${x}" y="${y + 4}" text-anchor="middle" style="font-size:${n.label.length > 9 ? 8.5 : 10}px">${n.label}</text></g>`; });
    $('modelSvg').innerHTML = s + '</svg>';
    $('modelSvg').onclick = (ev) => {
      const ng = ev.target.closest('.md-node'), eg = ev.target.closest('.md-edge');
      $('modelSvg').querySelectorAll('.md-edge').forEach((x) => x.classList.toggle('active', !!eg && x.dataset.rel === eg.dataset.rel));
      if (ng) { const n = M.nodes.find((x) => x.label === ng.dataset.node); $('modelInfo').innerHTML = `<b style="color:var(--ink)">:${n.label}</b> — ${esc(n.why)}<br><code>${n.properties.map(esc).join(', ')}</code>`; }
      else if (eg) { const r = M.relationships[+eg.dataset.rel]; $('modelInfo').innerHTML = `<b style="color:var(--ink)">[:${r.type}]</b> (${esc(r.from)}) → (${esc(r.to)}) — ${esc(r.why)}${r.properties.length ? `<br><code>${r.properties.map(esc).join(', ')}</code>` : ''}`; }
    };
  }
}
