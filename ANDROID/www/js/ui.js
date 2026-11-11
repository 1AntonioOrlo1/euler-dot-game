/* ui.js — Canvas-рендеринг + сенсорное управление для dotgame (Android/PWA).
 *
 * Универсальный механизм постановки (без выделения линий):
 *   - Тап (1-й) — призрак. Он сам прилипает и подсвечивается:
 *       ЗЕЛЁНЫЙ  — на пересечении СВОЕЙ линии/круга со своей, чужой линией
 *                  или с границей карты (точное пересечение).
 *       ЖЁЛТЫЙ   — на СВОЕЙ линии/круге в любом месте, или на границе карты.
 *       обычный  — свободная постановка (цвет текущего игрока).
 *   - Тап (2-й) рядом с призраком — подтвердить; далеко — переместить.
 *   - Чисто чужие пересечения (без своей линии) ставить нельзя.
 *
 * Жесты:
 *   - 1 палец: тап / перетаскивание (панорама).
 *   - 2 пальца: щипок = зум к пальцам + панорама; два быстрых тапа = undo.
 *   - Кнопки: ↩ undo, ⟲ reset, ? help.
 */
"use strict";
(function () {
  const C = window.DotCore;
  const canvas = document.getElementById("game");
  const ctx = canvas.getContext("2d");
  const stage = document.getElementById("stage");

  // ---- цвета ----
  const COL = {
    bg: "#ffffff",
    field: "#f7f7f7",
    fieldEdge: "#222222",
    red: "#dc2828",
    blue: "#2850dc",
    redEdge: "rgba(220,40,40,0.55)",
    blueEdge: "rgba(40,80,220,0.55)",
    redZone: "rgba(220,40,40,0.16)",
    blueZone: "rgba(40,80,220,0.16)",
    inactiveRed: "#b9a0a0",
    inactiveBlue: "#a0a8c0",
    ghostRing: "rgba(0,0,0,0.20)",
    contour: "#00aa3c",
    warn: "#e08a00",
    select: "#f0c800",   // жёлтый — на своей линии / границе карты
    green: "#00aa3c",    // зелёный — пересечение
  };

  const MIN_SCALE = 0.15, MAX_SCALE = 100;  // сильно увеличен макс. зум
  const DOT_R = 5;        // фиксированный радиус точки на экране (px)
  const GHOST_R = 6;
  const CONFIRM_PX = 22;  // радиус подтверждения призрака (px)
  const SNAP_PX = 14;     // порог снапа к линиям/пересечениям (px)

  // ---- камера ----
  let scale = 1, offsetX = 0, offsetY = 0;
  let W = 0, H = 0, DPR = 1;

  function resize() {
    DPR = window.devicePixelRatio || 1;
    const r = stage.getBoundingClientRect();
    W = r.width; H = r.height;
    canvas.width = Math.round(W * DPR);
    canvas.height = Math.round(H * DPR);
    canvas.style.width = W + "px";
    canvas.style.height = H + "px";
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  }
  function fitField() {
    scale = Math.min(W, H) / (2 * C.FIELD_RADIUS * 1.08);
    offsetX = 0; offsetY = 0;
  }
  function g2s(gx, gy) { return [W / 2 + offsetX + gx * scale, H / 2 + offsetY - gy * scale]; }
  function s2g(sx, sy) { return [(sx - W / 2 - offsetX) / scale, -(sy - H / 2 - offsetY) / scale]; }

  // ---- состояние игры ----
  let game = new C.Game();
  let flashes = [];
  let lastContour = null, lastContourT = 0, lastContourColor = COL.red;
  let ghost = null;
  let gameOverShown = false;
  const now = () => performance.now() / 1000;

  // ---- toast ----
  const toastEl = document.getElementById("toast");
  let toastTimer = null;
  function say(msg, ms = 1800) {
    toastEl.textContent = msg;
    toastEl.classList.add("show");
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toastEl.classList.remove("show"), ms);
  }

  // ---- HUD ----
  function updateHUD() {
    document.getElementById("score-red").textContent = game.score[C.RED_C];
    document.getElementById("score-blue").textContent = game.score[C.BLUE_C];
    const turn = document.getElementById("turn");
    const isRed = game.current === C.RED_C;
    turn.className = "turn " + (isRed ? "red" : "blue");
    document.getElementById("turn-text").textContent = isRed ? "Красные" : "Синие";
  }

  // ---- геометрия кривых ----
  function distPtSeg(px, py, ax, ay, bx, by) {
    const vx = bx - ax, vy = by - ay;
    const wx = px - ax, wy = py - ay;
    const c1 = vx * wx + vy * wy;
    if (c1 <= 0) return Math.hypot(px - ax, py - ay);
    const c2 = vx * vx + vy * vy;
    if (c2 <= c1) return Math.hypot(px - bx, py - by);
    const t = c1 / c2;
    return Math.hypot(px - (ax + t * vx), py - (ay + t * vy));
  }
  function projectPtSeg(px, py, ax, ay, bx, by) {
    const vx = bx - ax, vy = by - ay;
    const c1 = vx * (px - ax) + vy * (py - ay);
    if (c1 <= 0) return [ax, ay];
    const c2 = vx * vx + vy * vy;
    if (c2 <= c1) return [bx, by];
    const t = c1 / c2;
    return [ax + t * vx, ay + t * vy];
  }
  function intersectSegSeg(s1, s2) {
    const [ax, ay] = s1.p1, [bx, by] = s1.p2, [cx, cy] = s2.p1, [dx, dy] = s2.p2;
    const den = (ax - bx) * (cy - dy) - (ay - by) * (cx - dx);
    if (Math.abs(den) < C.EPSILON) return [];
    const t = ((ax - cx) * (cy - dy) - (ay - cy) * (cx - dx)) / den;
    const u = ((ax - cx) * (ay - by) - (ay - cy) * (ax - bx)) / den;
    if (-C.EPSILON <= t && t <= 1 + C.EPSILON && -C.EPSILON <= u && u <= 1 + C.EPSILON)
      return [[ax + t * (bx - ax), ay + t * (by - ay)]];
    return [];
  }
  function intersectCircSeg(circle, seg) {
    const [cx, cy] = circle.center, r = circle.radius;
    const [ax, ay] = seg.p1, [bx, by] = seg.p2;
    const dx = bx - ax, dy = by - ay;
    const fx = ax - cx, fy = ay - cy;
    const a = dx * dx + dy * dy;
    const b = 2 * (fx * dx + fy * dy);
    const c = fx * fx + fy * fy - r * r;
    let disc = b * b - 4 * a * c;
    if (disc < 0) return [];
    disc = Math.sqrt(disc);
    const t1 = (-b + disc) / (2 * a), t2 = (-b - disc) / (2 * a);
    const pts = [];
    if (-C.EPSILON <= t1 && t1 <= 1 + C.EPSILON) pts.push([ax + t1 * dx, ay + t1 * dy]);
    if (-C.EPSILON <= t2 && t2 <= 1 + C.EPSILON) pts.push([ax + t2 * dx, ay + t2 * dy]);
    return pts;
  }
  function computeIntersections(A, B) {
    if (A.type === "circle" && B.type === "circle") return C.intersectCircleCircle(A, B);
    if (A.type === "circle" && B.type === "segment") return intersectCircSeg(A, B);
    if (A.type === "segment" && B.type === "circle") return intersectCircSeg(B, A);
    if (A.type === "segment" && B.type === "segment") return intersectSegSeg(A, B);
    return [];
  }

  // ---- кривые ----
  function edgePairs(color) {
    const act = game.activeOf(color);
    const pairs = [];
    const R2 = (C.CONNECTION_RADIUS + C.EPSILON) ** 2;
    for (let i = 0; i < act.length; i++)
      for (let j = i + 1; j < act.length; j++)
        if ((act[i].x - act[j].x) ** 2 + (act[i].y - act[j].y) ** 2 <= R2) pairs.push([act[i], act[j]]);
    return pairs;
  }
  // Все кривые с флагом own (своя ли для текущего игрока)
  function getCurves() {
    const P = game.current, O = C.otherColor(P);
    const curves = [];
    for (const [a, b] of edgePairs(P)) curves.push({ type: "segment", p1: [a.x, a.y], p2: [b.x, b.y], own: true });
    for (const p of game.activeOf(P)) curves.push({ type: "circle", center: [p.x, p.y], radius: C.CONNECTION_RADIUS, own: true });
    for (const [a, b] of edgePairs(O)) curves.push({ type: "segment", p1: [a.x, a.y], p2: [b.x, b.y], own: false });
    for (const p of game.activeOf(O)) curves.push({ type: "circle", center: [p.x, p.y], radius: C.CONNECTION_RADIUS, own: false });
    curves.push({ type: "circle", center: [0, 0], radius: C.FIELD_RADIUS, own: false }); // граница карты
    return curves;
  }
  // Зелёные пересечения: хотя бы одна кривая — своя
  function getGreenIntersections() {
    const curves = getCurves();
    const pts = [];
    const minD = Math.max(C.EPSILON, 6 / scale);
    for (let i = 0; i < curves.length; i++) {
      for (let j = i + 1; j < curves.length; j++) {
        if (!curves[i].own && !curves[j].own) continue; // чисто чужие — не ставим
        for (const pt of computeIntersections(curves[i], curves[j])) {
          if (!C.isInsideField(pt[0], pt[1])) continue;
          if (game.points.some(p => Math.hypot(p.x - pt[0], p.y - pt[1]) < minD)) continue;
          if (pts.some(u => Math.hypot(u[0] - pt[0], u[1] - pt[1]) < C.EPSILON)) continue;
          pts.push(pt);
        }
      }
    }
    return pts;
  }
  // Жёлтые кривые: свои линии/круги + граница карты
  function getYellowCurves() {
    const P = game.current;
    const curves = [];
    for (const [a, b] of edgePairs(P)) curves.push({ type: "segment", p1: [a.x, a.y], p2: [b.x, b.y] });
    for (const p of game.activeOf(P)) curves.push({ type: "circle", center: [p.x, p.y], radius: C.CONNECTION_RADIUS });
    curves.push({ type: "circle", center: [0, 0], radius: C.FIELD_RADIUS });
    return curves;
  }
  // Захватится ли точка в этой позиции (самопожертвование)
  function checkCaptured(pos) {
    const opp = C.otherColor(game.current);
    game._ensureStruct(opp);
    try { return game.struct[opp].query(pos); } catch (e) { return false; }
  }

  // ---- призрак (универсальный механизм) ----
  function computeGhost(gx, gy) {
    if (!C.isInsideField(gx, gy)) return null;
    const minD = Math.max(C.EPSILON, 6 / scale);
    for (const p of game.points)
      if (Math.hypot(p.x - gx, p.y - gy) < minD) return null;
    const th = SNAP_PX / scale;
    // 1) зелёное пересечение (ближайшее в пределах порога)
    let bestG = null, bestGD = th;
    for (const pt of getGreenIntersections()) {
      const d = Math.hypot(pt[0] - gx, pt[1] - gy);
      if (d < bestGD) { bestGD = d; bestG = pt; }
    }
    if (bestG) return { x: bestG[0], y: bestG[1], kind: "green", captured: checkCaptured(bestG) };
    // 2) жёлтая кривая (проекция на ближайшую свою линию/круг/границу)
    let bestY = null, bestYD = th;
    for (const curve of getYellowCurves()) {
      let proj, d;
      if (curve.type === "circle") {
        const dc = Math.hypot(gx - curve.center[0], gy - curve.center[1]);
        d = Math.abs(dc - curve.radius);
        if (dc < C.EPSILON) proj = [curve.center[0] + curve.radius, curve.center[1]];
        else { const s = curve.radius / dc; proj = [curve.center[0] + (gx - curve.center[0]) * s, curve.center[1] + (gy - curve.center[1]) * s]; }
      } else {
        proj = projectPtSeg(gx, gy, curve.p1[0], curve.p1[1], curve.p2[0], curve.p2[1]);
        d = Math.hypot(gx - proj[0], gy - proj[1]);
      }
      if (d < bestYD) { bestYD = d; bestY = proj; }
    }
    if (bestY) return { x: bestY[0], y: bestY[1], kind: "yellow", captured: checkCaptured(bestY) };
    // 3) свободная постановка
    return { x: gx, y: gy, kind: "free", captured: checkCaptured([gx, gy]) };
  }

  // ---- постановка ----
  function doPlace(x, y) {
    const res = game.place(x, y);
    if (res.point === null) { if (res.passed) say("Лимит точек — ход переходит."); return; }
    flashes.push({ point: res.point, type: "birth", t0: now() });
    for (const p of res.newlyCaptured) flashes.push({ point: p, type: "captured", t0: now() });
    for (const p of res.reactivated) flashes.push({ point: p, type: "reactivated", t0: now() });
    if (res.lastContour) {
      lastContour = res.lastContour; lastContourT = now();
      lastContourColor = res.point.color === C.RED_C ? COL.red : COL.blue;
    }
    if (res.gameOver) showGameOver(res.winner);
    ghost = null;
    updateHUD();
  }

  // ---- тап (универсальный механизм) ----
  function handleTap(sx, sy) {
    if (gameOverShown) return;
    const [gx, gy] = s2g(sx, sy);
    if (ghost !== null) {
      const [gsx, gsy] = g2s(ghost.x, ghost.y);
      if (Math.hypot(sx - gsx, sy - gsy) < CONFIRM_PX) { doPlace(ghost.x, ghost.y); return; }
      const g = computeGhost(gx, gy);
      if (g !== null) ghost = g;
      return;
    }
    ghost = computeGhost(gx, gy);
    if (ghost === null) {
      if (!C.isInsideField(gx, gy)) say("Вне поля");
      else say("Слишком близко к точке");
    }
  }

  function doUndo() {
    if (game.undo()) {
      flashes = []; lastContour = null; ghost = null;
      gameOverShown = false; hideOverlay("overlay-over");
      say("Ход отменён."); updateHUD();
    } else say("Нечего отменять.");
  }
  function doReset() {
    game = new C.Game();
    flashes = []; lastContour = null; ghost = null;
    gameOverShown = false; fitField();
    hideOverlay("overlay-over"); hideOverlay("overlay-reset");
    say("Новая игра."); updateHUD();
  }
  function showGameOver(winner) {
    gameOverShown = true;
    const title = document.getElementById("over-title");
    const text = document.getElementById("over-text");
    title.textContent = winner === C.RED_C ? "Побеждают красные!" : winner === C.BLUE_C ? "Побеждают синие!" : "Ничья";
    text.textContent = `Счёт ${game.score[C.RED_C]} : ${game.score[C.BLUE_C]}`;
    showOverlay("overlay-over");
  }

  function showOverlay(id) { document.getElementById(id).classList.remove("hidden"); }
  function hideOverlay(id) { document.getElementById(id).classList.add("hidden"); }

  // ---- рендеринг ----
  function drawEdges(color, edgeColor) {
    const act = game.activeOf(color);
    const R2 = (C.CONNECTION_RADIUS + C.EPSILON) ** 2;
    ctx.strokeStyle = edgeColor; ctx.lineWidth = 1.5;
    for (let i = 0; i < act.length; i++)
      for (let j = i + 1; j < act.length; j++) {
        const a = act[i], b = act[j];
        if ((a.x - b.x) ** 2 + (a.y - b.y) ** 2 <= R2) {
          const [x1, y1] = g2s(a.x, a.y), [x2, y2] = g2s(b.x, b.y);
          ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
        }
      }
  }
  function drawZones() {
    // зоны досягаемости активных точек (тонко, как в оригинале)
    for (const p of game.points) {
      if (!p.active) continue;
      const [sx, sy] = g2s(p.x, p.y);
      ctx.strokeStyle = p.color === C.RED_C ? COL.redZone : COL.blueZone;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(sx, sy, C.CONNECTION_RADIUS * scale, 0, Math.PI * 2);
      ctx.stroke();
    }
  }
  function drawPoints(color) {
    for (const p of game.pointsOf(color)) {
      const [sx, sy] = g2s(p.x, p.y);
      ctx.beginPath(); ctx.arc(sx, sy, DOT_R, 0, Math.PI * 2);
      if (p.active) ctx.fillStyle = color === C.RED_C ? COL.red : COL.blue;
      else ctx.fillStyle = color === C.RED_C ? COL.inactiveRed : COL.inactiveBlue;
      ctx.fill();
      if (!p.active) {
        ctx.strokeStyle = "rgba(0,0,0,0.4)"; ctx.lineWidth = 1.5;
        const k = DOT_R * 0.5;
        ctx.beginPath();
        ctx.moveTo(sx - k, sy - k); ctx.lineTo(sx + k, sy + k);
        ctx.moveTo(sx + k, sy - k); ctx.lineTo(sx - k, sy + k);
        ctx.stroke();
      }
    }
  }
  function drawContour() {
    if (!lastContour) return;
    if (now() - lastContourT > 4) { lastContour = null; return; }
    ctx.strokeStyle = COL.contour; ctx.lineWidth = 3;
    ctx.beginPath();
    const n = lastContour.length;
    for (let i = 0; i < n; i++) {
      const [sx, sy] = g2s(lastContour[i].x, lastContour[i].y);
      if (i === 0) ctx.moveTo(sx, sy); else ctx.lineTo(sx, sy);
    }
    ctx.closePath(); ctx.stroke();
  }
  function drawGhost() {
    if (!ghost) return;
    const [sx, sy] = g2s(ghost.x, ghost.y);
    ctx.strokeStyle = COL.ghostRing; ctx.lineWidth = 1.5;
    ctx.setLineDash([5, 5]);
    ctx.beginPath(); ctx.arc(sx, sy, C.CONNECTION_RADIUS * scale, 0, Math.PI * 2); ctx.stroke();
    ctx.setLineDash([]);
    const cur = game.current;
    const R2 = (C.CONNECTION_RADIUS + C.EPSILON) ** 2;
    ctx.strokeStyle = cur === C.RED_C ? COL.redEdge : COL.blueEdge; ctx.lineWidth = 2;
    for (const p of game.activeOf(cur))
      if ((p.x - ghost.x) ** 2 + (p.y - ghost.y) ** 2 <= R2) {
        const [px, py] = g2s(p.x, p.y);
        ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(px, py); ctx.stroke();
      }
    // точка призрака — цвет по типу постановки
    let fill, stroke;
    if (ghost.kind === "green") { fill = "rgba(0,170,60,0.55)"; stroke = COL.green; }
    else if (ghost.kind === "yellow") { fill = "rgba(240,200,0,0.55)"; stroke = COL.select; }
    else { fill = cur === C.RED_C ? "rgba(220,40,40,0.5)" : "rgba(40,80,220,0.5)"; stroke = cur === C.RED_C ? COL.red : COL.blue; }
    ctx.beginPath(); ctx.arc(sx, sy, GHOST_R, 0, Math.PI * 2);
    ctx.fillStyle = fill; ctx.fill();
    ctx.strokeStyle = stroke; ctx.lineWidth = 2; ctx.stroke();
    if (ghost.captured) {
      ctx.strokeStyle = COL.warn; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.arc(sx, sy, GHOST_R + 6, 0, Math.PI * 2); ctx.stroke();
    }
  }
  function drawFlashes() {
    const t = now();
    flashes = flashes.filter(f => t - f.t0 < 0.6);
    for (const f of flashes) {
      const age = (t - f.t0) / 0.6;
      const [sx, sy] = g2s(f.point.x, f.point.y);
      const r = DOT_R + age * 22;
      ctx.strokeStyle = f.type === "captured" ? `rgba(224,138,0,${1 - age})` : `rgba(0,170,60,${1 - age})`;
      ctx.lineWidth = 3;
      ctx.beginPath(); ctx.arc(sx, sy, r, 0, Math.PI * 2); ctx.stroke();
    }
  }
  function render() {
    ctx.fillStyle = COL.bg; ctx.fillRect(0, 0, W, H);
    const [cx, cy] = g2s(0, 0);
    ctx.fillStyle = COL.field;
    ctx.beginPath(); ctx.arc(cx, cy, C.FIELD_RADIUS * scale, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = COL.fieldEdge; ctx.lineWidth = 1.5; ctx.stroke();
    drawZones();
    drawEdges(C.RED_C, COL.redEdge);
    drawEdges(C.BLUE_C, COL.blueEdge);
    drawPoints(C.RED_C);
    drawPoints(C.BLUE_C);
    drawContour();
    drawGhost();
    drawFlashes();
  }
  function loop() { render(); requestAnimationFrame(loop); }

  // ---- сенсорное управление ----
  let touches = [];
  let gesture = "none";
  let tapStart = null;
  let panStart = null;
  let pinchStart = null;
  let twoFinger = null;
  const TAP_MOVE = 12, TAP_TIME = 0.5;

  function touchPos(e) {
    const r = canvas.getBoundingClientRect();
    return Array.from(e.touches).map(t => ({ id: t.identifier, x: t.clientX - r.left, y: t.clientY - r.top }));
  }
  function midOf(ts) { return { x: (ts[0].x + ts[1].x) / 2, y: (ts[0].y + ts[1].y) / 2 }; }
  function distOf(ts) { return Math.hypot(ts[0].x - ts[1].x, ts[0].y - ts[1].y); }

  canvas.addEventListener("touchstart", (e) => {
    e.preventDefault();
    const ts = touchPos(e);
    touches = ts;
    if (ts.length === 1) {
      gesture = "tap-pending";
      tapStart = { x: ts[0].x, y: ts[0].y, t: now() };
      twoFinger = null;
    } else if (ts.length === 2) {
      gesture = "pinching";
      const mid = midOf(ts);
      pinchStart = { dist: distOf(ts), scale, g: s2g(mid.x, mid.y) };
      twoFinger = { t: now(), p0: [ts[0].x, ts[0].y], p1: [ts[1].x, ts[1].y], moved: 0 };
      tapStart = null;
    }
  }, { passive: false });

  canvas.addEventListener("touchmove", (e) => {
    e.preventDefault();
    const ts = touchPos(e);
    touches = ts;
    if (gesture === "tap-pending" && ts.length === 1 && tapStart) {
      if (Math.hypot(ts[0].x - tapStart.x, ts[0].y - tapStart.y) > TAP_MOVE) {
        gesture = "panning";
        panStart = { ox: offsetX, oy: offsetY, x: ts[0].x, y: ts[0].y };
      }
    } else if (gesture === "panning" && ts.length === 1 && panStart) {
      offsetX = panStart.ox + (ts[0].x - panStart.x);
      offsetY = panStart.oy + (ts[0].y - panStart.y);
    } else if (gesture === "pinching" && ts.length === 2 && pinchStart) {
      if (twoFinger)
        twoFinger.moved = Math.max(twoFinger.moved,
          Math.hypot(ts[0].x - twoFinger.p0[0], ts[0].y - twoFinger.p0[1]) +
          Math.hypot(ts[1].x - twoFinger.p1[0], ts[1].y - twoFinger.p1[1]));
      const mid = midOf(ts);
      const ns = pinchStart.scale * (distOf(ts) / pinchStart.dist);
      scale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, ns));
      // зум к пальцам: точка g (под старым центром щипка) следует за текущим центром
      offsetX = mid.x - W / 2 - pinchStart.g[0] * scale;
      offsetY = mid.y - H / 2 + pinchStart.g[1] * scale;
    }
  }, { passive: false });

  canvas.addEventListener("touchend", (e) => {
    e.preventDefault();
    const remaining = touchPos(e);
    touches = remaining;
    if (gesture === "tap-pending" && remaining.length === 0 && tapStart) {
      if (now() - tapStart.t < TAP_TIME) handleTap(tapStart.x, tapStart.y);
      gesture = "none"; tapStart = null;
    } else if (gesture === "pinching") {
      if (remaining.length === 0 && twoFinger) {
        if (now() - twoFinger.t < 0.35 && twoFinger.moved < 18) doUndo();
        twoFinger = null; gesture = "none";
      } else if (remaining.length === 1) {
        gesture = "panning";
        panStart = { ox: offsetX, oy: offsetY, x: remaining[0].x, y: remaining[0].y };
        twoFinger = null;
      } else { gesture = "none"; twoFinger = null; }
    } else { gesture = "none"; }
  }, { passive: false });

  canvas.addEventListener("touchcancel", (e) => {
    e.preventDefault();
    touches = touchPos(e);
    gesture = "none"; tapStart = null; twoFinger = null;
  }, { passive: false });

  // ---- мышь (десктоп/тесты) ----
  let mouseDown = false, mouseStart = null, mousePan = null;
  canvas.addEventListener("mousedown", (e) => {
    const r = canvas.getBoundingClientRect();
    mouseDown = true;
    mouseStart = { x: e.clientX - r.left, y: e.clientY - r.top, t: now() };
    mousePan = null;
  });
  canvas.addEventListener("mousemove", (e) => {
    if (!mouseDown) return;
    const r = canvas.getBoundingClientRect();
    const x = e.clientX - r.left, y = e.clientY - r.top;
    if (!mousePan) {
      if (Math.hypot(x - mouseStart.x, y - mouseStart.y) > TAP_MOVE)
        mousePan = { ox: offsetX, oy: offsetY, x: mouseStart.x, y: mouseStart.y };
    } else {
      offsetX = mousePan.ox + (x - mousePan.x);
      offsetY = mousePan.oy + (y - mousePan.y);
    }
  });
  window.addEventListener("mouseup", (e) => {
    if (!mouseDown) return;
    mouseDown = false;
    if (!mousePan && mouseStart) {
      const r = canvas.getBoundingClientRect();
      if (now() - mouseStart.t < TAP_TIME) handleTap(e.clientX - r.left, e.clientY - r.top);
    }
    mouseStart = null; mousePan = null;
  });

  // ---- кнопки ----
  document.getElementById("btn-undo").addEventListener("click", doUndo);
  document.getElementById("btn-reset").addEventListener("click", () => showOverlay("overlay-reset"));
  document.getElementById("btn-help").addEventListener("click", () => showOverlay("overlay-help"));
  document.getElementById("btn-help-close").addEventListener("click", () => hideOverlay("overlay-help"));
  document.getElementById("btn-reset-cancel").addEventListener("click", () => hideOverlay("overlay-reset"));
  document.getElementById("btn-reset-confirm").addEventListener("click", doReset);
  document.getElementById("btn-over-new").addEventListener("click", doReset);

  // ---- старт ----
  window.addEventListener("resize", resize);
  resize(); fitField(); updateHUD(); loop();

  window.__dotgame = {
    get game() { return game; },
    handleTap, doPlace, doUndo, doReset, computeGhost,
    g2s, s2g, get scale() { return scale; },
    setGhost(g) { ghost = g; },
    getGreenIntersections, getYellowCurves, getCurves,
  };
})();
