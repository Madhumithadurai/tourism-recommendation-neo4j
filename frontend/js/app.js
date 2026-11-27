/* Bootstrap: tabs, Neo4j status, the shared 3D scene and the network loaded from Neo4j. */
import { $, get, toast } from './util.js';
import { MapScene } from './scene.js';
import { RouteLab } from './routelab.js';
import { Explore } from './explore.js';
import { Recommend } from './recommend.js';
import { Build } from './build.js';
import { Evaluate } from './evaluate.js';
import { Console } from './console.js';

export const store = { network: { destinations: [], routes: [] }, meta: null, lists: null, connected: false };
const scene = new MapScene();
const pages = {};
let current = null;

export async function reloadNetwork() {
  try {
    store.network = await get('/api/network');
  } catch (e) {
    store.network = { destinations: [], routes: [] };
  }
  scene.setNetwork(store.network.destinations, store.network.routes);
  Object.values(pages).forEach((p) => p.onNetwork && p.onNetwork(store.network));
  return store.network;
}

export async function reloadLists() {
  try { store.lists = await get('/api/lists'); } catch (e) { store.lists = null; }
  Object.values(pages).forEach((p) => p.onLists && p.onLists(store.lists));
}

function show(name) {
  document.querySelectorAll('#tabs button').forEach((b) => b.classList.toggle('active', b.dataset.page === name));
  document.querySelectorAll('.page').forEach((p) => { p.hidden = p.id !== 'page-' + name; });
  if (current && pages[current] && pages[current].leave) pages[current].leave();
  current = name;
  const stage = document.getElementById('stage-' + name);
  if (stage) scene.mount(stage);
  if (pages[name] && pages[name].enter) pages[name].enter();
  history.replaceState(null, '', '#' + name);
}
export const showPage = show;

const tip = $('tooltip');
scene.on('hover', (hit, e) => {
  if (!hit || !e) { tip.hidden = true; return; }
  let html = '';
  if (hit.kind === 'node') {
    const d = store.network.destinations.find((x) => x.name === hit.name);
    html = `<b>${d.name}</b> · ${d.state}<br>${d.attractions} attractions · best ${d.bestMonths.map((m) => 'JFMAMJJASOND'[m - 1]).join('')}<br><span style="color:#8396b3">${d.description}</span>`;
    if (current && pages[current] && pages[current].nodeTip) html += pages[current].nodeTip(hit.name);
  } else {
    const r = store.network.routes.find((x) => `${x.from}|${x.to}|${x.mode}` === hit.key) || {};
    html = `<b>${r.from} – ${r.to}</b><br>${r.mode} · ${r.distanceKm} km · ${r.hours} h${(r.traffic || 1) > 1 ? ` (×${r.traffic} traffic)` : ''} · ₹${r.costInr}${r.closed ? '<br><span style="color:#f87171">closed</span>' : ''}`;
  }
  tip.innerHTML = html;
  tip.hidden = false;
  tip.style.left = Math.min(e.clientX + 14, window.innerWidth - 310) + 'px';
  tip.style.top = (e.clientY + 14) + 'px';
});
scene.on('pickNode', (name) => pages[current] && pages[current].pickNode && pages[current].pickNode(name));
scene.on('pickRoute', (key, r) => pages[current] && pages[current].pickRoute && pages[current].pickRoute(key, r));
['legStart', 'legEnd', 'arrive', 'travelProgress'].forEach((ev) => scene.on(ev, (...a) => pages.lab && pages.lab[ev] && pages.lab[ev](...a)));

async function health() {
  const pill = $('dbPill');
  try {
    const h = await get('/api/health');
    pill.className = 'pill ' + (h.neo4j ? 'up' : 'down');
    pill.textContent = h.neo4j ? 'Neo4j connected' : 'Neo4j offline';
    pill.title = h.neo4j ? h.neo4jUri : h.neo4jError || '';
    if (h.neo4j && !store.connected) { store.connected = true; await reloadNetwork(); await reloadLists(); }
    store.connected = h.neo4j;
  } catch (e) {
    pill.className = 'pill down'; pill.textContent = 'Backend offline'; store.connected = false;
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  if (location.protocol === 'file:') $('fileBanner').hidden = false;
  try { store.meta = await get('/api/meta'); } catch (e) { toast(e.message, 'error'); }
  pages.lab = new RouteLab(scene, store, { reloadNetwork });
  pages.explore = new Explore(scene, store);
  pages.recommend = new Recommend(scene, store);
  pages.build = new Build(scene, store, { reloadNetwork, reloadLists });
  pages.evaluate = new Evaluate(store);
  pages.console = new Console(store);
  document.querySelectorAll('#tabs button').forEach((b) => b.addEventListener('click', () => show(b.dataset.page)));
  window.tripgraph = { scene, pages, store };   // handy for debugging in the browser console
  await health();
  setInterval(health, 15000);
  const wanted = location.hash.slice(1);
  const empty = !store.network.destinations.length;
  show(pages[wanted] ? wanted : empty ? 'build' : 'lab');
  if (empty && store.connected) toast('The database is empty: press "Build everything" to load the sample data.');
});
