/* core.js — перенос ядра dotgame (MAID/dotgame_maid.py) на JavaScript.
 * Правила: без оживления (REACTIVATION=false), самопожертвование сохраняется.
 * Геометрия: «X внутри контура» = планарное вложение немостовых рёбер +
 * обход граней. 1:1 по алгоритму с Python-версией (покрыта оракулом).
 */
"use strict";

const FIELD_RADIUS = 350;
const CONNECTION_RADIUS = 50;
const EPSILON = 1e-5;
const REACTIVATION = false;
const UNDO_LIMIT = 200;

const GEPS = 1e-9;
const ON_EPS = 1e-5;
const PAR_EPS = 1e-10;

const RED_C = "red";
const BLUE_C = "blue";

function otherColor(c) { return c === RED_C ? BLUE_C : RED_C; }

// ---------- геометрия ----------
function dist2(ax, ay, bx, by) { return (ax - bx) ** 2 + (ay - by) ** 2; }

function pointSegDist2(px, py, a, b) {
  const vx = b[0] - a[0], vy = b[1] - a[1];
  const L2 = vx * vx + vy * vy;
  if (L2 < GEPS) return dist2(px, py, a[0], a[1]);
  let t = ((px - a[0]) * vx + (py - a[1]) * vy) / L2;
  if (t < 0) return dist2(px, py, a[0], a[1]);
  if (t > 1) return dist2(px, py, b[0], b[1]);
  const cx = a[0] + t * vx, cy = a[1] + t * vy;
  return dist2(px, py, cx, cy);
}

function convexHull(pts) {
  // dedup + sort по (x, y)
  const seen = new Set();
  let P = [];
  for (const p of pts) {
    const k = p[0] + "," + p[1];
    if (!seen.has(k)) { seen.add(k); P.push([p[0], p[1]]); }
  }
  P.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  if (P.length <= 2) return P;
  const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower = [];
  for (const p of P) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop();
    lower.push(p);
  }
  const upper = [];
  for (let i = P.length - 1; i >= 0; i--) {
    const p = P[i];
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop();
    upper.push(p);
  }
  lower.pop(); upper.pop();
  return lower.concat(upper);
}

function lineKey(a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const L = Math.hypot(dx, dy);
  if (L < GEPS) return null;
  let nx = dy / L, ny = -dx / L;
  let c = -(nx * a[0] + ny * a[1]);
  if (nx < -GEPS || (Math.abs(nx) <= GEPS && ny < -GEPS)) { nx = -nx; ny = -ny; c = -c; }
  return [Math.round(nx * 1e9) / 1e9, Math.round(ny * 1e9) / 1e9, Math.round(c * 1e9) / 1e9];
}

function canonDir(a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const L = Math.hypot(dx, dy);
  let dxn = dx / L, dyn = dy / L;
  if (dxn < -GEPS || (Math.abs(dxn) <= GEPS && dyn < -GEPS)) { dxn = -dxn; dyn = -dyn; }
  return [dxn, dyn];
}

function mergeCollinear(segs) {
  const groups = new Map();
  for (const s of segs) {
    const k = lineKey(s[0], s[1]);
    if (k) {
      const key = k.join(",");
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(s);
    }
  }
  const out = [];
  for (const g of groups.values()) {
    if (g.length === 1) { out.push(g[0]); continue; }
    const p0 = g[0][0];
    const [dx, dy] = canonDir(g[0][0], g[0][1]);
    const intervals = [];
    for (const [a, b] of g) {
      const ta = (a[0] - p0[0]) * dx + (a[1] - p0[1]) * dy;
      const tb = (b[0] - p0[0]) * dx + (b[1] - p0[1]) * dy;
      intervals.push([Math.min(ta, tb), Math.max(ta, tb)]);
    }
    intervals.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    const merged = [intervals[0].slice()];
    for (let i = 1; i < intervals.length; i++) {
      const lo = intervals[i][0], hi = intervals[i][1];
      if (lo <= merged[merged.length - 1][1] + 1e-7) merged[merged.length - 1][1] = Math.max(merged[merged.length - 1][1], hi);
      else merged.push([lo, hi]);
    }
    for (const [lo, hi] of merged) {
      out.push([[p0[0] + lo * dx, p0[1] + lo * dy], [p0[0] + hi * dx, p0[1] + hi * dy]]);
    }
  }
  return out;
}

function segIntersectParams(a1, a2, b1, b2) {
  const dx1 = a2[0] - a1[0], dy1 = a2[1] - a1[1];
  const dx2 = b2[0] - b1[0], dy2 = b2[1] - b1[1];
  const den = dx1 * dy2 - dy1 * dx2;
  if (Math.abs(den) < GEPS) return null;
  const dpx = b1[0] - a1[0], dpy = b1[1] - a1[1];
  const s = (dpx * dy2 - dpy * dx2) / den;
  const t = (dpx * dy1 - dpy * dx1) / den;
  return [s, t];
}

function planarize(segs) {
  const n = segs.length;
  const splits = Array.from({ length: n }, () => []);
  for (let i = 0; i < n; i++) {
    const a1 = segs[i][0], a2 = segs[i][1];
    for (let j = i + 1; j < n; j++) {
      const b1 = segs[j][0], b2 = segs[j][1];
      if (Math.max(Math.min(a1[0], a2[0]), Math.min(b1[0], b2[0])) >
          Math.min(Math.max(a1[0], a2[0]), Math.max(b1[0], b2[0])) + 1e-7) continue;
      if (Math.max(Math.min(a1[1], a2[1]), Math.min(b1[1], b2[1])) >
          Math.min(Math.max(a1[1], a2[1]), Math.max(b1[1], b2[1])) + 1e-7) continue;
      const st = segIntersectParams(a1, a2, b1, b2);
      if (!st) continue;
      const s = st[0], t = st[1];
      if (0 < s && s < 1 && 0 < t && t < 1) { splits[i].push(s); splits[j].push(t); }
      else if (Math.abs(s) < 1e-7 && 1e-7 < t && t < 1 - 1e-7) splits[j].push(t);
      else if (Math.abs(s - 1) < 1e-7 && 1e-7 < t && t < 1 - 1e-7) splits[j].push(t);
      else if (Math.abs(t) < 1e-7 && 1e-7 < s && s < 1 - 1e-7) splits[i].push(s);
      else if (Math.abs(t - 1) < 1e-7 && 1e-7 < s && s < 1 - 1e-7) splits[i].push(s);
    }
  }
  const vmap = new Map();
  const verts = [];
  function vid(p) {
    const k = Math.round(p[0] * 1e8) / 1e8 + "," + Math.round(p[1] * 1e8) / 1e8;
    if (!vmap.has(k)) { vmap.set(k, verts.length); verts.push(p); }
    return vmap.get(k);
  }
  const pslg = [];
  for (let i = 0; i < n; i++) {
    const a1 = segs[i][0], a2 = segs[i][1];
    const L = Math.hypot(a2[0] - a1[0], a2[1] - a1[1]);
    if (L < GEPS) continue;
    const dx = (a2[0] - a1[0]) / L, dy = (a2[1] - a1[1]) / L;
    const paramSet = new Set([0.0, 1.0]);
    for (const s of splits[i]) if (1e-9 < s && s < 1 - 1e-9) paramSet.add(s);
    const params = [...paramSet].sort((a, b) => a - b);
    for (let k = 0; k < params.length - 1; k++) {
      if (params[k + 1] - params[k] < 1e-9) continue;
      const pa = [a1[0] + dx * L * params[k], a1[1] + dy * L * params[k]];
      const pb = [a1[0] + dx * L * params[k + 1], a1[1] + dy * L * params[k + 1]];
      pslg.push([vid(pa), vid(pb)]);
    }
  }
  return [verts, pslg];
}

function findBridges(n, edges) {
  const adj = Array.from({ length: n }, () => []);
  edges.forEach((e, ei) => { adj[e[0]].push([e[1], ei]); adj[e[1]].push([e[0], ei]); });
  const disc = new Array(n).fill(-1);
  const low = new Array(n).fill(0);
  const bridges = new Set();
  let timer = 0;
  function dfs(u, pe) {
    disc[u] = low[u] = timer++;
    for (const [v, ei] of adj[u]) {
      if (ei === pe) continue;
      if (disc[v] === -1) {
        dfs(v, ei);
        low[u] = Math.min(low[u], low[v]);
        if (low[v] > disc[u]) bridges.add(ei);
      } else {
        low[u] = Math.min(low[u], disc[v]);
      }
    }
  }
  for (let i = 0; i < n; i++) if (disc[i] === -1) dfs(i, -1);
  return bridges;
}

// ---------- структура цвета ----------
class ColorStructure {
  constructor() { this.reset(); }
  reset() {
    this.pts = []; this.n = 0; this.edges = []; this.nbEdges = [];
    this.segs = []; this.empty = true; this.verts = []; this.pslg = [];
    this.faceOfDir = new Map(); this.outerFaces = new Set(); this.hull = [];
  }
  rebuild(points, radius) {
    this.pts = points.map(p => [p.x, p.y]);
    this.n = this.pts.length;
    this.edges = [];
    if (this.n >= 3) {
      const R2 = (radius + ON_EPS) ** 2;
      for (let i = 0; i < this.n; i++) {
        const xi = this.pts[i][0], yi = this.pts[i][1];
        const onBi = isOnBoundary(xi, yi);
        for (let j = i + 1; j < this.n; j++) {
          const xj = this.pts[j][0], yj = this.pts[j][1];
          if ((xi - xj) ** 2 + (yi - yj) ** 2 <= R2 &&
              !(onBi && isOnBoundary(xj, yj))) this.edges.push([i, j]);
        }
      }
    }
    this.nbEdges = [];
    if (this.edges.length) {
      const bridges = findBridges(this.n, this.edges);
      this.nbEdges = this.edges.filter((e, i) => !bridges.has(i));
    }
    if (!this.nbEdges.length) {
      this.empty = true; this.segs = []; this.verts = []; this.pslg = [];
      this.faceOfDir = new Map(); this.outerFaces = new Set();
      this.hull = convexHull(this.pts);
      return;
    }
    const segs = this.nbEdges.map(([u, v]) => [this.pts[u], this.pts[v]]);
    const merged = mergeCollinear(segs);
    const [verts, pslg] = planarize(merged);
    if (!pslg.length) { this.empty = true; return; }
    this.empty = false;
    this.verts = verts; this.pslg = pslg;
    // обход граней
    const ang = Array.from({ length: verts.length }, () => []);
    for (const [u, v] of pslg) { ang[u].push(v); ang[v].push(u); }
    const idx = Array.from({ length: verts.length }, () => ({}));
    for (let u = 0; u < verts.length; u++) {
      if (!ang[u].length) continue;
      const items = [];
      for (const v of ang[u]) {
        const dx = verts[v][0] - verts[u][0], dy = verts[v][1] - verts[u][1];
        items.push([Math.atan2(dy, dx), v]);
      }
      items.sort((a, b) => a[0] - b[0]);
      ang[u] = items.map(it => it[1]);
      idx[u] = {};
      ang[u].forEach((v, i) => { idx[u][v] = i; });
    }
    function nextDir(u, v) {
      const i = idx[v][u];
      const w = ang[v][(i - 1 + ang[v].length) % ang[v].length];
      return [v, w];
    }
    const faceOfDir = new Map();
    const faces = [];
    for (const [u, v] of pslg) {
      for (const d of [[u, v], [v, u]]) {
        const key = d[0] + "," + d[1];
        if (faceOfDir.has(key)) continue;
        let cur = d;
        const poly = [verts[d[0]], verts[d[1]]];
        while (true) {
          faceOfDir.set(cur[0] + "," + cur[1], faces.length);
          cur = nextDir(cur[0], cur[1]);
          poly.push(verts[cur[1]]);
          if (cur[0] === d[0] && cur[1] === d[1]) break;
        }
        faces.push(poly);
      }
    }
    const outer = new Set();
    faces.forEach((poly, fi) => {
      let a = 0.0;
      const m = poly.length;
      for (let i = 0; i < m; i++) {
        const x1 = poly[i][0], y1 = poly[i][1];
        const x2 = poly[(i + 1) % m][0], y2 = poly[(i + 1) % m][1];
        a += x1 * y2 - x2 * y1;
      }
      if (a < 0) outer.add(fi);
    });
    this.faceOfDir = faceOfDir;
    this.outerFaces = outer;
    this.hull = convexHull(this.pts);
    this.segs = this.nbEdges.map(([u, v]) => [this.pts[u], this.pts[v]]);
  }
  onEdge(X) {
    for (const [a, b] of this.segs) {
      if (pointSegDist2(X[0], X[1], a, b) < ON_EPS * ON_EPS) return true;
    }
    return false;
  }
  outsideHull(X) {
    const h = this.hull, n = h.length;
    if (n === 0) return true;
    if (n === 1) return dist2(X[0], X[1], h[0][0], h[0][1]) > ON_EPS * ON_EPS;
    if (n === 2) return pointSegDist2(X[0], X[1], h[0], h[1]) > ON_EPS * ON_EPS;
    for (let i = 0; i < n; i++) {
      const a = h[i], b = h[(i + 1) % n];
      const cr = (b[0] - a[0]) * (X[1] - a[1]) - (b[1] - a[1]) * (X[0] - a[0]);
      if (cr < -ON_EPS) return true;
    }
    return false;
  }
  query(X) {
    if (this.empty) return false;
    if (this.onEdge(X)) return true;
    if (this.outsideHull(X)) return false;
    const ts = [0.0, 1e-9, -1e-9, 1e-8, -1e-8, 1e-7, -1e-7, 1e-6, -1e-6];
    for (const t of ts) {
      let bad = false;
      for (const v of this.verts) {
        const rx = v[0] - X[0], ry = v[1] - X[1];
        if (rx <= 0) continue;
        if (Math.abs(rx * t - ry) < 1e-9 * Math.hypot(rx, ry)) { bad = true; break; }
      }
      if (bad) continue;
      let best = null;
      for (const [vi, vj] of this.pslg) {
        const pa = this.verts[vi], pb = this.verts[vj];
        const ddx = pb[0] - pa[0], ddy = pb[1] - pa[1];
        const den = 1.0 * ddy - t * ddx;
        if (Math.abs(den) < PAR_EPS) continue;
        const rx = pa[0] - X[0], ry = pa[1] - X[1];
        const s = (rx * ddy - ry * ddx) / den;
        const u = (rx * t - ry) / den;
        if (s > 1e-9 && 0 < u && u < 1) {
          if (best === null || s < best[0]) best = [s, vi, vj];
        }
      }
      if (best === null) return false;
      const s = best[0], vi = best[1], vj = best[2];
      const pa = this.verts[vi], pb = this.verts[vj];
      const e = 1e-9;
      const Q = [X[0] + s - e, X[1] + s * t - e * t];
      const side = (pb[0] - pa[0]) * (Q[1] - pa[1]) - (pb[1] - pa[1]) * (Q[0] - pa[0]);
      const d0 = side > 0 ? [vi, vj] : [vj, vi];
      return !this.outerFaces.has(this.faceOfDir.get(d0[0] + "," + d0[1]));
    }
    throw new Error("no generic ray found");
  }
}

// Точка на границе карты (окружность поля) — допуск покрывает float-ошибку снапа
const BOUNDARY_EPS = 1e-6;
function isOnBoundary(x, y) { return Math.abs(Math.hypot(x, y) - FIELD_RADIUS) <= BOUNDARY_EPS; }
// Соединяются ли две точки: расстояние ≤ R, но две точки НА ГРАНИЦЕ КАРТЫ
// НЕ соединяются (правило Android-версии)
function pointsConnect(a, b) {
  const dx = a.x - b.x, dy = a.y - b.y;
  if (dx * dx + dy * dy > (CONNECTION_RADIUS + ON_EPS) ** 2) return false;
  if (isOnBoundary(a.x, a.y) && isOnBoundary(b.x, b.y)) return false;
  return true;
}

// ---------- логика игры ----------
class Point {
  constructor(x, y, color, active = true, pid = 0) {
    this.x = x; this.y = y; this.color = color; this.active = active; this.id = pid;
  }
  pos() { return [this.x, this.y]; }
  snapshot() { return [this.id, this.x, this.y, this.color, this.active]; }
  static fromSnapshot(t) { return new Point(t[1], t[2], t[3], t[4], t[0]); }
}

class MoveResult {
  constructor(point, capturedAtBirth, newlyCaptured, reactivated, lastContour = null, passed = false, gameOver = false, winner = null) {
    this.point = point; this.capturedAtBirth = capturedAtBirth;
    this.newlyCaptured = newlyCaptured; this.reactivated = reactivated;
    this.lastContour = lastContour; this.passed = passed;
    this.gameOver = gameOver; this.winner = winner;
  }
}

class Game {
  constructor(maxPoints = 0, reactivation = REACTIVATION) {
    this.maxPoints = maxPoints;
    this.reactivation = reactivation;
    this.points = [];
    this.score = { [RED_C]: 0, [BLUE_C]: 0 };
    this.current = RED_C;
    this.history = [];
    this.struct = { [RED_C]: new ColorStructure(), [BLUE_C]: new ColorStructure() };
    this.structDirty = { [RED_C]: true, [BLUE_C]: true };
    this._nextId = 0;
  }
  pointsOf(color) { return this.points.filter(p => p.color === color); }
  activeOf(color) { return this.points.filter(p => p.color === color && p.active); }
  countOf(color) { return this.pointsOf(color).length; }
  atLimit(color) { return this.maxPoints > 0 && this.countOf(color) >= this.maxPoints; }
  _ensureStruct(color) {
    const st = this.struct[color];
    if (this.structDirty[color]) {
      st.rebuild(this.activeOf(color), CONNECTION_RADIUS);
      this.structDirty[color] = false;
    }
  }
  _invalidate(color) { this.structDirty[color] = true; }
  _inSomeContour(color, x, y) { this._ensureStruct(color); return this.struct[color].query([x, y]); }

  place(x, y) {
    if (this.atLimit(this.current)) {
      const ended = this.atLimit(RED_C) && this.atLimit(BLUE_C);
      return new MoveResult(null, false, [], [], null, true, ended, ended ? this._winner() : null);
    }
    const snap = this._snapshot();
    const O = otherColor(this.current);
    this._ensureStruct(O);
    const captured = this.struct[O].query([x, y]);
    const p = new Point(x, y, this.current, !captured, this._nextId);
    this._nextId++;
    this.points.push(p);
    if (captured) this.score[O]++;
    this._invalidate(this.current);
    const [newly, reactivated] = this._cascade();
    const contour = this._findCaptureContour(p, newly, captured);
    const prev = this.current;
    this.current = O;
    let passed = false;
    if (this.atLimit(this.current)) { this.current = prev; passed = true; }
    let gameOver = false, winner = null;
    if (this.atLimit(RED_C) && this.atLimit(BLUE_C)) { gameOver = true; winner = this._winner(); }
    this.history.push(snap);
    if (this.history.length > UNDO_LIMIT) this.history.shift();
    return new MoveResult(p, captured, newly, reactivated, contour, passed, gameOver, winner);
  }

  _cascade() {
    const moved = this.current, opp = otherColor(moved);
    const newly = [], reactivated = [];
    if (!this.reactivation) {
      this._ensureStruct(moved);
      const st = this.struct[moved];
      for (const p of this.pointsOf(opp)) {
        if (p.active && st.query(p.pos())) {
          p.active = false; this.score[moved]++; newly.push(p);
        }
      }
      if (newly.length) this._invalidate(opp);
      return [newly, reactivated];
    }
    let changed = true;
    while (changed) {
      changed = false;
      for (const C of [moved, opp]) {
        const OC = otherColor(C);
        this._ensureStruct(OC);
        const st = this.struct[OC];
        for (const p of this.pointsOf(C)) {
          const want = !st.query(p.pos());
          if (p.active === want) continue;
          p.active = want; changed = true; this._invalidate(C);
          if (want) reactivated.push(p);
          else { this.score[OC]++; newly.push(p); }
        }
      }
    }
    return [newly, reactivated];
  }

  _findCaptureContour(newPoint, newlyCaptured, capturedAtBirth) {
    let targets = newlyCaptured;
    if (capturedAtBirth && !targets.length) targets = [newPoint];
    if (!targets.length) return null;
    const C = this.current;
    let own = this.activeOf(C);
    if (!own.includes(newPoint) && newPoint.active) own = own.concat([newPoint]);
    const R2 = (CONNECTION_RADIUS + ON_EPS) ** 2;
    const idx = new Map();
    own.forEach((p, i) => idx.set(p, i));
    const ni = idx.get(newPoint);
    if (ni === undefined) return null;
    const adj = Array.from({ length: own.length }, () => []);
    for (let i = 0; i < own.length; i++) {
      const a = own[i];
      const onBi = isOnBoundary(a.x, a.y);
      for (let j = i + 1; j < own.length; j++) {
        const b = own[j];
        const dx = a.x - b.x, dy = a.y - b.y;
        if (dx * dx + dy * dy <= R2 &&
            !(onBi && isOnBoundary(b.x, b.y))) { adj[i].push(j); adj[j].push(i); }
      }
    }
    const neighbors = adj[ni];
    if (neighbors.length < 2) return null;
    let budget = 30000;
    let found = null;
    function polyOf(path, b) {
      // path: индексы [a,...,cur]; цикл = new -> a -> ... -> cur -> b -> new
      return [newPoint].concat(path.map(i => own[i])).concat([own[b]]);
    }
    function pip(poly, pt) {
      const n = poly.length;
      for (let i = 0; i < n; i++) {
        const a = poly[i], b = poly[(i + 1) % n];
        if (pointSegDist2(pt.x, pt.y, [a.x, a.y], [b.x, b.y]) < ON_EPS * ON_EPS) return true;
      }
      const xs = poly.map(q => q.x), ys = poly.map(q => q.y);
      let inside = false;
      let j = n - 1;
      for (let i = 0; i < n; i++) {
        const yi = ys[i], yj = ys[j];
        if ((yi > pt.y) !== (yj > pt.y)) {
          const xints = (xs[j] - xs[i]) * (pt.y - yi) / (yj - yi) + xs[i];
          if (pt.x < xints) inside = !inside;
        }
        j = i;
      }
      return inside;
    }
    for (const a of neighbors) {
      for (const b of neighbors) {
        if (a === b) continue;
        const inpath = new Set([ni, a]);
        const dfs = (cur, path) => {
          if (budget <= 0 || found !== null) return;
          budget--;
          for (const nb of adj[cur]) {
            if (nb === b && path.length >= 1) {
              const cyc = polyOf(path, b);
              for (const t of targets) if (pip(cyc, t)) { found = cyc; return; }
            }
            if (!inpath.has(nb) && nb !== ni) {
              inpath.add(nb); path.push(nb);
              dfs(nb, path);
              path.pop(); inpath.delete(nb);
            }
            if (found !== null) return;
          }
        };
        dfs(a, [a]);
        if (found !== null) break;
      }
      if (found !== null) break;
    }
    return found;
  }

  _winner() {
    if (this.score[RED_C] > this.score[BLUE_C]) return RED_C;
    if (this.score[BLUE_C] > this.score[RED_C]) return BLUE_C;
    return null;
  }
  _snapshot() {
    return [this.points.map(p => p.snapshot()), { ...this.score }, this.current, this._nextId];
  }
  undo() {
    if (!this.history.length) return false;
    const [pts, score, current, nextId] = this.history.pop();
    this.points = pts.map(t => Point.fromSnapshot(t));
    this.score = score; this.current = current; this._nextId = nextId;
    this.structDirty = { [RED_C]: true, [BLUE_C]: true };
    return true;
  }
  reset(maxPoints = null) {
    const mp = maxPoints !== null ? maxPoints : this.maxPoints;
    this.constructor.call(this, mp, this.reactivation);
  }
  clone() {
    const g = new Game(this.maxPoints, this.reactivation);
    g.points = this.points.map(p => Point.fromSnapshot(p.snapshot()));
    g.score = { ...this.score };
    g.current = this.current;
    g._nextId = this._nextId;
    return g;
  }
}

// ---------- хелперы ----------
function isInsideField(x, y) { return Math.hypot(x, y) <= FIELD_RADIUS + EPSILON; }
function distanceP(p1, p2) { return Math.hypot(p1.x - p2.x, p1.y - p2.y); }

function intersectCircleCircle(c1, c2) {
  const [x0, y0] = c1.center, r0 = c1.radius;
  const [x1, y1] = c2.center, r1 = c2.radius;
  const d = Math.hypot(x1 - x0, y1 - y0);
  if (d > r0 + r1 || d < Math.abs(r0 - r1) || d < EPSILON) return [];
  const a = (r0 * r0 - r1 * r1 + d * d) / (2 * d);
  const h = Math.sqrt(Math.max(0, r0 * r0 - a * a));
  const x2 = x0 + a * (x1 - x0) / d, y2 = y0 + a * (y1 - y0) / d;
  const rx = -h * (y1 - y0) / d, ry = h * (x1 - x0) / d;
  return [[x2 + rx, y2 + ry], [x2 - rx, y2 - ry]];
}

// Кандидатные позиции для автоснапа (та же геометрия, что у ИИ/привязки).
function snapCandidates(game) {
  const CR = CONNECTION_RADIUS;
  const pts = game.points;
  const act = pts.filter(p => p.active);
  const cands = [];
  const seen = new Set();
  const minDist = 1.0;
  function add(x, y) {
    if (Math.hypot(x, y) > FIELD_RADIUS - 1.0) return;
    const k = Math.round(x * 1000) / 1000 + "," + Math.round(y * 1000) / 1000;
    if (seen.has(k)) return;
    for (const p of pts) if ((p.x - x) ** 2 + (p.y - y) ** 2 < minDist * minDist) return;
    seen.add(k);
    cands.push([x, y]);
  }
  for (let i = 0; i < act.length; i++) {
    const a = act[i];
    for (let j = i + 1; j < act.length; j++) {
      const b = act[j];
      for (const [x, y] of intersectCircleCircle({ center: [a.x, a.y], radius: CR }, { center: [b.x, b.y], radius: CR })) add(x, y);
      add((a.x + b.x) / 2, (a.y + b.y) / 2);
      const d = Math.hypot(b.x - a.x, b.y - a.y);
      if (d > EPSILON) add(b.x + (b.x - a.x) / d * CR, b.y + (b.y - a.y) / d * CR);
    }
  }
  return cands;
}

// Экспорт для UI (и для тестов в браузере).
if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    FIELD_RADIUS, CONNECTION_RADIUS, EPSILON, RED_C, BLUE_C,
    otherColor, ColorStructure, Point, MoveResult, Game,
    isInsideField, distanceP, intersectCircleCircle, snapCandidates,
    isOnBoundary, pointsConnect,
    convexHull, pointSegDist2,
  };
}
if (typeof window !== "undefined") {
  window.DotCore = {
    FIELD_RADIUS, CONNECTION_RADIUS, EPSILON, RED_C, BLUE_C,
    otherColor, ColorStructure, Point, MoveResult, Game,
    isInsideField, distanceP, intersectCircleCircle, snapCandidates,
    isOnBoundary, pointsConnect,
  };
}
