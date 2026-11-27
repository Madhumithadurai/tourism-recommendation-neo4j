/* The 3D map shared by Route Lab, Explore, Recommend and Build.
   Destinations are towers placed by latitude/longitude on a dark board, routes are tubes (flights are arcs),
   and a traveller vehicle can drive along a path. One renderer is moved between pages with mount(). */
import * as THREE from 'three';
import { OrbitControls } from '../vendor/OrbitControls.js';
import { CSS2DRenderer, CSS2DObject } from '../vendor/CSS2DRenderer.js';

const COLORS = {
  board: 0x0d1729, edge: 0x2dd4bf, grid: 0x1c3355,
  node: 0xf59e0b, frontier: 0x22d3ee, visited: 0x14b8a6, current: 0xffffff, path: 0x4ade80, start: 0x4ade80, goal: 0xf472b6,
  road: 0xf59e0b, rail: 0x60a5fa, flight: 0xe879f9, closed: 0xef4444, traffic: 0xfb923c, added: 0xe2e8f0, relax: 0xfacc15,
  dim: 0x334155, reach: 0x38bdf8, beam: 0x2dd4bf, home: 0x4ade80,
};
const SCALE = 6.2;           // board units per degree

export class MapScene {
  constructor() {
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setClearColor(0x000000, 0);
    this.labels = new CSS2DRenderer();
    Object.assign(this.labels.domElement.style, { position: 'absolute', top: '0', left: '0', pointerEvents: 'none' });
    this.scene = new THREE.Scene();
    this.scene.fog = new THREE.Fog(0x070d18, 70, 140);
    this.camera = new THREE.PerspectiveCamera(42, 1, 0.1, 400);
    this.camera.position.set(0, 46, 42);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    Object.assign(this.controls, { enableDamping: true, dampingFactor: 0.08, maxPolarAngle: 1.38, minDistance: 12, maxDistance: 110 });
    this.scene.add(new THREE.HemisphereLight(0xbcd4ff, 0x0a1020, 0.9));
    const sun = new THREE.DirectionalLight(0xffffff, 1.1);
    sun.position.set(-20, 40, 25);
    this.scene.add(sun);
    this.board = new THREE.Group(); this.routeGroup = new THREE.Group(); this.nodeGroup = new THREE.Group();
    this.fx = new THREE.Group(); this.overlay = new THREE.Group();
    this.scene.add(this.board, this.routeGroup, this.nodeGroup, this.fx, this.overlay);
    this.nodes = new Map(); this.routes = new Map();
    this.ripples = []; this.beams = [];
    this.raycaster = new THREE.Raycaster();
    this.pointer = new THREE.Vector2();
    this.handlers = {};
    this.traveller = null;
    this.clock = new THREE.Clock();
    this.bindPointer();
    this.loop();
  }

  on(name, fn) { this.handlers[name] = fn; }
  emit(name, ...a) { if (this.handlers[name]) this.handlers[name](...a); }

  mount(container) {
    if (this.container === container) return;
    this.container = container;
    container.prepend(this.labels.domElement);
    container.prepend(this.renderer.domElement);
    if (this.ro) this.ro.disconnect();
    this.ro = new ResizeObserver(() => this.resize());
    this.ro.observe(container);
    this.resize();
  }

  resize() {
    if (!this.container) return;
    const w = this.container.clientWidth, h = this.container.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h);
    this.labels.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  project(lat, lon) { return new THREE.Vector3((lon - this.center.lon) * SCALE * this.k, 0, -(lat - this.center.lat) * SCALE); }

  // ------------------------------------------------------------------ build
  setNetwork(destinations, routes) {
    for (const g of [this.board, this.routeGroup, this.nodeGroup, this.fx, this.overlay]) {
      while (g.children.length) { const c = g.children.pop(); c.traverse((o) => { if (o.element) o.element.remove(); }); }
    }
    this.nodes.clear(); this.routes.clear(); this.beams = []; this.ripples = [];
    this.stopTraveller();
    if (!destinations.length) return;
    const lats = destinations.map((d) => d.lat), lons = destinations.map((d) => d.lon);
    this.center = { lat: (Math.min(...lats) + Math.max(...lats)) / 2, lon: (Math.min(...lons) + Math.max(...lons)) / 2 };
    this.k = Math.cos(this.center.lat * Math.PI / 180);
    this.buildBoard(lats, lons);
    destinations.forEach((d) => this.addNode(d));
    routes.forEach((r) => this.addRoute(r));
  }

  buildBoard(lats, lons) {
    const p0 = this.project(Math.min(...lats) - 0.6, Math.min(...lons) - 0.8), p1 = this.project(Math.max(...lats) + 0.6, Math.max(...lons) + 0.8);
    const w = p1.x - p0.x, d = p0.z - p1.z;
    const geo = new THREE.BoxGeometry(w, 0.5, d);
    const plate = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: COLORS.board, roughness: 0.9, metalness: 0.1 }));
    plate.position.set((p0.x + p1.x) / 2, -0.26, (p0.z + p1.z) / 2);
    this.board.add(plate);
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo), new THREE.LineBasicMaterial({ color: COLORS.edge, transparent: true, opacity: 0.55 }));
    edges.position.copy(plate.position);
    this.board.add(edges);
    const pts = [];
    for (let lon = Math.ceil(Math.min(...lons) - 0.8); lon <= Math.max(...lons) + 0.8; lon++) {
      const a = this.project(Math.min(...lats) - 0.6, lon), b = this.project(Math.max(...lats) + 0.6, lon);
      pts.push(a.x, 0.01, a.z, b.x, 0.01, b.z);
      this.board.add(this.label(`${lon}°E`, new THREE.Vector3(a.x, 0.1, a.z + 1.2), 'lbl dim'));
    }
    for (let lat = Math.ceil(Math.min(...lats) - 0.6); lat <= Math.max(...lats) + 0.6; lat++) {
      const a = this.project(lat, Math.min(...lons) - 0.8), b = this.project(lat, Math.max(...lons) + 0.8);
      pts.push(a.x, 0.01, a.z, b.x, 0.01, b.z);
      this.board.add(this.label(`${lat}°N`, new THREE.Vector3(a.x - 1.6, 0.1, a.z), 'lbl dim'));
    }
    const grid = new THREE.BufferGeometry();
    grid.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
    this.board.add(new THREE.LineSegments(grid, new THREE.LineBasicMaterial({ color: COLORS.grid, transparent: true, opacity: 0.6 })));
  }

  label(text, pos, cls = 'lbl') {
    const div = document.createElement('div');
    div.className = cls;
    div.innerHTML = text;
    const obj = new CSS2DObject(div);
    obj.position.copy(pos);
    return obj;
  }

  addNode(d) {
    const pos = this.project(d.lat, d.lon);
    const baseH = 0.7 + Math.min(d.attractions || 0, 5) * 0.28;
    const mat = new THREE.MeshStandardMaterial({ color: COLORS.node, emissive: COLORS.node, emissiveIntensity: 0.25, roughness: 0.5 });
    const mesh = new THREE.Mesh(new THREE.CylinderGeometry(0.42, 0.5, 1, 20), mat);
    mesh.position.set(pos.x, baseH / 2, pos.z);
    mesh.scale.y = baseH;
    mesh.userData = { kind: 'node', name: d.name };
    const ring = new THREE.Mesh(new THREE.TorusGeometry(0.85, 0.06, 8, 32), new THREE.MeshBasicMaterial({ color: COLORS.frontier, transparent: true, opacity: 0.9 }));
    ring.rotation.x = Math.PI / 2;
    ring.position.set(pos.x, 0.06, pos.z);
    ring.visible = false;
    const lbl = this.label(`${d.name}<small></small>`, new THREE.Vector3(pos.x, baseH + 0.6, pos.z));
    this.nodeGroup.add(mesh, ring, lbl);
    const n = { d, pos, mesh, mat, ring, lbl, baseH, h: baseH, targetH: baseH, color: new THREE.Color(COLORS.node), target: new THREE.Color(COLORS.node), glow: 0.25, targetGlow: 0.25, marker: null, state: 'idle', born: performance.now() };
    mesh.scale.y = 0.01;
    n.h = 0.01;
    this.nodes.set(d.name, n);
  }

  addRoute(r) {
    const key = `${r.from}|${r.to}|${r.mode}`;
    const a = this.nodes.get(r.from), b = this.nodes.get(r.to);
    if (!a || !b) return;
    const twin = [...this.routes.values()].filter((x) => (x.r.from === r.from && x.r.to === r.to) || (x.r.from === r.to && x.r.to === r.from)).length;
    const dir = new THREE.Vector3().subVectors(b.pos, a.pos);
    const side = new THREE.Vector3(-dir.z, 0, dir.x).normalize().multiplyScalar(twin * 0.32);
    let curve;
    if (r.mode === 'flight') {
      const mid = new THREE.Vector3().addVectors(a.pos, b.pos).multiplyScalar(0.5);
      mid.y = 2.5 + dir.length() * 0.12;
      curve = new THREE.QuadraticBezierCurve3(a.pos.clone().setY(0.2), mid, b.pos.clone().setY(0.2));
    } else {
      const y = r.mode === 'rail' ? 0.12 : 0.08;
      curve = new THREE.LineCurve3(a.pos.clone().add(side).setY(y), b.pos.clone().add(side).setY(y));
    }
    const radius = r.mode === 'road' ? 0.09 : r.mode === 'rail' ? 0.07 : 0.05;
    const mat = new THREE.MeshStandardMaterial({ color: COLORS[r.mode], emissive: COLORS[r.mode], emissiveIntensity: 0.35, transparent: true, opacity: 0.55 });
    const mesh = new THREE.Mesh(new THREE.TubeGeometry(curve, r.mode === 'flight' ? 40 : 2, radius, 6, false), mat);
    const hit = new THREE.Mesh(new THREE.TubeGeometry(curve, r.mode === 'flight' ? 20 : 2, 0.45, 5, false), new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false }));
    hit.userData = { kind: 'route', key };
    this.routeGroup.add(mesh, hit);
    const badge = this.label('', curve.getPointAt(0.5).clone().setY(curve.getPointAt(0.5).y + 0.5), 'road-badge');
    this.routeGroup.add(badge);
    this.routes.set(key, { key, r: { ...r }, curve, mesh, mat, hit, badge, state: 'idle', flash: 0 });
    this.refreshRoute(key);
  }

  // ------------------------------------------------------------------ node & route states
  setNodeState(name, state) {
    const n = this.nodes.get(name);
    if (!n) return;
    n.state = state;
    const c = { idle: COLORS.node, frontier: COLORS.frontier, visited: COLORS.visited, current: COLORS.current, path: COLORS.path,
      start: COLORS.start, goal: COLORS.goal, dim: COLORS.dim }[state] ?? COLORS.node;
    n.target.set(c);
    n.targetGlow = state === 'idle' || state === 'dim' ? 0.25 : state === 'current' ? 1.2 : 0.7;
    n.ring.visible = state === 'frontier';
    n.lbl.element.classList.toggle('dim', state === 'dim');
  }

  setNodeLook(name, { color, height, glow, sub, dim }) {
    const n = this.nodes.get(name);
    if (!n) return;
    if (color !== undefined) n.target.set(color);
    if (height !== undefined) n.targetH = height;
    if (glow !== undefined) n.targetGlow = glow;
    if (sub !== undefined) n.lbl.element.querySelector('small').textContent = sub;
    if (dim !== undefined) n.lbl.element.classList.toggle('dim', dim);
  }

  resetNodes() {
    this.nodes.forEach((n, name) => { this.setNodeState(name, 'idle'); n.targetH = n.baseH; this.setNodeLook(name, { sub: '', dim: false }); this.setMarker(name, null); });
    this.clearBeams();
  }

  setMarker(name, kind) {
    const n = this.nodes.get(name);
    if (!n) return;
    if (n.marker) { this.fx.remove(n.marker); n.marker = null; }
    if (!kind) return;
    const color = kind === 'start' ? COLORS.start : kind === 'home' ? COLORS.home : COLORS.goal;
    const m = new THREE.Mesh(new THREE.ConeGeometry(0.45, 1.1, 16), new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0.8 }));
    m.rotation.x = Math.PI;
    m.userData.bob = Math.random() * 6;
    m.userData.node = name;
    n.marker = m;
    this.fx.add(m);
  }

  refreshRoute(key) {
    const e = this.routes.get(key);
    if (!e) return;
    const r = e.r;
    let color = COLORS[r.mode], opacity = 0.55, glow = 0.35, badge = '';
    if (r.added) { color = COLORS.added; opacity = 0.85; badge = '🆕'; }
    if ((r.traffic || 1) > 1) { color = COLORS.traffic; opacity = 0.9; glow = 0.8; badge = `🚦×${r.traffic}`; }
    if (r.closed) { color = COLORS.closed; opacity = 0.9; glow = 0.9; badge = '⛔'; }
    if (e.state === 'explored' && !r.closed) { opacity = 0.95; glow = 0.9; }
    if (e.state === 'dim') { opacity = 0.12; glow = 0.1; }
    if (e.state === 'hidden') { opacity = 0.0; glow = 0; badge = ''; }
    e.mat.color.set(color); e.mat.emissive.set(color);
    e.mat.opacity = opacity; e.mat.emissiveIntensity = glow;
    e.baseColor = color;
    e.badge.element.textContent = badge;
  }

  setRouteState(key, state) {
    const e = this.routes.get(key);
    if (!e || (e.state === 'hidden' && state !== 'show')) return;
    if (state === 'show') state = 'idle';
    e.state = state;
    this.refreshRoute(key);
  }

  flashRoute(key) {
    const e = this.routes.get(key);
    if (e) e.flash = 1;
  }

  /* Make the scene show exactly these routes with these closures/traffic (other routes are hidden). */
  syncRoutes(routes) {
    const live = new Map(routes.map((r) => [`${r.from}|${r.to}|${r.mode}`, r]));
    this.routes.forEach((e, k) => {
      const r = live.get(k);
      if (r) { Object.assign(e.r, { closed: !!r.closed, traffic: r.traffic || 1, added: !!r.added }); e.state = 'idle'; }
      else e.state = 'hidden';
      e.flash = 0;
      this.refreshRoute(k);
    });
  }

  resetRoutes() { this.routes.forEach((e, k) => { if (e.state !== 'hidden') e.state = 'idle'; e.flash = 0; this.refreshRoute(k); }); }

  updateRouteData(key, patch) {
    const e = this.routes.get(key);
    if (e) { Object.assign(e.r, patch); this.refreshRoute(key); }
  }

  // ------------------------------------------------------------------ overlays
  drawPath(legs, { color = COLORS.path, radius = 0.2, alt = false } = {}) {
    const group = new THREE.Group();
    for (const leg of legs) {
      const e = this.routes.get(leg.key);
      if (!e) continue;
      const mat = new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: alt ? 0.4 : 1.0, transparent: true, opacity: alt ? 0.45 : 0.95 });
      group.add(new THREE.Mesh(new THREE.TubeGeometry(e.curve, e.r.mode === 'flight' ? 40 : 2, alt ? radius * 0.6 : radius, 8, false), mat));
    }
    group.userData.alt = alt;
    this.overlay.add(group);
    return group;
  }

  clearOverlay() { while (this.overlay.children.length) this.overlay.remove(this.overlay.children[0]); }

  ripple(name, color = COLORS.frontier) {
    const n = this.nodes.get(name);
    if (!n) return;
    const m = new THREE.Mesh(new THREE.RingGeometry(0.6, 0.75, 32), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.9, side: THREE.DoubleSide }));
    m.rotation.x = -Math.PI / 2;
    m.position.set(n.pos.x, 0.05, n.pos.z);
    m.userData.t = 0;
    this.fx.add(m);
    this.ripples.push(m);
  }

  setBeams(items) {
    this.clearBeams();
    items.forEach((it, i) => {
      const n = this.nodes.get(it.name);
      if (!n) return;
      const h = 4 + it.strength * 10;
      const m = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.55, h, 16, 1, true),
        new THREE.MeshBasicMaterial({ color: it.color ?? COLORS.beam, transparent: true, opacity: 0.32, depthWrite: false, side: THREE.DoubleSide }));
      m.position.set(n.pos.x, h / 2, n.pos.z);
      m.userData = { delay: i * 0.12, t: 0, h };
      m.scale.y = 0.01;
      this.fx.add(m);
      this.beams.push(m);
    });
  }

  clearBeams() { this.beams.forEach((b) => this.fx.remove(b)); this.beams = []; }

  flyTo(name) {
    const n = this.nodes.get(name);
    if (n) this.flyTarget = n.pos.clone();
  }

  // ------------------------------------------------------------------ traveller
  startTraveller(legs, opts = {}) {
    this.stopTraveller();
    if (!legs.length) return;
    const body = new THREE.Group();
    const car = new THREE.Mesh(new THREE.BoxGeometry(0.9, 0.45, 0.5), new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0x2dd4bf, emissiveIntensity: 0.9 }));
    car.position.y = 0.35;
    const light = new THREE.PointLight(0x2dd4bf, 6, 6);
    light.position.y = 1;
    body.add(car, light);
    this.scene.add(body);
    const trailGeo = new THREE.BufferGeometry();
    trailGeo.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(3 * 600), 3));
    trailGeo.setDrawRange(0, 0);
    const trail = new THREE.Line(trailGeo, new THREE.LineBasicMaterial({ color: 0x2dd4bf, transparent: true, opacity: 0.9 }));
    this.scene.add(trail);
    this.traveller = { legs: legs.slice(), i: 0, t: 0, body, car, trail, trailN: 0, opts, paused: false, reverse: false };
    this.emit('legStart', this.traveller.legs[0], 0);
  }

  replaceRemaining(newLegs) {
    const tv = this.traveller;
    if (!tv) return;
    tv.legs = [...tv.legs.slice(0, tv.i + 1), ...newLegs];
  }

  turnBack() {
    /* drive the current leg backwards to its start town */
    const tv = this.traveller;
    if (!tv) return;
    const leg = tv.legs[tv.i];
    tv.legs = [...tv.legs.slice(0, tv.i), { ...leg, from: leg.to, to: leg.from, back: true }];
    tv.t = 1 - tv.t;
  }

  stopTraveller() {
    if (!this.traveller) return;
    this.scene.remove(this.traveller.body);
    this.scene.remove(this.traveller.trail);
    this.traveller = null;
  }

  stepTraveller(dt) {
    const tv = this.traveller;
    if (!tv || tv.paused) return;
    const leg = tv.legs[tv.i];
    const e = this.routes.get(leg.key);
    if (!e) { this.stopTraveller(); return; }
    const secondsPerHour = 0.9 / (tv.opts.speed ? tv.opts.speed() : 1);
    tv.t += dt / Math.max(0.25, leg.hours * secondsPerHour);
    const forward = e.r.from === leg.from;
    const tt = Math.min(1, tv.t);
    const p = e.curve.getPointAt(forward ? tt : 1 - tt);
    const q = e.curve.getPointAt(Math.min(1, Math.max(0, forward ? tt + 0.02 : 1 - tt - 0.02)));
    tv.body.position.copy(p);
    tv.body.lookAt(q.x, p.y, q.z);
    tv.car.rotation.y = Math.PI / 2;
    const arr = tv.trail.geometry.attributes.position.array;
    if (tv.trailN < 600) { arr.set([p.x, p.y + 0.1, p.z], tv.trailN * 3); tv.trailN++; tv.trail.geometry.setDrawRange(0, tv.trailN); tv.trail.geometry.attributes.position.needsUpdate = true; }
    this.emit('travelProgress', tv.i, tt);
    if (tv.t >= 1) {
      this.emit('legEnd', leg, tv.i);
      if (!this.traveller) return;                // a handler may stop or re-plan
      tv.i++;
      tv.t = 0;
      if (tv.i >= tv.legs.length) { this.emit('arrive', leg.to); this.stopTraveller(); return; }
      this.emit('legStart', tv.legs[tv.i], tv.i);
    }
  }

  // ------------------------------------------------------------------ interaction
  bindPointer() {
    const el = this.renderer.domElement;
    let down = null;
    el.addEventListener('pointerdown', (e) => { down = { x: e.clientX, y: e.clientY }; });
    el.addEventListener('pointerup', (e) => {
      if (!down || Math.hypot(e.clientX - down.x, e.clientY - down.y) > 5) { down = null; return; }
      down = null;
      const hit = this.pick(e);
      if (hit && hit.kind === 'node') this.emit('pickNode', hit.name);
      else if (hit && hit.kind === 'route') this.emit('pickRoute', hit.key, this.routes.get(hit.key).r);
    });
    el.addEventListener('pointermove', (e) => {
      const hit = this.pick(e);
      el.style.cursor = hit ? 'pointer' : 'grab';
      this.emit('hover', hit, e);
    });
    el.addEventListener('pointerleave', () => this.emit('hover', null));
  }

  pick(e) {
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.pointer.set(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const targets = [...[...this.nodes.values()].map((n) => n.mesh), ...[...this.routes.values()].filter((r) => r.state !== 'hidden').map((r) => r.hit)];
    const hits = this.raycaster.intersectObjects(targets, false);
    if (!hits.length) return null;
    const nodeHit = hits.find((h) => h.object.userData.kind === 'node');
    return (nodeHit || hits[0]).object.userData;
  }

  // ------------------------------------------------------------------ animation loop
  loop() {
    requestAnimationFrame(() => this.loop());
    const dt = Math.min(0.05, this.clock.getDelta());
    const time = this.clock.elapsedTime;
    this.nodes.forEach((n) => {
      n.h += (n.targetH - n.h) * Math.min(1, dt * 6);
      n.mesh.scale.y = Math.max(0.01, n.h);
      n.mesh.position.y = n.h / 2;
      n.color.lerp(n.target, Math.min(1, dt * 8));
      n.mat.color.copy(n.color); n.mat.emissive.copy(n.color);
      n.glow += (n.targetGlow - n.glow) * Math.min(1, dt * 8);
      n.mat.emissiveIntensity = n.glow;
      n.lbl.position.y = n.h + 0.6;
      if (n.ring.visible) { const s = 1 + 0.18 * Math.sin(time * 6); n.ring.scale.set(s, s, s); }
      if (n.marker) { n.marker.position.set(n.pos.x, n.h + 1.4 + Math.sin(time * 3 + n.marker.userData.bob) * 0.25, n.pos.z); n.marker.rotation.y = time * 1.5; }
    });
    this.routes.forEach((e) => {
      if (e.flash > 0) {
        e.flash = Math.max(0, e.flash - dt * 2.2);
        const c = new THREE.Color(e.baseColor).lerp(new THREE.Color(COLORS.relax), e.flash);
        e.mat.color.copy(c); e.mat.emissive.copy(c);
        e.mat.emissiveIntensity = 0.4 + e.flash * 1.6;
        if (e.flash === 0) this.refreshRoute(e.key);
      } else if ((e.r.traffic || 1) > 1 && !e.r.closed) {
        e.mat.emissiveIntensity = 0.5 + 0.4 * Math.sin(time * 5);
      }
    });
    this.ripples = this.ripples.filter((m) => {
      m.userData.t += dt;
      const s = 1 + m.userData.t * 4;
      m.scale.set(s, s, s);
      m.material.opacity = Math.max(0, 0.9 - m.userData.t * 1.4);
      if (m.material.opacity <= 0) { this.fx.remove(m); return false; }
      return true;
    });
    this.beams.forEach((b) => {
      b.userData.t += dt;
      const k = Math.min(1, Math.max(0, (b.userData.t - b.userData.delay) * 2.5));
      b.scale.y = Math.max(0.01, k);
      b.position.y = (b.userData.h * k) / 2;
      b.material.opacity = 0.22 + 0.12 * Math.sin(time * 3 + b.userData.delay * 10);
    });
    this.overlay.children.forEach((g) => g.children.forEach((m) => { if (!g.userData.alt) m.material.emissiveIntensity = 0.8 + 0.4 * Math.sin(time * 4); }));
    if (this.flyTarget) {
      this.controls.target.lerp(this.flyTarget, Math.min(1, dt * 3));
      if (this.controls.target.distanceTo(this.flyTarget) < 0.05) this.flyTarget = null;
    }
    this.stepTraveller(dt);
    this.controls.update();
    if (this.container && this.container.offsetParent !== null) {
      this.renderer.render(this.scene, this.camera);
      this.labels.render(this.scene, this.camera);
    }
  }
}
