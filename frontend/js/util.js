/* Shared helpers (ES module). */
export async function api(method, url, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  let res;
  try { res = await fetch(url, opts); } catch (e) { throw new Error('The backend is not reachable. Start it with "python app.py".'); }
  let data = null;
  try { data = await res.json(); } catch (e) { /* not JSON */ }
  if (!res.ok) { const err = new Error((data && data.error) || `Request failed (${res.status})`); err.data = data; throw err; }
  return data;
}
export const get = (u) => api('GET', u);
export const post = (u, b) => api('POST', u, b || {});

export const $ = (id) => document.getElementById(id);
export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const num = (v, d = 1) => (v === null || v === undefined || Number.isNaN(v) ? '—' : Number.isInteger(v) ? v.toLocaleString('en-IN') : Number(v.toFixed(d)).toLocaleString('en-IN'));
export const ms = (v) => (v < 1 ? v.toFixed(2) + ' ms' : v < 100 ? v.toFixed(1) + ' ms' : Math.round(v) + ' ms');
export const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
export const CAT_ICON = { Beach: '🏖️', Temple: '🛕', Heritage: '🏛️', Museum: '🖼️', Nature: '🌿', Wildlife: '🐘', Waterfall: '💧', Backwaters: '🛶', Plantation: '🍃', Adventure: '🧗', Spiritual: '🕉️', 'Hill Station': '⛰️' };
export const MODE_ICON = { road: '🚌', rail: '🚆', flight: '✈️' };
export const METRIC_UNIT = { hours: 'h', distanceKm: 'km', costInr: '₹' };
export const fmtMetric = (metric, v) => (v === null || v === undefined ? '—' : metric === 'costInr' ? '₹' + Math.round(v).toLocaleString('en-IN') : metric === 'distanceKm' ? Math.round(v) + ' km' : v.toFixed(1) + ' h');

let toastTimer;
export function toast(msg, kind) {
  const t = $('toast');
  t.textContent = msg;
  t.className = 'toast show' + (kind ? ' ' + kind : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.className = 'toast'; }, kind === 'error' ? 6000 : 2800);
}

export async function busy(btn, label, fn) {
  const old = btn.innerHTML;
  btn.disabled = true; btn.textContent = label;
  try { return await fn(); } catch (e) { toast(e.message, 'error'); return undefined; } finally { btn.disabled = false; btn.innerHTML = old; }
}

export function debounce(fn, wait) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), wait); };
}

export function haversine(a, b) {
  const R = 6371, toR = Math.PI / 180;
  const dLat = (b.lat - a.lat) * toR, dLon = (b.lon - a.lon) * toR;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * toR) * Math.cos(b.lat * toR) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

/* ---- Cypher highlighting ---- */
const KW = 'MATCH|OPTIONAL|WHERE|RETURN|WITH|CREATE|MERGE|SET|DELETE|DETACH|REMOVE|UNWIND|AS|ORDER|BY|DESC|ASC|LIMIT|SKIP|AND|OR|NOT|IN|IS|NULL|DISTINCT|CASE|WHEN|THEN|ELSE|END|ON|EXISTS|CALL|YIELD|SHOW|CONSTRAINT|INDEX|FOR|REQUIRE|UNIQUE|IF|PROFILE|EXPLAIN|UNION|ALL|TRUE|FALSE|FOREACH';
const FN = 'count|collect|size|keys|labels|type|nodes|relationships|length|shortestPath|allShortestPaths|coalesce|reduce|round|date|datetime|toString|toFloat|all|any|none|single|sum|avg|min|max|head|last|tail|range|sign|startNode|endNode';
export function highlight(code) {
  const re = new RegExp(`(\\/\\/[^\\n]*)|('(?:[^'\\\\]|\\\\.)*'|"(?:[^"\\\\]|\\\\.)*")|(\\$\\w+)|(:\\w+)|\\b(${KW})\\b|\\b(${FN})(?=\\s*\\()|\\b(\\d+(?:\\.\\d+)?)\\b`, 'gi');
  let out = '', last = 0, m;
  while ((m = re.exec(code))) {
    out += esc(code.slice(last, m.index));
    const t = m[0];
    if (m[1]) out += `<span class="tok-com">${esc(t)}</span>`;
    else if (m[2]) out += `<span class="tok-str">${esc(t)}</span>`;
    else if (m[3]) out += `<span class="tok-par">${esc(t)}</span>`;
    else if (m[4]) out += /^:[A-Z_]+$/.test(t) && t.length > 3 ? `:<span class="tok-rel">${esc(t.slice(1))}</span>` : `:<span class="tok-lab">${esc(t.slice(1))}</span>`;
    else if (m[5] || m[6]) out += `<span class="tok-kw">${esc(t)}</span>`;
    else out += `<span class="tok-num">${esc(t)}</span>`;
    last = m.index + t.length;
  }
  return out + esc(code.slice(last));
}
export const cypherBlock = (code) => `<pre class="cy">${highlight(code)}</pre>`;

export function cell(v) {
  if (v === null || v === undefined) return '<span class="muted">null</span>';
  if (Array.isArray(v)) return v.length && typeof v[0] !== 'object' ? esc(v.join(', ')) : v.map(cell).join(' ');
  if (typeof v === 'object') {
    if (v._node) return `<span class="tag">${esc(v._node)}</span>`;
    if (v._rel) return `<span class="tag">[:${esc(v._rel)}]</span>`;
    if (v._path) return esc(v._path.join(' → '));
    return `<code>${esc(JSON.stringify(v))}</code>`;
  }
  if (typeof v === 'boolean') return v ? '<span class="ok-text">true</span>' : '<span class="muted">false</span>';
  if (typeof v === 'number') return num(v, 2);
  return esc(v);
}
export function table(columns, rows, empty) {
  if (!rows.length) return `<p class="muted">${empty || 'No rows.'}</p>`;
  return `<table class="data"><thead><tr>${columns.map((c) => `<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((v) => `<td class="${typeof v === 'number' ? 'num' : ''}">${cell(v)}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
}

/* FLIP animation for re-ordered lists: items keep data-key */
export function flip(container, render) {
  const before = new Map([...container.children].map((el) => [el.dataset.key, el.getBoundingClientRect().top]));
  render();
  [...container.children].forEach((el) => {
    const prev = before.get(el.dataset.key);
    if (prev === undefined) { el.animate([{ opacity: 0, transform: 'translateX(12px)' }, { opacity: 1, transform: 'none' }], { duration: 300 }); return; }
    const dy = prev - el.getBoundingClientRect().top;
    if (dy) el.animate([{ transform: `translateY(${dy}px)` }, { transform: 'none' }], { duration: 380, easing: 'ease-out' });
  });
}
