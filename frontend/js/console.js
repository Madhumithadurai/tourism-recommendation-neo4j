/* Cypher console: every query of the project, one click to load and run. */
import { $, esc, post, toast, busy, table, ms } from './util.js';
import { Graph2D } from './graph2d.js';

const SECTIONS = { model: 'MODEL', discover: 'DESTINATION DISCOVERY', routes: 'ROUTES', recommend: 'RECOMMENDATIONS' };

export class Console {
  constructor(store) {
    this.store = store;
    this.graph = new Graph2D($('conGraph'), { empty: 'Return nodes, relationships or paths to see a graph.' });
    $('conRun').onclick = () => busy($('conRun'), 'Running…', () => this.run());
    $('conText').addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); $('conRun').click(); } });
    this.library();
  }

  library() {
    const qs = (this.store.meta && this.store.meta.queries) || [];
    let html = '', sec = null;
    qs.forEach((q) => {
      if (q.section !== sec) { sec = q.section; html += `<h5>${SECTIONS[sec] || sec}</h5>`; }
      html += `<button data-id="${q.id}">${esc(q.title)}</button>`;
    });
    html += '<h5>EXTRA</h5><button data-extra="routes">All routes as a graph</button><button data-extra="tourist">One tourist and everything they touch</button>';
    $('conLib').innerHTML = html;
    $('conLib').querySelectorAll('button').forEach((b) => b.onclick = () => {
      $('conLib').querySelectorAll('button').forEach((x) => x.classList.toggle('on', x === b));
      if (b.dataset.extra === 'routes') return this.load('MATCH (a:Destination)-[r:ROUTE]->(b:Destination)\nRETURN a, r, b', {});
      if (b.dataset.extra === 'tourist') return this.load('MATCH (t:Tourist {touristId: $tourist})-[r]->(x)\nRETURN t, r, x', { tourist: 't01' });
      const q = qs.find((x) => x.id === b.dataset.id);
      const text = q.cypher.replace('{maxHops}', '5').replace(/\{metric\}/g, 'hours');
      const params = {};
      q.params.forEach((p) => { if (p !== 'maxHops' && p !== 'metric') params[p] = this.store.meta.sample[p]; });
      if (text.includes('$hidden')) params.hidden = null;
      this.load(text, params);
    });
  }

  load(text, params) {
    $('conText').value = text;
    $('conParams').value = JSON.stringify(params);
    $('conRun').click();
  }

  async run() {
    let params;
    try { params = JSON.parse($('conParams').value || '{}'); } catch (e) { throw new Error('Parameters must be valid JSON, e.g. {"tourist": "t01"}'); }
    const d = await post('/api/playground', { cypher: $('conText').value, params, profile: $('conProfile').checked });
    $('conMeta').textContent = `${d.rowCount} row${d.rowCount === 1 ? '' : 's'} · ${ms(d.timing.wallMs)}${d.dbHits != null ? ` · ${d.dbHits} db hits` : ''}`;
    $('conTable').innerHTML = table(d.columns, d.rows);
    this.graph.setData(d.graph);
  }
}
