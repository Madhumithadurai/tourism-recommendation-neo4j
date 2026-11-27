/* Small 2D force-directed graph (SVG, no libraries) for explanation paths and console results. */
import { esc } from './util.js';

export const LABEL_COLOR = { Tourist: '#2dd4bf', Destination: '#4ade80', Attraction: '#f59e0b', Category: '#e879f9', Hotel: '#a78bfa' };
const REL_COLOR = { ROUTE: '#60a5fa', VISITED: '#f59e0b', INTERESTED_IN: '#e879f9', HAS_CATEGORY: '#e879f9', LOCATED_IN: '#4ade80', STAYED_AT: '#a78bfa', LIVES_IN: '#4ade80', WISHLISTED: '#2dd4bf' };
const NS = 'http://www.w3.org/2000/svg';
const el = (tag, attrs) => { const e = document.createElementNS(NS, tag); Object.entries(attrs || {}).forEach(([k, v]) => e.setAttribute(k, v)); return e; };

export class Graph2D {
  constructor(host, { empty = 'No graph to show.' } = {}) {
    this.host = host; this.empty = empty; this.raf = null;
    this.view = { x: 0, y: 0, k: 1 };
  }

  setData(graph, focus) {
    cancelAnimationFrame(this.raf);
    this.host.innerHTML = '';
    if (!graph || !graph.nodes.length) { this.host.innerHTML = `<div class="g2-empty">${esc(this.empty)}</div>`; return; }
    const W = this.host.clientWidth || 400, H = this.host.clientHeight || 300;
    const svg = el('svg', { viewBox: `0 0 ${W} ${H}` });
    const g = el('g');
    svg.appendChild(g);
    this.host.appendChild(svg);
    const nodes = graph.nodes.map((n, i) => ({ ...n, x: W / 2 + Math.cos(i * 2.4) * (40 + i * 6), y: H / 2 + Math.sin(i * 2.4) * (40 + i * 6), vx: 0, vy: 0 }));
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const links = graph.relationships.filter((r) => byId.has(r.source) && byId.has(r.target)).map((r) => ({ ...r, s: byId.get(r.source), t: byId.get(r.target) }));
    const linkEls = links.map((l) => {
      const line = el('line', { class: 'g2-edge', stroke: REL_COLOR[l.type] || '#4b5d7a' });
      const lab = el('text', { class: 'g2-label', 'text-anchor': 'middle' });
      lab.textContent = l.type === 'ROUTE' ? `${l.properties.mode}` : l.type;
      g.append(line, lab);
      return { l, line, lab };
    });
    const nodeEls = nodes.map((n) => {
      const grp = el('g', { class: 'g2-node' });
      const label = n.labels[0];
      const r = n.id === focus ? 13 : label === 'Category' ? 8 : 10;
      const c = el('circle', { r, fill: LABEL_COLOR[label] || '#8396b3' });
      if (n.id === focus) c.setAttribute('stroke', '#fff');
      const t = el('text', { 'text-anchor': 'middle', dy: r + 11 });
      t.textContent = (n.caption || '').length > 22 ? n.caption.slice(0, 21) + '…' : n.caption;
      const title = el('title'); title.textContent = `${label}: ${n.caption}`;
      grp.append(c, t, title);
      g.appendChild(grp);
      let drag = null;
      grp.addEventListener('pointerdown', (e) => { e.stopPropagation(); drag = true; n.fixed = true; grp.setPointerCapture(e.pointerId); });
      grp.addEventListener('pointermove', (e) => { if (!drag) return; const p = this.toLocal(svg, e); n.x = p.x; n.y = p.y; tick(0.3); });
      grp.addEventListener('pointerup', () => { drag = null; });
      return { n, grp };
    });
    // pan & zoom
    let pan = null;
    svg.addEventListener('pointerdown', (e) => { pan = { x: e.clientX, y: e.clientY, vx: this.view.x, vy: this.view.y }; });
    svg.addEventListener('pointermove', (e) => { if (!pan) return; const s = W / svg.clientWidth; this.view.x = pan.vx + (e.clientX - pan.x) * s; this.view.y = pan.vy + (e.clientY - pan.y) * s; apply(); });
    svg.addEventListener('pointerup', () => { pan = null; });
    svg.addEventListener('wheel', (e) => { e.preventDefault(); this.view.k = Math.min(3, Math.max(0.3, this.view.k * (e.deltaY < 0 ? 1.1 : 0.9))); apply(); }, { passive: false });
    this.view = { x: 0, y: 0, k: 1 };
    const apply = () => g.setAttribute('transform', `translate(${this.view.x},${this.view.y}) scale(${this.view.k})`);
    const draw = () => {
      linkEls.forEach(({ l, line, lab }) => {
        line.setAttribute('x1', l.s.x); line.setAttribute('y1', l.s.y); line.setAttribute('x2', l.t.x); line.setAttribute('y2', l.t.y);
        lab.setAttribute('x', (l.s.x + l.t.x) / 2); lab.setAttribute('y', (l.s.y + l.t.y) / 2 - 3);
      });
      nodeEls.forEach(({ n, grp }) => grp.setAttribute('transform', `translate(${n.x},${n.y})`));
    };
    const tick = (alpha) => {
      for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        let dx = b.x - a.x, dy = b.y - a.y, d2 = dx * dx + dy * dy || 1;
        const f = (2600 / d2) * alpha, d = Math.sqrt(d2);
        dx /= d; dy /= d;
        a.vx -= dx * f; a.vy -= dy * f; b.vx += dx * f; b.vy += dy * f;
      }
      links.forEach((l) => {
        const dx = l.t.x - l.s.x, dy = l.t.y - l.s.y, d = Math.hypot(dx, dy) || 1, f = (d - 75) * 0.04 * alpha;
        l.s.vx += (dx / d) * f; l.s.vy += (dy / d) * f; l.t.vx -= (dx / d) * f; l.t.vy -= (dy / d) * f;
      });
      nodes.forEach((n) => {
        n.vx += (W / 2 - n.x) * 0.004 * alpha; n.vy += (H / 2 - n.y) * 0.004 * alpha;
        if (!n.fixed) { n.x += n.vx; n.y += n.vy; }
        n.vx *= 0.6; n.vy *= 0.6;
      });
      draw();
    };
    let alpha = 1;
    const run = () => { tick(alpha); alpha *= 0.985; if (alpha > 0.02) this.raf = requestAnimationFrame(run); };
    run();
  }

  toLocal(svg, e) {
    const pt = svg.createSVGPoint();
    pt.x = e.clientX; pt.y = e.clientY;
    const p = pt.matrixTransform(svg.getScreenCTM().inverse());
    return { x: (p.x - this.view.x) / this.view.k, y: (p.y - this.view.y) / this.view.k };
  }
}
