// boundary_test.js — правило границы карты (Android-версия):
// две точки, поставленные на границу карты, НЕ соединяются;
// точка на границе соединяется только с точками, НЕ на границе.
// Запуск: node boundary_test.js
"use strict";
const C = require("../www/js/core.js");

let pass = 0, fail = 0;
function check(cond, msg) {
  if (cond) { pass++; }
  else { fail++; console.log("FAIL:", msg); }
}

const R = C.FIELD_RADIUS, CR = C.CONNECTION_RADIUS;

// Точки на границе: хорда длины 45 (< R=50)
const th = 2 * Math.asin(22.5 / R);
const b1 = { x: R, y: 0 };
const b2 = { x: R * Math.cos(th), y: R * Math.sin(th) };
// Внутренняя точка в пределах R от обеих
const i1 = { x: 340, y: 20 };
check(Math.hypot(b2.x - b1.x, b2.y - b1.y) <= CR, "chord b1-b2 <= R");
check(Math.hypot(i1.x - b1.x, i1.y - b1.y) <= CR, "i1-b1 <= R");
check(Math.hypot(i1.x - b2.x, i1.y - b2.y) <= CR, "i1-b2 <= R");

// --- isOnBoundary ---
check(C.isOnBoundary(b1.x, b1.y) === true, "b1 (R,0) — на границе");
check(C.isOnBoundary(b2.x, b2.y) === true, "b2 (тригонометрия) — на границе");
check(C.isOnBoundary(0, R) === true, "(0,R) — на границе");
check(C.isOnBoundary(R / Math.SQRT2, R / Math.SQRT2) === true, "45° — на границе");
check(C.isOnBoundary(i1.x, i1.y) === false, "i1 — внутри");
check(C.isOnBoundary(0, 0) === false, "центр — внутри");
check(C.isOnBoundary(R - 0.1, 0) === false, "на 0.1 внутри — не граница");
check(C.isOnBoundary(-(R + 0.1), 0) === false, "снаружи — не граница");

// --- pointsConnect ---
check(C.pointsConnect(b1, b2) === false, "граница-граница (<=R): НЕ соединяются");
check(C.pointsConnect(b1, i1) === true, "граница-внутри (<=R): соединяются");
check(C.pointsConnect(i1, { x: 345, y: 25 }) === true, "внутри-внутри (<=R): соединяются");
const b2b2 = { x: R * Math.cos(0.001), y: R * Math.sin(0.001) };
check(C.pointsConnect({ x: R, y: 0 }, b2b2) === false, "граница-граница очень близко: НЕ соединяются");
check(C.pointsConnect({ x: 0, y: 0 }, { x: 60, y: 0 }) === false, "внутри-внутри (>R): не соединяются");

// --- ColorStructure: рёбра графа ---
const st = new C.ColorStructure();
st.rebuild([b1, b2, i1], CR);
const has = (i, j) => st.edges.some(e => (e[0] === i && e[1] === j) || (e[0] === j && e[1] === i));
check(has(0, 2) === true, "ребро b1-i1 есть");
check(has(1, 2) === true, "ребро b2-i1 есть");
check(has(0, 1) === false, "ребро b1-b2 НЕТ");
// Открытая «V» — замкнутого контура нет
const inside = [0.4 * b1.x + 0.3 * b2.x + 0.3 * i1.x, 0.4 * b1.y + 0.3 * b2.y + 0.3 * i1.y];
check(st.query(inside) === false, "открытая V не захватывает");

// Контроль: треугольник из 3 ВНУТРЕННИХ точек замыкается
const c1 = { x: 340, y: 10 }, c2 = { x: 335, y: 30 }, c3 = { x: 320, y: 15 };
check(Math.hypot(c2.x - c1.x, c2.y - c1.y) <= CR &&
      Math.hypot(c3.x - c2.x, c3.y - c2.y) <= CR &&
      Math.hypot(c1.x - c3.x, c1.y - c3.y) <= CR, "triangle edges <= R");
const st2 = new C.ColorStructure();
st2.rebuild([c1, c2, c3], CR);
check(st2.edges.length === 3, "внутренний треугольник: 3 ребра");
const cen = [(c1.x + c2.x + c3.x) / 3, (c1.y + c2.y + c3.y) / 3];
check(st2.query(cen) === true, "внутренний треугольник замыкается");

// --- Game: захват при рождении ---
const g = new C.Game();
g.current = C.RED_C; g.place(b1.x, b1.y);
g.current = C.RED_C; g.place(b2.x, b2.y);
g.current = C.RED_C; g.place(i1.x, i1.y);
const res = g.place(inside[0], inside[1]); // ход синих
check(res.capturedAtBirth === false, "синяя в открытой V: НЕ захвачена при рождении");
check(res.point.active === true, "синяя точка активна");
check(g.score[C.RED_C] === 0, "счёт красных = 0");

// Контроль: захват при рождении всё ещё работает на внутренних контурах
const g2 = new C.Game();
g2.current = C.RED_C; g2.place(c1.x, c1.y);
g2.current = C.RED_C; g2.place(c2.x, c2.y);
g2.current = C.RED_C; g2.place(c3.x, c3.y);
const res2 = g2.place(cen[0], cen[1]);
check(res2.capturedAtBirth === true, "контроль: синяя в замкнутом треугольнике захвачена");
check(g2.score[C.RED_C] === 1, "контроль: счёт красных = 1");

console.log(`boundary_test: ${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
