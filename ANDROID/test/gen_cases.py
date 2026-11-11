#!/usr/bin/env python3
"""Генерация позиций + Python-ссылка (быстрый предикат + перебор) для
дифференциального теста JS-порта. Вывод: cases.json + ref_py.json."""
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "MAID"))
import test_oracle as oracle  # noqa: E402
import dotgame_maid as dm     # noqa: E402


def make_struct(pts, R):
    class P:
        __slots__ = ("x", "y")
        def __init__(s, t):
            s.x = t[0]; s.y = t[1]
    st = dm.ColorStructure()
    st.rebuild([P(t) for t in pts], R)
    return st


def random_case_ext(kind, rng):
    R = 2.2
    if kind in ("grid", "clique", "scattered"):
        return oracle.random_case(kind, rng)
    if kind == "line":
        n = rng.randint(3, 6)
        pts = [(i * R * 0.7 + rng.uniform(-0.02, 0.02), rng.uniform(-0.02, 0.02)) for i in range(n)]
        qs = [(rng.uniform(-1, n * R), rng.uniform(-1, 1)) for _ in range(8)]
        return pts, R, qs
    if kind == "near_collinear":
        n = rng.randint(4, 6)
        pts = [(i * R * 0.6, rng.uniform(-0.35, 0.35)) for i in range(n)]
        qs = [(rng.uniform(-1, n * R), rng.uniform(-1, 1.5)) for _ in range(10)]
        return pts, R, qs
    if kind == "nested":
        s1, s2 = R * 0.9, R * 0.4
        pts = [(-s1, -s1), (s1, -s1), (s1, s1), (-s1, s1),
               (-s2, -s2), (s2, -s2), (s2, s2), (-s2, s2)]
        qs = [(0, 0), (s2 * 0.5, 0), (0, (s1 + s2) / 2)]
        for _ in range(4):
            qs.append((rng.uniform(-s1, s1), rng.uniform(-s1, s1)))
        return pts, R, qs
    if kind == "crossing":
        a = R * 0.8
        pts = [(-a, -a), (a, a), (a, -a), (-a, a)]
        qs = [(0, 0), (a * 0.5, 0), (0, a * 0.5)]
        for _ in range(4):
            qs.append((rng.uniform(-a, a), rng.uniform(-a, a)))
        return pts, R, qs
    if kind == "shared_edge":
        pts = [(0, 0), (R * 0.9, 0), (R * 0.45, R * 0.78), (R * 0.45, -R * 0.78)]
        qs = [(R * 0.45, R * 0.3), (R * 0.45, -R * 0.3), (R * 0.45, 0)]
        for _ in range(4):
            qs.append((rng.uniform(-0.5, R * 1.4), rng.uniform(-R, R)))
        return pts, R, qs
    if kind == "on_boundary":
        pts = [(0, 0), (R * 0.9, 0), (R * 0.45, R * 0.78)]
        qs = [(0, 0), (R * 0.9, 0), (R * 0.45, R * 0.78),
              (R * 0.45, 0), (R * 0.225, R * 0.39), (R * 0.675, R * 0.39)]
        return pts, R, qs
    raise ValueError(kind)


def main():
    kinds = ["grid", "clique", "scattered", "line", "near_collinear",
             "nested", "crossing", "shared_edge", "on_boundary"]
    rng = random.Random(20261110)
    N = 1500
    cases = []
    ref_py = []   # параллельно cases: список ответов [fast_py, ref] на каждый запрос
    total_q = 0
    for it in range(N):
        kind = kinds[it % len(kinds)]
        pts, R, qs = random_case_ext(kind, rng)
        st = make_struct(pts, R)
        case = {"pts": pts, "R": R, "qs": qs}
        cases.append(case)
        row = []
        for X in qs:
            # Python быстрый предикат
            try:
                fast_py = st.query(X)
            except RuntimeError:
                fast_py = None
            # эталон
            try:
                ref = oracle.bf_predicate(X, pts, R)
            except RuntimeError:
                ref = oracle.clique_analytic(pts, R, X)
            row.append([fast_py, ref])
            if ref is not None:
                total_q += 1
        ref_py.append(row)
    out = os.path.join(HERE, "cases.json")
    with open(out, "w") as f:
        json.dump(cases, f)
    out2 = os.path.join(HERE, "ref_py.json")
    with open(out2, "w") as f:
        json.dump(ref_py, f)
    print(f"cases={N} total_queries_with_ref={total_q}")
    print("wrote", out, out2)


if __name__ == "__main__":
    main()
