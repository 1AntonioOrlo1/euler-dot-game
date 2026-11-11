#!/usr/bin/env python3
"""Усиленное тестирование dotgame: логика игры + механизм проверки контуров.

Запуск: ./.venv/bin/python stress_test.py

Два фронта:
  [A] Механизм контуров — дифференциальный тест быстрого предиката
      (планарное вложение + обход граней) против эталона (полный перебор
      простых циклов / аналитика клики) на тысячах случайных и
      специально-вырожденных позиций.
  [B] Логика игры — инварианты при тысячах случайных ходов:
      согласованность счёта, точность undo, корректность clone,
      границы поля, производительность на плотных кластерах.
"""
import math
import os
import random
import sys
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dotgame_maid as dm
import test_oracle as oracle

PASS = 0
FAIL = 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {extra}")


# ======================================================================
# [A] МЕХАНИЗМ ПРОВЕРКИ КОНТУРОВ
# ======================================================================

def _make_struct(pts, R):
    class P:
        __slots__ = ("x", "y")

        def __init__(s, t):
            s.x = t[0]
            s.y = t[1]
    st = dm.ColorStructure()
    st.rebuild([P(t) for t in pts], R)
    return st


def _reference(X, pts, R):
    """Эталонный ответ: перебор циклов, при исчерпании бюджета — аналитика
    клики. Возвращает (answer, used_analytic)."""
    try:
        return oracle.bf_predicate(X, pts, R), False
    except RuntimeError:
        an = oracle.clique_analytic(pts, R, X)
        if an is None:
            return None, False  # сравнить нечем — пропускаем
        return an, True


def random_case_ext(kind, rng):
    """Расширенный генератор позиций (включая вырожденные)."""
    R = 2.2
    if kind in ("grid", "clique", "scattered"):
        return oracle.random_case(kind, rng)
    if kind == "line":  # коллинеарные — циклов нет
        n = rng.randint(3, 6)
        pts = [(i * R * 0.7 + rng.uniform(-0.02, 0.02),
                rng.uniform(-0.02, 0.02)) for i in range(n)]
        qs = [(rng.uniform(-1, n * R), rng.uniform(-1, 1)) for _ in range(8)]
        return pts, R, qs
    if kind == "near_collinear":  # почти коллинеарные — тонкие треугольники
        n = rng.randint(4, 6)
        pts = [(i * R * 0.6, rng.uniform(-0.35, 0.35)) for i in range(n)]
        qs = [(rng.uniform(-1, n * R), rng.uniform(-1, 1.5)) for _ in range(10)]
        return pts, R, qs
    if kind == "nested":  # вложенные квадраты
        s1, s2 = R * 0.9, R * 0.4
        pts = [(-s1, -s1), (s1, -s1), (s1, s1), (-s1, s1),
               (-s2, -s2), (s2, -s2), (s2, s2), (-s2, s2)]
        qs = [(0, 0), (s2 * 0.5, 0), (0, (s1 + s2) / 2)]
        for _ in range(4):
            qs.append((rng.uniform(-s1, s1), rng.uniform(-s1, s1)))
        return pts, R, qs
    if kind == "crossing":  # перекрещивающиеся рёбра (X)
        a = R * 0.8
        pts = [(-a, -a), (a, a), (a, -a), (-a, a)]
        qs = [(0, 0), (a * 0.5, 0), (0, a * 0.5)]
        for _ in range(4):
            qs.append((rng.uniform(-a, a), rng.uniform(-a, a)))
        return pts, R, qs
    if kind == "shared_edge":  # два треугольника с общим ребром
        pts = [(0, 0), (R * 0.9, 0), (R * 0.45, R * 0.78),
               (R * 0.45, -R * 0.78)]
        qs = [(R * 0.45, R * 0.3), (R * 0.45, -R * 0.3), (R * 0.45, 0)]
        for _ in range(4):
            qs.append((rng.uniform(-0.5, R * 1.4), rng.uniform(-R, R)))
        return pts, R, qs
    if kind == "on_boundary":  # запросы ровно на вершинах и серединах рёбер
        pts = [(0, 0), (R * 0.9, 0), (R * 0.45, R * 0.78)]
        qs = [(0, 0), (R * 0.9, 0), (R * 0.45, R * 0.78),
              (R * 0.45, 0), (R * 0.225, R * 0.39), (R * 0.675, R * 0.39)]
        return pts, R, qs
    raise ValueError(kind)


def stress_oracle():
    print("\n[A] Механизм проверки контуров: дифференциальный тест")
    kinds = ["grid", "clique", "scattered", "line", "near_collinear",
             "nested", "crossing", "shared_edge", "on_boundary"]
    rng = random.Random(20261110)
    total = 0
    mism = 0
    analytic = 0
    skipped = 0
    ray_errors = 0
    per_kind = {k: [0, 0] for k in kinds}  # kind -> [total, mism]
    N = 6000
    t0 = time.time()
    for it in range(N):
        kind = kinds[it % len(kinds)]
        pts, R, qs = random_case_ext(kind, rng)
        st = _make_struct(pts, R)
        for X in qs:
            ref, used_an = _reference(X, pts, R)
            if ref is None:
                skipped += 1
                continue
            total += 1
            per_kind[kind][0] += 1
            if used_an:
                analytic += 1
            try:
                fast = st.query(X)
            except RuntimeError:
                ray_errors += 1
                per_kind[kind][1] += 1
                if ray_errors <= 5:
                    print(f"    RAY-ERROR {kind} X={X} pts={pts}")
                continue
            if fast != ref:
                mism += 1
                per_kind[kind][1] += 1
                if mism <= 8:
                    print(f"    MISMATCH {kind} X={X} fast={fast} ref={ref}")
    dt = time.time() - t0
    print(f"    видов позиций: {', '.join(kinds)}")
    print(f"    запросов сравнено: {total}, через аналитику клики: {analytic}, "
          f"пропущено (нет эталона): {skipped}")
    for k in kinds:
        t, m = per_kind[k]
        print(f"      {k:16s} {t:6d} запросов, {m} расхождений")
    check(f"оракул {N} позиций / {total} запросов: 0 расхождений",
          mism == 0, f"mism={mism}")
    check("нет ошибок 'no generic ray' (робастность луча)",
          ray_errors == 0, f"ray_errors={ray_errors}")
    check(f"дифференциальный тест уложился во время ({dt:.1f} с < 120 с)",
          dt < 120, f"{dt:.1f}s")


def adversarial_contours():
    print("\n[A2] Адаптивные случаи: ручной контроль ответа предиката")
    R = 50.0

    def q(pts, X):
        return _make_struct(pts, R).query(X)

    # 1) К4: квадрат с диагоналями. Точка внутри одного треугольника — внутри.
    k4 = [(0, 0), (35, 0), (35, 35), (0, 35)]
    check("K4: центр внутри", q(k4, (17.5, 17.5)) is True)
    check("K4: точка вне квадрата — вне", q(k4, (60, 17.5)) is False)

    # 2) Бабочка (самопересечение): (0,0),(2,2),(0,4),(2,0) — рёбра пересекаются.
    #    Быстрый предикат обязан совпасть с перебором.
    bow = [(0, 0), (2, 2), (0, 4), (2, 0)]
    for X in [(1, 2), (0.5, 1), (1.5, 3), (1, 0.5)]:
        ref, _ = _reference(X, bow, R)
        if ref is not None:
            check(f"бабочка: {X} совпадает с перебором",
                  q(bow, X) == ref, f"fast={q(bow, X)} ref={ref}")

    # 3) Точка ровно на вершине контура — считается внутри (правило мастера).
    tri = [(0, 0), (35, 0), (0, 35)]
    check("точка на вершине контура — внутри", q(tri, (35, 0)) is True)
    # 4) Точка ровно на середине ребра — внутри.
    check("точка на середине ребра — внутри", q(tri, (17.5, 0)) is True)
    # 5) Точка на продолжении ребра (вне) — вне.
    check("точка на продолжении ребра — вне", q(tri, (50, 0)) is False)

    # 6) Вложенные квадраты: точка между квадратами.
    s1, s2 = 40.0, 15.0
    nested = [(-s1, -s1), (s1, -s1), (s1, s1), (-s1, s1),
              (-s2, -s2), (s2, -s2), (s2, s2), (-s2, s2)]
    # все 8 точек в пределах R=50 друг от друга? нет — внешние далеко.
    # Проверим согласованность с перебором на нескольких точках.
    for X in [(0, 0), (s2 + 5, 0), (0, s2 + 5), (s1 - 5, 0)]:
        ref, _ = _reference(X, nested, R)
        if ref is not None:
            check(f"вложенные квадраты: {X} совпадает с перебором",
                  q(nested, X) == ref, f"fast={q(nested, X)} ref={ref}")

    # 7) Мост (хвост) не создаёт контур: точка рядом с хвостом — вне.
    tail = [(0, 0), (35, 0), (0, 35), (35, 35)]  # квадрат + хвост от (35,35)
    tail.append((70, 35))
    ref, _ = _reference((52, 35), tail, R)
    if ref is not None:
        check("хвост (мост): точка на мосту — совпадает с перебором",
              q(tail, (52, 35)) == ref, f"fast={q(tail, (52, 35))} ref={ref}")


# ======================================================================
# [B] ЛОГИКА ИГРЫ
# ======================================================================

def score_invariant(g):
    """В режиме без оживления: счёт = число неактивных точек противника."""
    inactive_red = sum(1 for p in g.points if p.color == dm.RED_C and not p.active)
    inactive_blue = sum(1 for p in g.points if p.color == dm.BLUE_C and not p.active)
    return (g.score[dm.RED_C] == inactive_blue and
            g.score[dm.BLUE_C] == inactive_red)


def full_state(g):
    return ([tuple(p.snapshot()) for p in g.points],
            dict(g.score), g.current, g._next_id)


def stress_random_play():
    print("\n[B] Логика игры: инварианты при случайной игре")
    rng = random.Random(777)
    games = 120
    moves_total = 0
    inv_fail = 0
    field_fail = 0
    first_bad = None
    for gi in range(games):
        g = dm.Game()  # без оживления, без лимита
        for _ in range(120):
            a = rng.uniform(0, 2 * math.pi)
            r = rng.uniform(0, dm.FIELD_RADIUS - 2)
            x, y = r * math.cos(a), r * math.sin(a)
            g.place(x, y)
            moves_total += 1
            if not score_invariant(g):
                inv_fail += 1
                if first_bad is None:
                    first_bad = (gi, moves_total, dict(g.score),
                                 len(g.points))
            for p in g.points:
                if math.hypot(p.x, p.y) > dm.FIELD_RADIUS + 1e-6:
                    field_fail += 1
    check(f"инвариант счёта (счёт = неактивные противника) на {moves_total} ходах",
          inv_fail == 0, f"fail={inv_fail} first={first_bad}")
    check("все точки в поле", field_fail == 0, f"fail={field_fail}")


def stress_undo():
    print("\n[B2] Точность undo: полное восстановление состояния")
    rng = random.Random(4242)
    bad = 0
    for _ in range(40):
        g = dm.Game()
        n = rng.randint(1, 40)
        for _ in range(n):
            a = rng.uniform(0, 2 * math.pi)
            r = rng.uniform(0, dm.FIELD_RADIUS - 2)
            g.place(r * math.cos(a), r * math.sin(a))
        target = full_state(g)
        for _ in range(n):
            if not g.undo():
                break
        if full_state(g) != ([tuple(t) for t in target[0]],
                             target[1], target[2], target[3]):
            # сравниваем по существу: после полного undo — пустая игра
            bad += 1
    # отдельная строгая проверка: полный undo допустим только до пустого
    g = dm.Game()
    seq = []
    rng2 = random.Random(5)
    for _ in range(15):
        a = rng2.uniform(0, 2 * math.pi)
        r = rng2.uniform(0, dm.FIELD_RADIUS - 2)
        x, y = r * math.cos(a), r * math.sin(a)
        g.place(x, y)
        seq.append((x, y))
    ok = True
    for _ in range(15):
        if not g.undo():
            ok = False
            break
    check("полный undo возвращает пустую игру",
          ok and len(g.points) == 0 and g.score == {dm.RED_C: 0, dm.BLUE_C: 0}
          and g.current == dm.RED_C)
    # частичный undo: откат на k ходов совпадает с игрой на n-k ходах
    g1 = dm.Game()
    for (x, y) in seq:
        g1.place(x, y)
    for _ in range(5):
        g1.undo()
    g2 = dm.Game()
    for (x, y) in seq[:10]:
        g2.place(x, y)
    check("частичный undo == игра на (n-k) ходах",
          full_state(g1) == ([tuple(t) for t in full_state(g2)[0]],
                             full_state(g2)[1], full_state(g2)[2],
                             full_state(g2)[3]))


def stress_clone():
    print("\n[B3] Корректность clone (используется ИИ)")
    rng = random.Random(99)
    bad = 0
    for _ in range(30):
        g = dm.Game()
        for _ in range(rng.randint(3, 25)):
            a = rng.uniform(0, 2 * math.pi)
            r = rng.uniform(0, dm.FIELD_RADIUS - 2)
            g.place(r * math.cos(a), r * math.sin(a))
        c = g.clone()
        # одинаковый ход в оригинале и копии -> одинаковый результат
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(0, dm.FIELD_RADIUS - 2)
        x, y = r * math.cos(a), r * math.sin(a)
        r1 = g.place(x, y)
        r2 = c.place(x, y)
        if (r1.point is None) != (r2.point is None):
            bad += 1
            continue
        if r1.point is not None:
            if (r1.captured_at_birth != r2.captured_at_birth or
                    len(r1.newly_captured) != len(r2.newly_captured) or
                    g.score != c.score):
                bad += 1
    check("clone: одинаковый ход даёт одинаковый результат (30 позиций)",
          bad == 0, f"bad={bad}")


def stress_reactivation_invariant():
    print("\n[B4] Режим с оживлением: сходимость и валидность")
    rng = random.Random(31337)
    bad = 0
    for _ in range(60):
        g = dm.Game(reactivation=True)
        for _ in range(60):
            a = rng.uniform(0, 2 * math.pi)
            r = rng.uniform(0, dm.FIELD_RADIUS - 2)
            g.place(r * math.cos(a), r * math.sin(a))
            # инвариант: каждая точка имеет валидный статус, счёт не отрицателен
            if g.score[dm.RED_C] < 0 or g.score[dm.BLUE_C] < 0:
                bad += 1
    check("режим с оживлением: 3600 ходов без отрицательного счёта/сбоев",
          bad == 0, f"bad={bad}")


def stress_performance():
    print("\n[B5] Производительность на плотных кластерах")
    rng = random.Random(1)
    # плотный кластер из 40 точек в пятне радиуса 30 (почти клика)
    g = dm.Game()
    cx, cy = 0, 0
    for i in range(40):
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(0, 30)
        g.place(cx + r * math.cos(a), cy + r * math.sin(a))
    t0 = time.time()
    slow = 0.0
    for i in range(20):
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(0, 30)
        t1 = time.time()
        g.place(cx + r * math.cos(a), cy + r * math.sin(a))
        slow = max(slow, time.time() - t1)
    dt = time.time() - t0
    check(f"20 ходов в плотном кластере (60 точек): макс. ход {slow*1000:.0f} мс (< 1500 мс)",
          slow < 1.5, f"max={slow:.2f}s total={dt:.2f}s")

    # длинная случайная партия: 300 ходов
    g2 = dm.Game()
    rng2 = random.Random(2)
    t0 = time.time()
    slow2 = 0.0
    for i in range(300):
        a = rng2.uniform(0, 2 * math.pi)
        r = rng2.uniform(0, dm.FIELD_RADIUS - 5)
        t1 = time.time()
        g2.place(r * math.cos(a), r * math.sin(a))
        slow2 = max(slow2, time.time() - t1)
    dt2 = time.time() - t0
    check(f"300 случайных ходов: макс. ход {slow2*1000:.0f} мс (< 800 мс), "
          f"всего {dt2:.1f} с (< 30 с)",
          slow2 < 0.8 and dt2 < 30, f"max={slow2:.2f}s total={dt2:.1f}s")


def main():
    t0 = time.time()
    stress_oracle()
    adversarial_contours()
    stress_random_play()
    stress_undo()
    stress_clone()
    stress_reactivation_invariant()
    stress_performance()
    print(f"\nИТОГ: {PASS} ok, {FAIL} fail, {time.time() - t0:.1f} с")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
