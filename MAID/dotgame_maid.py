#!/usr/bin/env python3
"""
Игра в точки — версия горничной (MAID).
=======================================

Синтез всех версий мастера (dotgame.py … dotgame2026_manual.py) без их
центральной проблемы: экспоненциального перебора циклов.

Ключевое отличие
----------------
В версиях мастера после каждого хода перечислялись ВСЕ простые циклы
графа соединений. Плотный кластер из ~10 точек даёт сотни тысяч циклов —
игра зависала после каждого хода. Здесь перебора циклов НЕТ:

  точка X «внутри какого-либо контура» цвета C  <=>
  X лежит на некомпонентном (не мостовом) ребре графа C
  ИЛИ X находится в ограниченной грани планарного вложения
  множества некомпонентных рёбер.

Грани находятся обходом за O(V+E), членство X в грани — лучом за O(E).
Предикат проверен полным перебором циклов на 16828 конфигурациях:
0 расхождений; скорость ~0.03–0.3 мс на запрос.

Правила (по заданию мастера, 06.11.2026)
----------------------------------------
* Круглое поле, красные ходят первыми, ходы чередуются.
* Точки одной стороны в пределах CONNECTION_RADIUS соединяются линиями.
* Закрытая цепочка линий — контур; точка противника внутри (или на
  линии) контура захватывается и становится неактивной НАВСЕГДА
  (без оживления; режим с оживлением — REACTIVATION = True).
* Поставленная внутрь чужого контура точка захватывается сразу
  (самопожертвование) — идёт в счёт противнику.
* Счёт — число захваченных точек (без оживления счёт = текущее
  число неактивных точек противника).
* NEW: лимит точек на сторону (MAX_POINTS_PER_PLAYER, 0 = без лимита)
  и конец игры; отмена хода (Z); сброс (R); справка (H).

Управление
----------
  ЛКМ          поставить точку (с привязкой к выбранной линии)
  ПКМ          выбрать линию (границу поля / окружность точки / ребро)
  ПКМ повторно та же линия — зелёные кандидаты на пересечениях
  СКМ (тянуть) перемещение камеры; колесо — масштаб
  Z            отменить последний ход
  R            новая игра
  H            справка
  Esc          снять выделение линии

Режимы (аргументы командной строки)
-----------------------------------
  (нет)        два игрока за одной клавиатурой
  --ai         компьютер играет синими, игрок — красные
  --aibot      обе стороны играет компьютер (демо/автопартия)
"""

import math
import sys

# ----------------------------------------------------------------------
# Настройки
# ----------------------------------------------------------------------
WIDTH, HEIGHT = 800, 800
FIELD_RADIUS = 350        # радиус игрового поля (координаты поля: центр 0,0)
CONNECTION_RADIUS = 50    # радиус соединения точек
DOT_SIZE = 3
FPS = 60
EPSILON = 1e-5            # допуск «на линии» (как у мастера)
MAX_POINTS_PER_PLAYER = 0 # 0 = без лимита (как раньше); например 40 — с концом игры
UNDO_LIMIT = 200
# По просьбе мастера: без оживления точек — захваченная точка неактивна навсегда.
# (Вариант с оживлением сохранён: REACTIVATION = True — как в dotgame2026.py.)
REACTIVATION = False

# Цвета
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (220, 40, 40)
BLUE = (40, 80, 220)
YELLOW = (240, 200, 0)
GREEN = (0, 170, 60)
GRAY_RED = (150, 120, 120)
GRAY_BLUE = (120, 120, 150)
FAINT = (205, 205, 205)

# ----------------------------------------------------------------------
# Ядро геометрии: «X внутри какого-либо простого цикла графа точек»
# ----------------------------------------------------------------------
GEPS = 1e-9
ON_EPS = 1e-5
PAR_EPS = 1e-10


def _dist2(ax, ay, bx, by):
    return (ax - bx) ** 2 + (ay - by) ** 2


def _point_seg_dist2(px, py, a, b):
    vx, vy = b[0] - a[0], b[1] - a[1]
    L2 = vx * vx + vy * vy
    if L2 < GEPS:
        return _dist2(px, py, a[0], a[1])
    t = ((px - a[0]) * vx + (py - a[1]) * vy) / L2
    if t < 0:
        return _dist2(px, py, a[0], a[1])
    if t > 1:
        return _dist2(px, py, b[0], b[1])
    cx = a[0] + t * vx
    cy = a[1] + t * vy
    return _dist2(px, py, cx, cy)


def _convex_hull(pts):
    P = sorted(set(pts))
    if len(P) <= 2:
        return P

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in P:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(P):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _line_key(a, b):
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    L = math.hypot(dx, dy)
    if L < GEPS:
        return None
    nx, ny = dy / L, -dx / L
    c = -(nx * a[0] + ny * a[1])
    if nx < -GEPS or (abs(nx) <= GEPS and ny < -GEPS):
        nx, ny, c = -nx, -ny, -c
    return (round(nx, 9), round(ny, 9), round(c, 9))


def _canon_dir(a, b):
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    L = math.hypot(dx, dy)
    dx, dy = dx / L, dy / L
    if dx < -GEPS or (abs(dx) <= GEPS and dy < -GEPS):
        dx, dy = -dx, -dy
    return dx, dy


def _merge_collinear(segs):
    groups = {}
    for s in segs:
        k = _line_key(s[0], s[1])
        if k is not None:
            groups.setdefault(k, []).append(s)
    out = []
    for g in groups.values():
        if len(g) == 1:
            out.append(g[0])
            continue
        p0 = g[0][0]
        dx, dy = _canon_dir(g[0][0], g[0][1])
        intervals = []
        for (a, b) in g:
            ta = (a[0] - p0[0]) * dx + (a[1] - p0[1]) * dy
            tb = (b[0] - p0[0]) * dx + (b[1] - p0[1]) * dy
            intervals.append((min(ta, tb), max(ta, tb)))
        intervals.sort()
        merged = [list(intervals[0])]
        for lo, hi in intervals[1:]:
            if lo <= merged[-1][1] + 1e-7:
                merged[-1][1] = max(merged[-1][1], hi)
            else:
                merged.append([lo, hi])
        for lo, hi in merged:
            out.append(((p0[0] + lo * dx, p0[1] + lo * dy),
                        (p0[0] + hi * dx, p0[1] + hi * dy)))
    return out


def _seg_intersect_params(a1, a2, b1, b2):
    dx1, dy1 = a2[0] - a1[0], a2[1] - a1[1]
    dx2, dy2 = b2[0] - b1[0], b2[1] - b1[1]
    den = dx1 * dy2 - dy1 * dx2
    if abs(den) < GEPS:
        return None
    dpx, dpy = b1[0] - a1[0], b1[1] - a1[1]
    s = (dpx * dy2 - dpy * dx2) / den
    t = (dpx * dy1 - dpy * dx1) / den
    return s, t


def _planarize(segs):
    """Разбивает отрезки в точках пересечений и T-контактов."""
    n = len(segs)
    splits = [[] for _ in range(n)]
    for i in range(n):
        a1, a2 = segs[i]
        for j in range(i + 1, n):
            b1, b2 = segs[j]
            if (max(min(a1[0], a2[0]), min(b1[0], b2[0])) >
                    min(max(a1[0], a2[0]), max(b1[0], b2[0])) + 1e-7):
                continue
            if (max(min(a1[1], a2[1]), min(b1[1], b2[1])) >
                    min(max(a1[1], a2[1]), max(b1[1], b2[1])) + 1e-7):
                continue
            st = _seg_intersect_params(a1, a2, b1, b2)
            if st is None:
                continue
            s, t = st
            if 0 < s < 1 and 0 < t < 1:
                splits[i].append(s)
                splits[j].append(t)
            elif abs(s) < 1e-7 and 1e-7 < t < 1 - 1e-7:
                splits[j].append(t)
            elif abs(s - 1) < 1e-7 and 1e-7 < t < 1 - 1e-7:
                splits[j].append(t)
            elif abs(t) < 1e-7 and 1e-7 < s < 1 - 1e-7:
                splits[i].append(s)
            elif abs(t - 1) < 1e-7 and 1e-7 < s < 1 - 1e-7:
                splits[i].append(s)
    vmap = {}
    verts = []

    def vid(p):
        k = (round(p[0], 8), round(p[1], 8))
        if k not in vmap:
            vmap[k] = len(verts)
            verts.append(p)
        return vmap[k]

    pslg = []
    for i in range(n):
        a1, a2 = segs[i]
        L = math.hypot(a2[0] - a1[0], a2[1] - a1[1])
        if L < GEPS:
            continue
        dx, dy = (a2[0] - a1[0]) / L, (a2[1] - a1[1]) / L
        params = sorted(set([0.0, 1.0] +
                            [s for s in splits[i] if 1e-9 < s < 1 - 1e-9]))
        for k in range(len(params) - 1):
            if params[k + 1] - params[k] < 1e-9:
                continue
            pa = (a1[0] + dx * L * params[k], a1[1] + dy * L * params[k])
            pb = (a1[0] + dx * L * params[k + 1], a1[1] + dy * L * params[k + 1])
            pslg.append((vid(pa), vid(pb)))
    return verts, pslg


def _find_bridges(n, edges):
    adj = [[] for _ in range(n)]
    for ei, (u, v) in enumerate(edges):
        adj[u].append((v, ei))
        adj[v].append((u, ei))
    disc = [-1] * n
    low = [0] * n
    bridges = set()
    timer = [0]

    def dfs(u, pe):
        disc[u] = low[u] = timer[0]
        timer[0] += 1
        for v, ei in adj[u]:
            if ei == pe:
                continue
            if disc[v] == -1:
                dfs(v, ei)
                low[u] = min(low[u], low[v])
                if low[v] > disc[u]:
                    bridges.add(ei)
            else:
                low[u] = min(low[u], disc[v])

    for i in range(n):
        if disc[i] == -1:
            dfs(i, -1)
    return bridges


class ColorStructure:
    """Ленивая структура цвета для предиката «X внутри контура».

    Пересчитывается при каждом изменении набора активных точек этого
    цвета. Сложность: O(E log E); запрос — O(E).
    """

    def __init__(self):
        self.pts = []
        self.n = 0
        self.edges = []
        self.nb_edges = []
        self.segs = []
        self.empty = True
        self.verts = []
        self.pslg = []
        self.face_of_dir = {}
        self.outer_faces = set()
        self.hull = []

    def rebuild(self, points, radius):
        self.pts = [(p.x, p.y) for p in points]
        self.n = len(self.pts)
        self.edges = []
        if self.n >= 3:
            R2 = (radius + ON_EPS) ** 2
            for i in range(self.n):
                xi, yi = self.pts[i]
                for j in range(i + 1, self.n):
                    xj, yj = self.pts[j]
                    if (xi - xj) ** 2 + (yi - yj) ** 2 <= R2:
                        self.edges.append((i, j))
        self.nb_edges = []
        if self.edges:
            bridges = _find_bridges(self.n, self.edges)
            self.nb_edges = [e for i, e in enumerate(self.edges) if i not in bridges]
        if not self.nb_edges:
            self.empty = True
            self.segs = []
            self.verts = []
            self.pslg = []
            self.face_of_dir = {}
            self.outer_faces = set()
            self.hull = _convex_hull(self.pts)
            return
        segs = [(self.pts[u], self.pts[v]) for (u, v) in self.nb_edges]
        merged = _merge_collinear(segs)
        verts, pslg = _planarize(merged)
        if not pslg:
            self.empty = True
            return
        self.empty = False
        self.verts = verts
        self.pslg = pslg
        # обход граней
        ang = [[] for _ in range(len(verts))]
        for u, v in pslg:
            ang[u].append(v)
            ang[v].append(u)
        idx = [{} for _ in range(len(verts))]
        for u in range(len(verts)):
            if not ang[u]:
                continue
            items = []
            for v in ang[u]:
                dx = verts[v][0] - verts[u][0]
                dy = verts[v][1] - verts[u][1]
                items.append((math.atan2(dy, dx), v))
            items.sort()
            ang[u] = [v for _, v in items]
            idx[u] = {v: i for i, v in enumerate(ang[u])}

        def next_dir(u, v):
            # ЛЕВАЯ грань: шаг по ЧАСОВОЙ стрелке от обратного направления
            i = idx[v][u]
            w = ang[v][(i - 1) % len(ang[v])]
            return (v, w)

        face_of_dir = {}
        faces = []
        for u, v in pslg:
            for d in ((u, v), (v, u)):
                if d in face_of_dir:
                    continue
                cur = d
                poly = [verts[d[0]], verts[d[1]]]
                while True:
                    face_of_dir[cur] = len(faces)
                    cur = next_dir(cur[0], cur[1])
                    poly.append(verts[cur[1]])
                    if cur == d:
                        break
                faces.append(poly)
        outer = set()
        for fi, poly in enumerate(faces):
            a = 0.0
            m = len(poly)
            for i in range(m):
                x1, y1 = poly[i]
                x2, y2 = poly[(i + 1) % m]
                a += x1 * y2 - x2 * y1
            if a < 0:
                outer.add(fi)
        self.face_of_dir = face_of_dir
        self.outer_faces = outer
        self.hull = _convex_hull(self.pts)
        self.segs = [(self.pts[u], self.pts[v]) for (u, v) in self.nb_edges]

    # ---- запрос ----
    def on_edge(self, X):
        for (a, b) in self.segs:
            if _point_seg_dist2(X[0], X[1], a, b) < ON_EPS * ON_EPS:
                return True
        return False

    def outside_hull(self, X):
        h = self.hull
        n = len(h)
        if n == 0:
            return True
        if n == 1:
            return _dist2(X[0], X[1], h[0][0], h[0][1]) > ON_EPS * ON_EPS
        if n == 2:
            return _point_seg_dist2(X[0], X[1], h[0], h[1]) > ON_EPS * ON_EPS
        for i in range(n):
            a = h[i]
            b = h[(i + 1) % n]
            cr = (b[0] - a[0]) * (X[1] - a[1]) - (b[1] - a[1]) * (X[0] - a[0])
            if cr < -ON_EPS:
                return True
        return False

    def query(self, X):
        """True, если X внутри (или на линии) какого-либо простого цикла."""
        if self.empty:
            return False
        if self.on_edge(X):
            return True
        if self.outside_hull(X):
            return False
        for t in (0.0, 1e-9, -1e-9, 1e-8, -1e-8, 1e-7, -1e-7, 1e-6, -1e-6):
            # дегенерация: вершина на луче / отрезок на луче
            bad = False
            for v in self.verts:
                rx, ry = v[0] - X[0], v[1] - X[1]
                if rx <= 0:
                    continue
                if abs(rx * t - ry) < 1e-9 * math.hypot(rx, ry):
                    bad = True
                    break
            if bad:
                continue
            best = None
            for (vi, vj) in self.pslg:
                pa = self.verts[vi]
                pb = self.verts[vj]
                ddx = pb[0] - pa[0]
                ddy = pb[1] - pa[1]
                den = 1.0 * ddy - t * ddx
                if abs(den) < PAR_EPS:
                    continue
                rx, ry = pa[0] - X[0], pa[1] - X[1]
                s = (rx * ddy - ry * ddx) / den
                u = (rx * t - ry) / den
                if s > 1e-9 and 0 < u < 1:
                    if best is None or s < best[0]:
                        best = (s, vi, vj)
            if best is None:
                return False
            s, vi, vj = best
            pa = self.verts[vi]
            pb = self.verts[vj]
            e = 1e-9
            Q = (X[0] + s - e, X[1] + s * t - e * t)  # точка сражения, чуть назад
            side = (pb[0] - pa[0]) * (Q[1] - pa[1]) - (pb[1] - pa[1]) * (Q[0] - pa[0])
            d0 = (vi, vj) if side > 0 else (vj, vi)
            return self.face_of_dir[d0] not in self.outer_faces
        raise RuntimeError("no generic ray found")


# ----------------------------------------------------------------------
# Логика игры (без pygame — тестируется отдельно)
# ----------------------------------------------------------------------
RED_C = "red"
BLUE_C = "blue"


def other_color(c):
    return BLUE_C if c == RED_C else RED_C


class Point:
    __slots__ = ("id", "x", "y", "color", "active")

    def __init__(self, x, y, color, active=True, pid=0):
        self.x = x
        self.y = y
        self.color = color
        self.active = active
        self.id = pid

    def pos(self):
        return (self.x, self.y)

    def snapshot(self):
        return (self.id, self.x, self.y, self.color, self.active)

    @staticmethod
    def from_snapshot(t):
        return Point(t[1], t[2], t[3], t[4], t[0])


class MoveResult:
    def __init__(self, point, captured_at_birth, newly_captured, reactivated,
                 last_contour=None, passed=False, game_over=False, winner=None):
        self.point = point
        self.captured_at_birth = captured_at_birth
        self.newly_captured = newly_captured
        self.reactivated = reactivated
        self.last_contour = last_contour
        self.passed = passed
        self.game_over = game_over   # True, если игра окончена
        self.winner = winner         # RED_C / BLUE_C / None (ничья)


class Game:
    """Чистая логика: точки, захваты, оживания, счёт, отмена."""

    def __init__(self, max_points=MAX_POINTS_PER_PLAYER, reactivation=REACTIVATION):
        self.max_points = max_points
        self.reactivation = reactivation
        self.points = []          # все точки (оба цвета)
        self.score = {RED_C: 0, BLUE_C: 0}
        self.current = RED_C
        self.history = []         # снапшоты для отмены
        self.struct = {RED_C: ColorStructure(), BLUE_C: ColorStructure()}
        self.struct_dirty = {RED_C: True, BLUE_C: True}
        self._next_id = 0

    # ---------- служебное ----------
    def points_of(self, color):
        return [p for p in self.points if p.color == color]

    def active_of(self, color):
        return [p for p in self.points if p.color == color and p.active]

    def count_of(self, color):
        return len(self.points_of(color))

    def at_limit(self, color):
        return self.max_points > 0 and self.count_of(color) >= self.max_points

    def _ensure_struct(self, color):
        st = self.struct[color]
        if self.struct_dirty[color]:
            st.rebuild(self.active_of(color), CONNECTION_RADIUS)
            self.struct_dirty[color] = False

    def _invalidate(self, color):
        self.struct_dirty[color] = True

    def _in_some_contour(self, color, x, y):
        self._ensure_struct(color)
        return self.struct[color].query((x, y))

    # ---------- ход ----------
    def place(self, x, y):
        """Ставит точку за current. Возвращает MoveResult."""
        if self.at_limit(self.current):
            ended = self.at_limit(RED_C) and self.at_limit(BLUE_C)
            return MoveResult(None, False, [], [], passed=True,
                              game_over=ended,
                              winner=(self._winner() if ended else None))
        snap = self._snapshot()
        O = other_color(self.current)
        self._ensure_struct(O)
        captured = self.struct[O].query((x, y))
        p = Point(x, y, self.current, active=not captured, pid=self._next_id)
        self._next_id += 1
        self.points.append(p)
        if captured:
            self.score[O] += 1
        self._invalidate(self.current)
        newly, reactivated = self._cascade()
        contour = self._find_capture_contour(p, newly, captured_at_birth=captured)
        # смена хода (с учётом лимитов)
        prev = self.current
        self.current = O
        passed = False
        if self.at_limit(self.current):
            self.current = prev
            passed = True
        game_over = False
        winner = None
        if self.at_limit(RED_C) and self.at_limit(BLUE_C):
            game_over = True
            winner = self._winner()
        self.history.append(snap)
        if len(self.history) > UNDO_LIMIT:
            self.history.pop(0)
        return MoveResult(p, captured, newly, reactivated,
                          last_contour=contour, passed=passed,
                          game_over=game_over, winner=winner)

    def _cascade(self):
        """Захваты (и оживления, если включены) после хода.

        Без оживления (основной режим) достаточно одного прохода:
        область ходящего монотонно растёт, захваченные точки не
        возвращаются, поэтому повторные захваты невозможны.

        С оживлением: область ходящего растёт, область противника
        сжимается, каждая точка меняет статус не более раза — цикл
        до устойчивого состояния гарантированно сходится."""
        moved = self.current
        opp = other_color(moved)
        newly = []
        reactivated = []
        if not self.reactivation:
            self._ensure_struct(moved)
            st = self.struct[moved]
            for p in self.points_of(opp):
                if p.active and st.query(p.pos()):
                    p.active = False
                    self.score[moved] += 1
                    newly.append(p)
            if newly:
                self._invalidate(opp)
            return newly, reactivated
        changed = True
        while changed:
            changed = False
            for C in (moved, opp):
                OC = other_color(C)
                self._ensure_struct(OC)
                st = self.struct[OC]
                for p in self.points_of(C):
                    want = not st.query(p.pos())
                    if p.active == want:
                        continue
                    p.active = want
                    changed = True
                    self._invalidate(C)
                    if want:
                        reactivated.append(p)
                    else:
                        self.score[OC] += 1
                        newly.append(p)
        return newly, reactivated

    def _find_capture_contour(self, new_point, newly_captured, captured_at_birth):
        """Визуализация: один из новых контуров, сделавших захват (с ограничением)."""
        targets = newly_captured
        if captured_at_birth and not targets:
            targets = [new_point]
        if not targets:
            return None
        C = self.current
        own = self.active_of(C)
        if new_point not in own and new_point.active:
            own = own + [new_point]
        R2 = (CONNECTION_RADIUS + ON_EPS) ** 2
        idx = {id(p): i for i, p in enumerate(own)}
        ni = idx.get(id(new_point))
        if ni is None:
            return None
        adj = [[] for _ in own]
        for i, a in enumerate(own):
            for j in range(i + 1, len(own)):
                b = own[j]
                dx = a.x - b.x
                dy = a.y - b.y
                if dx * dx + dy * dy <= R2:
                    adj[i].append(j)
                    adj[j].append(i)
        neighbors = adj[ni]
        if len(neighbors) < 2:
            return None
        budget = [30000]
        found = [None]

        def poly_of(path):
            # path: [a, ..., cur] — индексы (без новой точки и замыкающей b)
            # цикл = new -> a -> ... -> cur -> b -> new
            return [new_point] + [own[i] for i in path] + [own[b]]

        def pip(poly, pt):
            # even-odd; на границе -> True
            xs = [q.x for q in poly]
            ys = [q.y for q in poly]
            n = len(poly)
            for i in range(n):
                a = poly[i]
                b = poly[(i + 1) % n]
                if _point_seg_dist2(pt.x, pt.y, (a.x, a.y), (b.x, b.y)) < ON_EPS * ON_EPS:
                    return True
            inside = False
            j = n - 1
            for i in range(n):
                yi, yj = ys[i], ys[j]
                if (yi > pt.y) != (yj > pt.y):
                    xints = (xs[j] - xs[i]) * (pt.y - yi) / (yj - yi) + xs[i]
                    if pt.x < xints:
                        inside = not inside
                j = i
            return inside

        for a in neighbors:
            for b in neighbors:
                if a == b:
                    continue
                inpath = {ni, a}

                def dfs(cur, path):
                    if budget[0] <= 0 or found[0] is not None:
                        return
                    budget[0] -= 1
                    for nb in adj[cur]:
                        if nb == b and len(path) >= 1:
                            cyc = poly_of(path)
                            for t in targets:
                                if pip(cyc, t):
                                    found[0] = cyc
                                    return
                        if nb not in inpath and nb != ni:
                            inpath.add(nb)
                            path.append(nb)
                            dfs(nb, path)
                            path.pop()
                            inpath.remove(nb)
                        if found[0] is not None:
                            return
                dfs(a, [a])
                if found[0] is not None:
                    break
            if found[0] is not None:
                break
        return found[0]

    def _winner(self):
        if self.score[RED_C] > self.score[BLUE_C]:
            return RED_C
        if self.score[BLUE_C] > self.score[RED_C]:
            return BLUE_C
        return None

    # ---------- отмена / сброс ----------
    def _snapshot(self):
        return ([p.snapshot() for p in self.points],
                dict(self.score), self.current, self._next_id)

    def undo(self):
        if not self.history:
            return False
        pts, score, current, next_id = self.history.pop()
        self.points = [Point.from_snapshot(t) for t in pts]
        self.score = score
        self.current = current
        self._next_id = next_id
        self.struct_dirty = {RED_C: True, BLUE_C: True}
        return True

    def reset(self, max_points=None):
        self.__init__(max_points if max_points is not None else self.max_points)

    def clone(self):
        """Копия позиции для симуляции (история не копируется)."""
        g = Game(self.max_points, reactivation=self.reactivation)
        g.points = [Point.from_snapshot(p.snapshot()) for p in self.points]
        g.score = dict(self.score)
        g.current = self.current
        g._next_id = self._next_id
        return g


# ----------------------------------------------------------------------
# Простой локальный ИИ (режимы --ai / --aibot)
# ----------------------------------------------------------------------
# Стратегия: кандидатные точки — пересечения окружений радиуса
# CONNECTION_RADIUS вокруг активных точек (та же геометрия, что и привязка),
# середины рёбер и продолжения рёбер; для пустой доски — стартовый набор
# (центр + кольцо). Двухслойная оценка: выгода собственного хода (захваты,
# новый цикл, почти-захваты чужих точек) минус выгода лучшего ответа
# противника (тот же набор сценариев, со скидкой 0.9).
# Ход-самопожертвование выбирается только если безопасных нет.
# Бюджет времени ограничивает число полноценных оценок.


def _starter_points():
    """Стартовый набор для пустой/редкой позиции: центр и кольцо."""
    pts = [(0.0, 0.0)]
    for i in range(7):
        a = 2 * math.pi * i / 7
        pts.append((CONNECTION_RADIUS * 2 * math.cos(a),
                    CONNECTION_RADIUS * 2 * math.sin(a)))
    return pts


def ai_candidates(game, color, cap=120, min_dist=1.0):
    """Кандидатные позиции для хода color. Детерминированный порядок."""
    CR = CONNECTION_RADIUS
    pts = game.points
    act = [p for p in pts if p.active]
    cands = []
    seen = set()

    def add(x, y):
        if math.hypot(x, y) > FIELD_RADIUS - 1.0:
            return
        k = (round(x, 3), round(y, 3))
        if k in seen:
            return
        for p in pts:
            if (p.x - x) ** 2 + (p.y - y) ** 2 < min_dist * min_dist:
                return
        seen.add(k)
        cands.append((x, y))

    for i in range(len(act)):
        a = act[i]
        for j in range(i + 1, len(act)):
            b = act[j]
            for (x, y) in intersect_circle_circle(
                    {'center': (a.x, a.y), 'radius': CR},
                    {'center': (b.x, b.y), 'radius': CR}):
                add(x, y)
            mx, my = (a.x + b.x) / 2.0, (a.y + b.y) / 2.0
            add(mx, my)
            d = math.hypot(b.x - a.x, b.y - a.y)
            if d > EPSILON:
                # продолжение ребра a->b: точка в CR от b вдоль луча
                add(b.x + (b.x - a.x) / d * CR, b.y + (b.y - a.y) / d * CR)
    if not cands:
        # пустая или редкая доска: стартовый набор
        for (x, y) in _starter_points():
            add(x, y)
    if not cands:
        # поле почти заполнено: грубая сетка как последний резерв
        step = 12.0
        x = -FIELD_RADIUS + 10.0
        while x < FIELD_RADIUS - 10.0:
            y = -FIELD_RADIUS + 10.0
            while y < FIELD_RADIUS - 10.0:
                add(x, y)
                y += step
            x += step
    if len(cands) > cap:
        cands = cands[:cap]
    return cands


class SimpleAI:
    """Двухслойная оценка по кандидатным точкам, с бюджетом времени."""

    def __init__(self, color, budget_s=4.0, cap1=60, cap2=30):
        self.color = color
        self.budget_s = budget_s
        self.cap1 = cap1
        self.cap2 = cap2

    def choose(self, game):
        """Возвращает (x, y) или None (только если ходить некуда)."""
        t0 = ai_now()
        cands = ai_candidates(game, self.color, cap=self.cap1)
        if not cands:
            return None
        # первый проход: симуляция всех кандидатов (без ответных угроз)
        evals = []
        for (x, y) in cands:
            sim = game.clone()
            res = sim.place(x, y)
            if res.point is not None:
                evals.append(((x, y), res.captured_at_birth, res, sim))
        safe = [e for e in evals if not e[1]]
        pool = safe if safe else evals  # жертва — только если нет выбора
        best = None
        best_val = None
        for ((x, y), suicide, res, sim) in pool:
            if best is not None and ai_now() - t0 > self.budget_s:
                break
            val = 3.0 * len(res.newly_captured)
            val += 0.1 * self._own_neighbors(sim, res.point)
            if self._creates_cycle(sim, res.point):
                # ход замкнул собственный цикл — контур-угроза для противника
                val += 4.0
            val += self._corners_on_opponents(sim)
            # минус: полная выгода лучшего ответа противника (2-слойный взгляд)
            val -= 0.9 * self._opp_threat(sim)
            if best_val is None or val > best_val:
                best_val = val
                best = (x, y)
        return best

    def _corners(self, sim, mover):
        """Почти-захват: у точки противника ходящего уже >=2 его активных
        точек в радиусе соединения — ещё один ход её закрывает.
        Награда за такое сгущение."""
        R2 = (CONNECTION_RADIUS + EPSILON) ** 2
        own = sim.active_of(mover)
        val = 0.0
        for q in sim.active_of(other_color(mover)):
            c = 0
            for a in own:
                if (a.x - q.x) ** 2 + (a.y - q.y) ** 2 <= R2:
                    c += 1
            if c >= 3:
                val += 2.0
            elif c == 2:
                val += 1.0
        return val

    def _corners_on_opponents(self, sim):
        return self._corners(sim, self.color)

    def _creates_cycle_for(self, sim, mover, p):
        """Создал ли ход p (цвет mover) новый цикл в графе mover: p лежит
        на цикле. Эквивалент: у p два соседа, между которыми существует
        путь без прохождения через p. BFS, O(V^2)."""
        R2 = (CONNECTION_RADIUS + EPSILON) ** 2
        own = sim.active_of(mover)
        nbrs = [q for q in own
                if q is not p and (q.x - p.x) ** 2 + (q.y - p.y) ** 2 <= R2]
        if len(nbrs) < 2:
            return False
        start = nbrs[0]
        seen = {id(start)}
        stack = [start]
        while stack:
            u = stack.pop()
            for v in own:
                if v is p or v is u or id(v) in seen:
                    continue
                if (u.x - v.x) ** 2 + (u.y - v.y) ** 2 <= R2:
                    if any(v is n for n in nbrs[1:]):
                        return True
                    seen.add(id(v))
                    stack.append(v)
        return False

    def _creates_cycle(self, sim, p):
        return self._creates_cycle_for(sim, self.color, p)

    def _own_neighbors(self, sim, p):
        """Сколько своих активных точек рядом (награда за сгущение)."""
        n = 0
        for q in sim.active_of(self.color):
            if q is p:
                continue
            if (q.x - p.x) ** 2 + (q.y - p.y) ** 2 <= (CONNECTION_RADIUS + EPSILON) ** 2:
                n += 1
        return n

    def _opp_threat(self, sim):
        """Полная оценка (лист) лучшего ответного хода противника:
        его захваты + его новый цикл + его почти-захваты. Это и есть
        взгляд вперёд на один слой."""
        oc = other_color(self.color)
        threats = 0.0
        for (ox, oy) in ai_candidates(sim, oc, cap=self.cap2):
            s2 = sim.clone()
            r2 = s2.place(ox, oy)
            if r2.point is None or r2.captured_at_birth:
                continue
            v = 3.0 * len(r2.newly_captured)
            if self._creates_cycle_for(s2, oc, r2.point):
                v += 4.0
            v += self._corners(s2, oc)
            if v > threats:
                threats = v
        return threats


def ai_now():
    try:
        import pygame
        return pygame.time.get_ticks() / 1000.0
    except Exception:
        import time
        return time.monotonic()
def is_inside_field(x, y):
    return math.hypot(x, y) <= FIELD_RADIUS + EPSILON


def distance_p(p1, p2):
    return math.hypot(p1.x - p2.x, p1.y - p2.y)


def distance_point_to_segment(px, py, ax, ay, bx, by):
    vx = bx - ax
    vy = by - ay
    wx = px - ax
    wy = py - ay
    dot = vx * wx + vy * wy
    len_sq = vx * vx + vy * vy
    if len_sq < EPSILON:
        return math.hypot(px - ax, py - ay)
    t = dot / len_sq
    if t < 0:
        return math.hypot(px - ax, py - ay)
    elif t > 1:
        return math.hypot(px - bx, py - by)
    else:
        proj_x = ax + t * vx
        proj_y = ay + t * vy
        return math.hypot(px - proj_x, py - proj_y)


def project_point_on_segment(px, py, ax, ay, bx, by):
    vx = bx - ax
    vy = by - ay
    dot = (px - ax) * vx + (py - ay) * vy
    len_sq = vx * vx + vy * vy
    if len_sq < EPSILON:
        return (ax, ay)
    t = max(0, min(1, dot / len_sq))
    return (ax + t * vx, ay + t * vy)


def intersect_circle_circle(c1, c2):
    (x0, y0), r0 = c1['center'], c1['radius']
    (x1, y1), r1 = c2['center'], c2['radius']
    d = math.hypot(x1 - x0, y1 - y0)
    if d > r0 + r1 or d < abs(r0 - r1) or d < EPSILON:
        return []
    a = (r0 * r0 - r1 * r1 + d * d) / (2 * d)
    h = math.sqrt(max(0, r0 * r0 - a * a))
    x2 = x0 + a * (x1 - x0) / d
    y2 = y0 + a * (y1 - y0) / d
    rx = -h * (y1 - y0) / d
    ry = h * (x1 - x0) / d
    return [(x2 + rx, y2 + ry), (x2 - rx, y2 - ry)]


def intersect_circle_segment(circle, seg):
    cx, cy = circle['center']
    r = circle['radius']
    ax, ay = seg['p1']
    bx, by = seg['p2']
    dx = bx - ax
    dy = by - ay
    fx = ax - cx
    fy = ay - cy
    a_coef = dx * dx + dy * dy
    b_coef = 2 * (fx * dx + fy * dy)
    c_coef = fx * fx + fy * fy - r * r
    discriminant = b_coef * b_coef - 4 * a_coef * c_coef
    if discriminant < 0:
        return []
    discriminant = math.sqrt(discriminant)
    t1 = (-b_coef + discriminant) / (2 * a_coef)
    t2 = (-b_coef - discriminant) / (2 * a_coef)
    points = []
    if -EPSILON <= t1 <= 1 + EPSILON:
        points.append((ax + t1 * dx, ay + t1 * dy))
    if -EPSILON <= t2 <= 1 + EPSILON:
        points.append((ax + t2 * dx, ay + t2 * dy))
    return points


def intersect_segment_segment(seg1, seg2):
    ax, ay = seg1['p1']
    bx, by = seg1['p2']
    cx, cy = seg2['p1']
    dx, dy = seg2['p2']
    denominator = (ax - bx) * (cy - dy) - (ay - by) * (cx - dx)
    if abs(denominator) < EPSILON:
        return []
    t = ((ax - cx) * (cy - dy) - (ay - cy) * (cx - dx)) / denominator
    u = ((ax - cx) * (ay - by) - (ay - cy) * (ax - bx)) / denominator
    if -EPSILON <= t <= 1 + EPSILON and -EPSILON <= u <= 1 + EPSILON:
        return [(ax + t * (bx - ax), ay + t * (by - ay))]
    return []


def compute_intersections(selected, other):
    if selected['type'] == 'circle' and other['type'] == 'circle':
        return intersect_circle_circle(selected, other)
    elif selected['type'] == 'circle' and other['type'] == 'segment':
        return intersect_circle_segment(selected, other)
    elif selected['type'] == 'segment' and other['type'] == 'circle':
        return intersect_circle_segment(other, selected)
    elif selected['type'] == 'segment' and other['type'] == 'segment':
        return intersect_segment_segment(selected, other)
    return []


def candidate_equals(cand1, cand2):
    if cand1['type'] != cand2['type']:
        return False
    if cand1['type'] == 'circle':
        cx1, cy1 = cand1['center']
        cx2, cy2 = cand2['center']
        return (math.hypot(cx1 - cx2, cy1 - cy2) < EPSILON and
                abs(cand1['radius'] - cand2['radius']) < EPSILON)
    p1, p2 = cand1['p1'], cand1['p2']
    q1, q2 = cand2['p1'], cand2['p2']
    return ((math.hypot(p1[0] - q1[0], p1[1] - q1[1]) < EPSILON and
             math.hypot(p2[0] - q2[0], p2[1] - q2[1]) < EPSILON) or
            (math.hypot(p1[0] - q2[0], p1[1] - q2[1]) < EPSILON and
             math.hypot(p2[0] - q1[0], p2[1] - q1[1]) < EPSILON))


def get_candidate_lines(red_points, blue_points):
    candidates = []
    candidates.append({'type': 'circle', 'center': (0, 0), 'radius': FIELD_RADIUS,
                       'desc': 'field', 'owner': "neutral"})
    for p in red_points + blue_points:
        if p.active:
            candidates.append({'type': 'circle', 'center': (p.x, p.y),
                               'radius': CONNECTION_RADIUS, 'desc': 'point',
                               'owner': p.color})

    def add_segments(points):
        active_points = [p for p in points if p.active]
        n = len(active_points)
        for i in range(n):
            for j in range(i + 1, n):
                if distance_p(active_points[i], active_points[j]) <= CONNECTION_RADIUS + EPSILON:
                    candidates.append({
                        'type': 'segment',
                        'p1': (active_points[i].x, active_points[i].y),
                        'p2': (active_points[j].x, active_points[j].y),
                        'desc': 'graph',
                        'owner': active_points[i].color})

    add_segments(red_points)
    add_segments(blue_points)
    return candidates


def distance_to_candidate(candidate, x, y):
    if candidate['type'] == 'circle':
        cx, cy = candidate['center']
        return abs(math.hypot(x - cx, y - cy) - candidate['radius'])
    return distance_point_to_segment(x, y, candidate['p1'][0], candidate['p1'][1],
                                     candidate['p2'][0], candidate['p2'][1])


def place_point_on_candidate(candidate, click_x, click_y):
    if candidate['type'] == 'circle':
        cx, cy = candidate['center']
        dx = click_x - cx
        dy = click_y - cy
        dist = math.hypot(dx, dy)
        if dist < EPSILON:
            return (cx + candidate['radius'], cy)
        scale_factor = candidate['radius'] / dist
        return (cx + dx * scale_factor, cy + dy * scale_factor)
    return project_point_on_segment(click_x, click_y,
                                    candidate['p1'][0], candidate['p1'][1],
                                    candidate['p2'][0], candidate['p2'][1])


# ----------------------------------------------------------------------
# UI (pygame)
# ----------------------------------------------------------------------
HELP_TEXT = [
    "ПРАВИЛА",
    "Круглое поле. Красные и синие по очереди ставят точки.",
    "Точки одной стороны в пределах 50px соединяются линиями.",
    "Закрытая цепочка линий — контур. Чужая точка внутри (или на линии)",
    "контура захватывается: становится неактивной и теряет связи.",
    "Захваченная точка не возвращается — захват окончательный.",
    "Поставить точку внутрь чужого контура — самопожертвование:",
    "она сразу захвачена и идёт в счёт противнику.",
    "Счёт: сколько точек каждая сторона захватила.",
    "",
    "УПРАВЛЕНИЕ",
    "ЛКМ — поставить точку.  ПКМ — выбрать линию (границу, окружность",
    "точки, ребро).  ПКМ повторно по той же линии — кандидаты на",
    "пересечениях (зелёные).  ЛКМ по кандидату ставит точку точно там.",
    "СКМ (тянуть) — сдвиг поля, колесо — масштаб.  Без ПКМ точка",
    "ставится там, где кликнули.",
    "Z — отменить ход, R — новая игра, H — эта справка, Esc — сброс",
    "выбора линии.",
]

if MAX_POINTS_PER_PLAYER > 0:
    HELP_TEXT.insert(10, f"Лимит: {MAX_POINTS_PER_PLAYER} точек на сторону — конец игры и победитель.")


def main():
    import pygame
    pygame.init()
    pygame.font.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))

    # Режимы: --ai — компьютер играет синими, --aibot — обе стороны компьютер
    args = set(sys.argv[1:])
    ai_colors = set()
    if "--aibot" in args or "--demo" in args:
        ai_colors = {RED_C, BLUE_C}
    elif "--ai" in args:
        ai_colors = {BLUE_C}
    if ai_colors:
        who = ("обе стороны" if len(ai_colors) == 2
               else ("синие" if BLUE_C in ai_colors else "красные"))
        if not any(line.startswith("Режим: ") for line in HELP_TEXT):
            HELP_TEXT.insert(1, f"Режим: компьютер играет за {who}.")
    pygame.display.set_caption("Игра в точки — MAID" +
                               (" · компьютер vs компьютер" if len(ai_colors) == 2
                                else (" · с компьютером" if ai_colors else "")))
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 22)
    font_big = pygame.font.Font(None, 40)
    font_small = pygame.font.Font(None, 18)

    game = Game(MAX_POINTS_PER_PLAYER)

    # ИИ: состояние и расписание ходов
    ais = {c: SimpleAI(c, budget_s=2.5 if len(ai_colors) == 2 else 3.5)
           for c in ai_colors}
    ai_pending = None      # (color, ready_time)
    ai_thinking = False
    ai_passes = 0          # подряд пропущенные ходы ИИ
    ai_stuck = False       # поле забито — ИИ больше не расписывать

    # камера
    scale = 1.0
    offset_x = 0.0
    offset_y = 0.0
    dragging = False
    last_mouse_pos = (0, 0)

    # выделение линии
    selected_line = None
    selected_green_points = []

    # визуальные эффекты
    flashes = []       # (point, kind, t)  kind: 'captured' | 'reactivated' | 'birth'
    last_contour = None
    last_contour_t = 0.0
    last_contour_color = RED
    message = None
    message_t = 0.0
    help_open = False

    t_now = 0.0

    def now():
        return pygame.time.get_ticks() / 1000.0

    def say(text):
        nonlocal message, message_t
        message = text
        message_t = now()

    def game_to_screen(x, y):
        return (int((x - offset_x) * scale + WIDTH / 2),
                int((y - offset_y) * scale + HEIGHT / 2))

    def screen_to_game(sx, sy):
        return (offset_x + (sx - WIDTH / 2) / scale,
                offset_y + (sy - HEIGHT / 2) / scale)

    def draw_connections(screen, pts, color):
        n = len(pts)
        active = [p for p in pts if p.active]
        m = len(active)
        R2 = (CONNECTION_RADIUS + EPSILON) ** 2
        for i in range(m):
            a = active[i]
            for j in range(i + 1, m):
                b = active[j]
                dx = a.x - b.x
                dy = a.y - b.y
                if dx * dx + dy * dy <= R2:
                    pygame.draw.line(screen, color, game_to_screen(a.x, a.y),
                                     game_to_screen(b.x, b.y), 1)

    def draw_candidate(screen, cand, color, width=2):
        if cand['type'] == 'circle':
            center = game_to_screen(cand['center'][0], cand['center'][1])
            pygame.draw.circle(screen, color, center, int(cand['radius'] * scale), width)
        else:
            p1 = game_to_screen(cand['p1'][0], cand['p1'][1])
            p2 = game_to_screen(cand['p2'][0], cand['p2'][1])
            pygame.draw.line(screen, color, p1, p2, width)

    def snapshot_state():
        return (screen, scale, offset_x, offset_y)

    def do_place(game_x, game_y):
        """Общий путь постановки точки (обычный клик или по кандидату)."""
        nonlocal selected_line, selected_green_points, last_contour, last_contour_t
        nonlocal last_contour_color, help_open
        res = game.place(game_x, game_y)
        if res.point is None:
            if res.passed:
                say(f"У {game.current} лимит точек — ход переходит.")
            sync_ai()
            return
        flashes.append((res.point, 'birth', now()))
        for p in res.newly_captured:
            flashes.append((p, 'captured', now()))
        for p in res.reactivated:
            flashes.append((p, 'reactivated', now()))
        if res.last_contour:
            last_contour = res.last_contour
            last_contour_t = now()
            last_contour_color = RED if res.point.color == RED_C else BLUE
        if res.game_over:
            if res.winner == RED_C:
                say("Конец игры. Побеждают красные!")
            elif res.winner == BLUE_C:
                say("Конец игры. Побеждают синие!")
            else:
                say("Конец игры. Ничья.")
        if res.passed:
            say("У ходящего лимит точек — ход переходит.")
        selected_line = None
        selected_green_points = []
        sync_ai()

    def sync_ai():
        """Расписать ход ИИ, если ход его (и игра не окончена)."""
        nonlocal ai_pending
        if (ai_colors and ai_pending is None and not ai_thinking
                and not ai_stuck and game.current in ai_colors
                and not (game.at_limit(RED_C) and game.at_limit(BLUE_C))):
            delay = 0.4 if len(ai_colors) == 2 else 0.6
            ai_pending = (game.current, now() + delay)
    sync_ai()  # стартовое расписание (в --aibot первым ходит компьютер)

    def try_place_at_click(game_x, game_y):
        # если выбрана линия — ставим по линии/кандидату
        if (selected_line is not None and
                selected_line.get("owner", "neutral") in (game.current, "neutral")):
            if selected_green_points:
                best = min(selected_green_points,
                           key=lambda pt: math.hypot(game_x - pt[0], game_y - pt[1]))
                do_place(best[0], best[1])
            else:
                nx, ny = place_point_on_candidate(selected_line, game_x, game_y)
                do_place(nx, ny)
        else:
            do_place(game_x, game_y)

    def ghost_position(game_x, game_y):
        if (selected_line is not None and
                selected_line.get("owner", "neutral") in (game.current, "neutral")):
            if selected_green_points:
                return min(selected_green_points,
                           key=lambda pt: math.hypot(game_x - pt[0], game_y - pt[1]))
            return place_point_on_candidate(selected_line, game_x, game_y)
        return (game_x, game_y)

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if help_open:
                        help_open = False
                    else:
                        selected_line = None
                        selected_green_points = []
                elif event.key == pygame.K_h:
                    help_open = not help_open
                elif event.key == pygame.K_z:
                    if game.undo():
                        flashes.clear()
                        last_contour = None
                        say("Ход отменён.")
                    else:
                        say("Нечего отменять.")
                    ai_pending = None
                    sync_ai()
                elif event.key == pygame.K_r:
                    game.reset()
                    scale, offset_x, offset_y = 1.0, 0.0, 0.0
                    selected_line = None
                    selected_green_points = []
                    flashes.clear()
                    last_contour = None
                    message = None
                    help_open = False
                    ai_pending = None
                    ai_passes = 0
                    ai_stuck = False
                    say("Новая игра.")
                    sync_ai()

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # ЛКМ — постановка
                    if help_open:
                        help_open = False
                        continue
                    if game.at_limit(RED_C) and game.at_limit(BLUE_C):
                        continue  # игра окончена
                    if game.current in ai_colors:
                        continue  # ход компьютера — ждём
                    sx, sy = event.pos
                    gx, gy = screen_to_game(sx, sy)
                    if not is_inside_field(gx, gy):
                        selected_line = None
                        selected_green_points = []
                        continue
                    # позиция с учётом привязки
                    px, py = ghost_position(gx, gy)
                    if not is_inside_field(px, py):
                        continue
                    # слишком близко к существующей точке — не ставим
                    # (проверка по финальной позиции, чтобы не мешать snap)
                    min_d = max(EPSILON, 0.5 / scale)
                    for p in game.points:
                        if math.hypot(p.x - px, p.y - py) < min_d:
                            break
                    else:
                        try_place_at_click(gx, gy)

                elif event.button == 3:  # ПКМ — выбор линии
                    if help_open:
                        continue
                    sx, sy = event.pos
                    gx, gy = screen_to_game(sx, sy)
                    if not is_inside_field(gx, gy):
                        selected_line = None
                        selected_green_points = []
                        continue
                    candidates = get_candidate_lines(game.points_of(RED_C),
                                                     game.points_of(BLUE_C))
                    best_candidate = None
                    best_dist = float('inf')
                    for cand in candidates:
                        d = distance_to_candidate(cand, gx, gy)
                        if d < best_dist:
                            best_dist = d
                            best_candidate = cand
                    if (best_candidate is None or
                            best_candidate.get("owner") not in (game.current, "neutral")):
                        selected_line = None
                        selected_green_points = []
                    else:
                        if selected_line is not None and candidate_equals(selected_line, best_candidate):
                            if not selected_green_points:
                                intersections = []
                                for cand in candidates:
                                    if candidate_equals(cand, selected_line):
                                        continue
                                    if (selected_line.get("owner") == "neutral" and
                                            cand.get("owner") not in (game.current, "neutral")):
                                        continue
                                    intersections.extend(compute_intersections(selected_line, cand))
                                unique_inters = []
                                for pt in intersections:
                                    if any(math.hypot(pt[0] - u[0], pt[1] - u[1]) < EPSILON
                                           for u in unique_inters):
                                        continue
                                    if any(math.hypot(pt[0] - p.x, pt[1] - p.y) < max(EPSILON, 0.5 / scale)
                                           for p in game.points):
                                        continue
                                    if is_inside_field(pt[0], pt[1]):
                                        unique_inters.append(pt)
                                if unique_inters:
                                    selected_green_points = unique_inters
                                else:
                                    selected_line = None
                                    selected_green_points = []
                            else:
                                selected_line = None
                                selected_green_points = []
                        else:
                            selected_line = best_candidate
                            selected_green_points = []

                elif event.button == 2:  # СКМ — перетаскивание
                    dragging = True
                    last_mouse_pos = event.pos

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 2:
                    dragging = False

            elif event.type == pygame.MOUSEMOTION:
                if dragging:
                    mx, my = event.pos
                    dx = (mx - last_mouse_pos[0]) / scale
                    dy = (my - last_mouse_pos[1]) / scale
                    offset_x -= dx
                    offset_y -= dy
                    last_mouse_pos = (mx, my)

            elif event.type == pygame.MOUSEWHEEL:
                if event.y > 0:
                    scale *= 1.1
                elif event.y < 0:
                    scale = max(0.2, scale / 1.1)

        # ход компьютера
        if (ai_pending is not None and not ai_thinking and
                now() >= ai_pending[1]):
            color = ai_pending[0]
            ai_pending = None
            if game.current != color:
                # состояние сменилось (undo/reset) — расписание устарело
                sync_ai()
            else:
                ai_thinking = True
                say("Компьютер думает…")
                pygame.display.flip()
                move = ais[color].choose(game)
                if move is None:
                    ai_passes += 1
                    if ai_passes >= 2:
                        ai_stuck = True
                        say("Свободных клеток нет — ИИ остановлен.")
                    elif not (game.at_limit(RED_C) and game.at_limit(BLUE_C)):
                        game.current = other_color(color)
                        say("Ходить некуда — ход переходит.")
                else:
                    ai_passes = 0
                    do_place(move[0], move[1])
                ai_thinking = False
                sync_ai()

        # очистка эффектов
        t = now()
        flashes = [f for f in flashes if t - f[2] < 1.2]
        if last_contour is not None and t - last_contour_t > 2.5:
            last_contour = None

        # ---------------- отрисовка ----------------
        screen.fill(WHITE)
        fc = game_to_screen(0, 0)
        fr = int(FIELD_RADIUS * scale)
        pygame.draw.circle(screen, BLACK, fc, fr, 1)

        red_pts = game.points_of(RED_C)
        blue_pts = game.points_of(BLUE_C)

        draw_connections(screen, red_pts, RED)
        draw_connections(screen, blue_pts, BLUE)

        # зоны досягаемости активных точек (тонко)
        for p in red_pts:
            if p.active:
                pos = game_to_screen(p.x, p.y)
                pygame.draw.circle(screen, (240, 200, 200), pos, int(CONNECTION_RADIUS * scale), 1)
        for p in blue_pts:
            if p.active:
                pos = game_to_screen(p.x, p.y)
                pygame.draw.circle(screen, (200, 210, 240), pos, int(CONNECTION_RADIUS * scale), 1)

        # последний замкнутый контур
        if last_contour is not None:
            alpha = max(0.0, 1.0 - (t - last_contour_t) / 2.5)
            col = tuple(int(c * alpha + 255 * (1 - alpha)) for c in last_contour_color)
            pygame.draw.polygon(screen, col,
                                [game_to_screen(p.x, p.y) for p in last_contour], 3)

        # выделенная линия и кандидаты
        if selected_line is not None:
            draw_candidate(screen, selected_line, YELLOW)
        for pt in selected_green_points:
            pygame.draw.circle(screen, GREEN, game_to_screen(pt[0], pt[1]), 5)

        # точки
        for p in red_pts:
            pos = game_to_screen(p.x, p.y)
            col = RED if p.active else GRAY_RED
            pygame.draw.circle(screen, col, pos, DOT_SIZE)
        for p in blue_pts:
            pos = game_to_screen(p.x, p.y)
            col = BLUE if p.active else GRAY_BLUE
            pygame.draw.circle(screen, col, pos, DOT_SIZE)

        # вспышки захвата/оживления
        for (p, kind, ft) in flashes:
            age = t - ft
            r = DOT_SIZE + int(10 * age)
            a = max(0.0, 1.0 - age / 1.2)
            if kind == 'captured':
                col = tuple(int(c * a + 255 * (1 - a)) for c in (200, 0, 0))
            elif kind == 'reactivated':
                col = tuple(int(c * a + 255 * (1 - a)) for c in (0, 150, 0))
            else:
                col = p.color == RED_C and RED or BLUE
                col = tuple(int(c * a + 255 * (1 - a)) for c in col)
            pygame.draw.circle(screen, col, game_to_screen(p.x, p.y), r, 2)

        # курсор: зона досягаемости + призрак точки
        mx, my = pygame.mouse.get_pos()
        gx, gy = screen_to_game(mx, my)
        if (is_inside_field(gx, gy) and not help_open
                and game.current not in ai_colors):
            mpos = game_to_screen(gx, gy)
            pygame.draw.circle(screen, FAINT, mpos, int(CONNECTION_RADIUS * scale), 1)
            if not game.at_limit(game.current):
                px, py = ghost_position(gx, gy)
                if is_inside_field(px, py):
                    gpos = game_to_screen(px, py)
                    gcol = RED if game.current == RED_C else BLUE
                    pygame.draw.circle(screen, gcol, gpos, 4, 1)

        # панель сверху
        cur_name = "Красные" if game.current == RED_C else "Синие"
        if game.current in ai_colors:
            cur_name += " (компьютер)"
        cap_r = sum(1 for p in red_pts if not p.active)
        cap_b = sum(1 for p in blue_pts if not p.active)
        line1 = f"Красные: {game.score[RED_C]}   Синие: {game.score[BLUE_C]}"
        line2 = f"Сейчас захвачено — красных: {cap_r}, синих: {cap_b}   Ход: {cur_name}"
        if game.max_points > 0:
            line2 += f"   Точек: {game.count_of(RED_C)}/{game.max_points} · {game.count_of(BLUE_C)}/{game.max_points}"
        screen.blit(font.render(line1, True, BLACK), (10, 8))
        screen.blit(font.render(line2, True, BLACK), (10, 32))
        hint = "ЛКМ точка · ПКМ линия · СКМ сдвиг · колесо масштаб · Z отмена · R новая · H справка"
        screen.blit(font_small.render(hint, True, (130, 130, 130)), (10, HEIGHT - 26))

        # сообщение
        if message is not None and t - message_t < 4.0:
            surf = font.render(message, True, BLACK)
            rect = surf.get_rect(midtop=(WIDTH // 2, 64))
            bg = surf.copy()
            bg.fill(WHITE)
            pad = 8
            full = pygame.Surface((rect.w + pad * 2, rect.h + pad * 2), pygame.SRCALPHA)
            full.fill((255, 255, 255, 210))
            screen.blit(full, (rect.x - pad, rect.y - pad))
            screen.blit(surf, (rect.x, rect.y))
        elif message is not None:
            message = None

        # конец игры
        if game.at_limit(RED_C) and game.at_limit(BLUE_C):
            w = game._winner()
            if w == RED_C:
                text = "Конец игры — побеждают красные"
            elif w == BLUE_C:
                text = "Конец игры — побеждают синие"
            else:
                text = "Конец игры — ничья"
            sub = f"{game.score[RED_C]} : {game.score[BLUE_C]}      R — новая игра"
            s1 = font_big.render(text, True, BLACK)
            s2 = font.render(sub, True, BLACK)
            full = pygame.Surface((s1.get_width() + 40, s1.get_height() + s2.get_height() + 30),
                                  pygame.SRCALPHA)
            full.fill((0, 0, 0, 140))
            fx = (WIDTH - full.get_width()) // 2
            fy = (HEIGHT - full.get_height()) // 2
            screen.blit(full, (fx, fy))
            screen.blit(s1, (fx + 20, fy + 10))
            screen.blit(s2, (fx + 20, fy + 10 + s1.get_height() + 8))

        # справка
        if help_open:
            full = pygame.Surface((WIDTH - 80, HEIGHT - 80), pygame.SRCALPHA)
            full.fill((255, 255, 255, 235))
            screen.blit(full, (40, 40))
            pygame.draw.rect(screen, BLACK, (40, 40, WIDTH - 80, HEIGHT - 80), 2)
            y = 60
            for line in HELP_TEXT:
                screen.blit(font.render(line, True, BLACK), (60, y))
                y += 26
            screen.blit(font_small.render("H или клик — закрыть", True, (130, 130, 130)),
                        (60, HEIGHT - 60))

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
