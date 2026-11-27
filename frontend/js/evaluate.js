/* Live evaluation: tourists are evaluated one at a time and the scoreboard fills in as results arrive. */
import { $, esc, get, post, toast, busy } from './util.js';

const COLORS = { popular: '#64748b', content: '#f59e0b', collaborative: '#60a5fa', hybrid: '#2dd4bf' };

export class Evaluate {
  constructor(store) {
    this.store = store;
    $('evalRun').onclick = () => busy($('evalRun'), 'Evaluating…', () => this.run());
  }

  async run() {
    const { cases, methods, attractions } = await get('/api/evaluate/cases');
    if (!cases.length) throw new Error('No tourists with enough visits. Build the graph first.');
    const keys = Object.keys(methods);
    const res = Object.fromEntries(keys.map((k) => [k, []]));
    $('evalTable').innerHTML = `<table><thead><tr><th>Tourist</th><th>Hidden visit</th>${keys.map((k) => `<th style="color:${COLORS[k]}">${esc(methods[k].split(' ')[0])}</th>`).join('')}</tr></thead><tbody>
      ${cases.map((c, i) => `<tr id="erow-${i}"><td>${esc(c.name)}</td><td class="muted">${esc(c.hiddenName)}</td>${keys.map(() => '<td></td>').join('')}</tr>`).join('')}</tbody></table>`;
    this.bars(keys, methods, res, attractions);
    for (let i = 0; i < cases.length; i++) {
      const c = cases[i];
      $('evalProgress').textContent = `Tourist ${i + 1} of ${cases.length}: ${c.name}`;
      const d = await post('/api/evaluate/one', { tourist: c.tourist, hidden: c.hidden });
      const row = $('erow-' + i);
      keys.forEach((k, j) => {
        const r = d.results[k];
        res[k].push({ hidden: c.hidden, ranking: r.ranking });
        const td = row.children[2 + j];
        td.className = 'cell ' + (r.rank && r.rank <= 5 ? 'h5' : r.rank ? 'h10' : 'miss');
        td.textContent = r.rank ? '#' + r.rank : '—';
        td.title = 'Top 5: ' + r.top.join(', ');
      });
      this.bars(keys, methods, res, attractions);
      await new Promise((r) => setTimeout(r, 120));
    }
    const best = keys.reduce((a, k) => (this.metric(res[k], attractions)['hit@10'] > this.metric(res[a], attractions)['hit@10'] ? k : a), keys[0]);
    $('evalProgress').textContent = `Done: ${cases.length} tourists. Best Hit@10: ${methods[best]}.`;
    toast(`Evaluation finished. Best Hit@10: ${methods[best]}.`);
  }

  metric(list, n) {
    const N = list.length || 1;
    const hit = (k) => list.filter((r) => r.ranking.slice(0, k).includes(r.hidden)).length / N;
    const mrr = list.reduce((a, r) => a + (r.ranking.includes(r.hidden) ? 1 / (r.ranking.indexOf(r.hidden) + 1) : 0), 0) / N;
    const cov = new Set(list.flatMap((r) => r.ranking)).size / (n || 1);
    return { 'hit@5': hit(5), 'hit@10': hit(10), mrr, coverage: cov };
  }

  bars(keys, methods, res, n) {
    const ms = Object.fromEntries(keys.map((k) => [k, this.metric(res[k], n)]));
    const block = (title, key, fmt, scale = 1) => `<div class="mbar"><h4>${title}</h4>${keys.map((k) => `<div class="row"><span>${esc(methods[k].split(' ')[0])}</span>
      <div class="track"><div class="fill" style="width:${Math.min(100, ms[k][key] * 100 * scale)}%;background:${COLORS[k]}"></div></div><span class="val">${fmt(ms[k][key])}</span></div>`).join('')}</div>`;
    const pct = (v) => (v * 100).toFixed(0) + '%';
    if (!$('evalBars').children.length) {
      $('evalBars').innerHTML = block('Hit@5', 'hit@5', pct) + block('Hit@10', 'hit@10', pct) + block('MRR (×2 scale)', 'mrr', (v) => v.toFixed(3), 2) + block('Coverage of attractions', 'coverage', pct);
      return;
    }
    // update widths in place so the bars animate
    const html = block('Hit@5', 'hit@5', pct) + block('Hit@10', 'hit@10', pct) + block('MRR (×2 scale)', 'mrr', (v) => v.toFixed(3), 2) + block('Coverage of attractions', 'coverage', pct);
    const tmp = document.createElement('div');
    tmp.innerHTML = html;
    const newFills = tmp.querySelectorAll('.fill'), newVals = tmp.querySelectorAll('.val');
    $('evalBars').querySelectorAll('.fill').forEach((f, i) => { f.style.width = newFills[i].style.width; });
    $('evalBars').querySelectorAll('.val').forEach((v, i) => { v.textContent = newVals[i].textContent; });
  }
}
