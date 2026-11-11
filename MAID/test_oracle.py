#!/usr/bin/env python3
"""Оракул для геометрического предиката «точка в контуре».

Самодостаточный модуль (не зависит от dotgame_maid): генерирует случайные
позиции и даёт эталонный ответ полным перебором простых циклов графа.
Используется test_maid.py, чтобы сверять быстрый предикат (планарное
вложение + обход граней) с перебором.

Определение: X «внутри какого-либо контура» <=> X лежит на линии какого-либо
простого цикла графа соединений ИЛИ внутри его полигона.
"""
import math

GEPS = 1e-9
ON_EPS = 1e-5


def _dist2(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _point_seg_dist2(px, py, a, b):
    vx, vy = b[0] - a[0], b[1] - a[1]
    L2 = vx * vx + vy * vy
    if L2 < GEPS:
        return _dist2((px, py), a)
    t = ((px - a[0]) * vx + (py - a[1]) * vy) / L2
    if t < 0:
        return _dist2((px, py), a)
    if t > 1:
        return _dist2((px, py), b)
    cx = a[0] + t * vx
    cy = a[1] + t * vy
    return _dist2((px, py), (cx, cy))


def _on_segment(X, a, b):
    return _point_seg_dist2(X[0], X[1], a, b) < ON_EPS * ON_EPS


def _pip(cycle, X):
    """Точка в простом полигоне (even-odd) или на его границе."""
    m = len(cycle)
    for i in range(m):
        if _on_segment(X, cycle[i], cycle[(i + 1) % m]):
            return True
    inside = False
    j = m - 1
    for i in range(m):
        xi, yi = cycle[i]
        xj, yj = cycle[j]
        if (yi > X[1]) != (yj > X[1]):
            xints = (xj - xi) * (X[1] - yi) / (yj - yi) + xi
            if X[0] < xints:
                inside = not inside
        j = i
    return inside


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


def random_case(kind, rng):
    """Возвращает (pts, R, qs): точки, радиус соединения, запросы."""
    R = 2.2
    if kind == "grid":
        cols = rng.choice((2, 3))
        rows = rng.choice((2, 3))
        sp = R * 0.8
        pts = []
        for r in range(rows):
            for c in range(cols):
                pts.append((c * sp + rng.uniform(-0.05, 0.05),
                            r * sp + rng.uniform(-0.05, 0.05)))
        qs = []
        for r in range(rows - 1):
            for c in range(cols - 1):
                qs.append(((c + 0.5) * sp, (r + 0.5) * sp))
        for _ in range(8):
            qs.append((rng.uniform(-0.5, (cols - 1) * sp + 0.5),
                       rng.uniform(-0.5, (rows - 1) * sp + 0.5)))
        return pts, R, qs
    if kind == "clique":
        n = rng.randint(4, 6)
        pts = []
        for _ in range(n):
            a = rng.uniform(0, 2 * math.pi)
            r = rng.uniform(0, R * 0.45)
            pts.append((r * math.cos(a), r * math.sin(a)))
        qs = []
        for _ in range(10):
            a = rng.uniform(0, 2 * math.pi)
            r = rng.uniform(0, R * 0.9)
            qs.append((r * math.cos(a), r * math.sin(a)))
        return pts, R, qs
    # scattered
    n = rng.randint(4, 8)
    pts = [(rng.uniform(0, 6), rng.uniform(0, 6)) for _ in range(n)]
    qs = [(rng.uniform(-1, 7), rng.uniform(-1, 7)) for _ in range(10)]
    return pts, R, qs


def bf_predicate(X, pts, R):
    """Эталон: полный перебор простых циклов. True, если X в/на каком-либо.

    Бюджет ограничен: при исчерпании (клики дают экспоненциально много
    циклов) бросает RuntimeError — вызывающий переходит на clique_analytic.
    """
    n = len(pts)
    if n < 3:
        return False
    R2 = (R + ON_EPS) ** 2
    adj = [[] for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if _dist2(pts[i], pts[j]) <= R2:
                adj[i].append(j)
                adj[j].append(i)
    budget = [300000]

    def dfs(s, cur, path, visited):
        if budget[0] <= 0:
            raise RuntimeError("budget exhausted")
        budget[0] -= 1
        for nb in adj[cur]:
            if nb == s and len(path) >= 3:
                if _pip([pts[i] for i in path], X):
                    return True
            elif nb > s and nb not in visited:
                visited.add(nb)
                path.append(nb)
                if dfs(s, nb, path, visited):
                    return True
                path.pop()
                visited.remove(nb)
        return False

    for s in range(n):
        if dfs(s, s, [s], {s}):
            return True
    return False


def clique_analytic(pts, R, X):
    """Аналитика для клики: в полном графе X в каком-либо цикле <=> X в
    (или на) выпуклой оболочке. Возвращает None, если pts не клика."""
    R2 = (R + ON_EPS) ** 2
    n = len(pts)
    for i in range(n):
        for j in range(i + 1, n):
            if _dist2(pts[i], pts[j]) > R2:
                return None
    hull = _convex_hull(pts)
    return _pip(hull, X)
