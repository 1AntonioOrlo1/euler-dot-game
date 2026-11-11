#!/usr/bin/env python3
"""Тесты для dotgame_maid.py. Запуск: .venv/bin/python test_maid.py"""
import math
import os
import random
import sys
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dotgame_maid as dm

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


def active(g, c):
    return {id(p): (round(p.x, 3), round(p.y, 3)) for p in g.active_of(c)}


def by_pos(g, x, y):
    for p in g.points:
        if math.hypot(p.x - x, p.y - y) < 1e-6:
            return p
    return None


def is_active(g, x, y):
    p = by_pos(g, x, y)
    return p is not None and p.active


def test_basic_capture():
    print("\n[1] Базовый захват треугольником")
    g = dm.Game()
    g.place(0, 0)          # red A
    g.place(25, 25)        # blue X (будет захвачен)
    g.place(50, 0)         # red B
    g.place(100, 100)      # blue decoy
    r = g.place(25, 43.30127018922193)  # red C — замыкает треугольник
    check("синяя X захвачена", not is_active(g, 25, 25))
    check("счёт красных = 1", g.score[dm.RED_C] == 1, str(g.score))
    check("счёт синих = 0", g.score[dm.BLUE_C] == 0)
    check("красные активны: 3", len(g.active_of(dm.RED_C)) == 3)
    check("новая точка активного цвета в newly_captured пустая",
          r.point.color == dm.RED_C and r.point.active)


def test_suicide():
    print("\n[2] Самопожертвование (точка в чужом контуре при постановке)")
    g = dm.Game()
    g.place(0, 0)
    g.place(25, 25)
    g.place(50, 0)
    g.place(100, 100)
    g.place(25, 43.30127018922193)   # красный треугольник, X захвачен
    r = g.place(20, 20)              # blue: внутрь красного треугольника
    check("точка захвачена при рождении", r.captured_at_birth)
    check("точка неактивна", not is_active(g, 20, 20))
    check("красным +1 за самопожертвование", g.score[dm.RED_C] == 2, str(g.score))


def test_no_reactivation():
    print("\n[3] Без оживления: захваченная точка не возвращается (режим по умолчанию)")
    g = dm.Game()
    g.place(0, 0)          # red A
    g.place(25, 25)        # blue X
    g.place(50, 0)         # red B
    g.place(100, 100)      # blue decoy
    g.place(25, 43.30127018922193)  # red C -> X захвачен
    check("X захвачен", not is_active(g, 25, 25))
    # Синий треугольник вокруг B(50,0): (45,15), (75,15), (60,-32)
    # (все рёбра <= 49.5, B внутри, вершины вне красного треугольника)
    g.place(45, 15)        # blue R2
    g.place(200, 200)      # red decoy
    g.place(75, 15)        # blue R3
    g.place(300, 300)      # red decoy 2
    r = g.place(60, -32)   # blue R1: замыкает треугольник
    check("R1 не захвачена при рождении (вне красного контура)",
          not r.captured_at_birth)
    check("B(50,0) захвачен синими", not is_active(g, 50, 0))
    check("X(25,25) НЕ ожил — захват окончательный", not is_active(g, 25, 25))
    check("красный счёт = 1 (X)", g.score[dm.RED_C] == 1, str(g.score))
    check("синий счёт = 1 (B)", g.score[dm.BLUE_C] == 1, str(g.score))
    # Тот же сценарий с оживлением — для контроля второго режима
    g2 = dm.Game(reactivation=True)
    g2.place(0, 0)
    g2.place(25, 25)
    g2.place(50, 0)
    g2.place(100, 100)
    g2.place(25, 43.30127018922193)
    g2.place(45, 15)
    g2.place(200, 200)
    g2.place(75, 15)
    g2.place(300, 300)
    g2.place(60, -32)      # синий треугольник ломает красный
    check("режим с оживлением: B захвачен", not is_active(g2, 50, 0))
    check("режим с оживлением: X ожил", is_active(g2, 25, 25))


def test_paradox_case():
    print("\n[4] Параллельно-наивный случай: квадрат с диагоналями (K4)")
    # Точка внутри одного из треугольников K4: наивный parity по всем рёбрам
    # сказал бы «вне» (2 пересечения), правильный ответ — внутри.
    g = dm.Game()
    g.place(0, 0)          # red
    g.place(7, 7)          # blue X
    g.place(35, 0)         # red
    g.place(100, 100)      # blue
    g.place(35, 35)        # red
    g.place(150, 150)      # blue
    r = g.place(0, 35)     # red: замыкает K4 (все рёбра <= 49.5 <= 50)
    check("X(7,7) захвачен хотя наивный parity=вне", not is_active(g, 7, 7))
    check("счёт красных = 1", g.score[dm.RED_C] == 1, str(g.score))


def test_bridge_not_captured():
    print("\n[5] Мост (хвост) не захватывает: точка рядом с хвостом вне цикла")
    g = dm.Game()
    g.place(0, 0)          # red A
    g.place(62.5, 5)       # blue X (рядом с будущим хвостом, вне треугольника)
    g.place(50, 0)         # red B
    g.place(200, 200)      # blue decoy
    g.place(0, 50)         # red C: треугольник ABC
    check("X вне треугольника — не захвачен", is_active(g, 62.5, 5))
    g.place(75, 0)         # red D: хвост от B (мост)
    g.place(62.5, 0)       # blue X2: на линии хвоста B-D
    check("X2 на линии МОСТА — не захвачен (мост не входит в цикл)",
          is_active(g, 62.5, 0))
    check("счёт красных = 0", g.score[dm.RED_C] == 0, str(g.score))


def test_on_cycle_edge_captured():
    print("\n[6] Точка ровно на линии контура — захвачена (правило мастера)")
    # Треугольник (0,0),(35,0),(0,35): гипотенуза 49.5 <= 50
    g = dm.Game()
    g.place(0, 0)
    g.place(10, 10)        # blue X: внутри (10+10=20 < 35)
    g.place(35, 0)
    g.place(200, 200)
    g.place(0, 35)         # замыкает треугольник
    check("X(10,10) внутри треугольника — захвачена",
          not is_active(g, 10, 10))
    # точка ровно на гипотенузе (35,0)-(0,35): линия x+y=35
    g2 = dm.Game()
    g2.place(0, 0)
    g2.place(17.5, 17.5)   # blue: ровно на будущей гипотенузе
    g2.place(35, 0)
    g2.place(300, 300)
    g2.place(0, 35)
    check("точка на линии контура захвачена", not is_active(g2, 17.5, 17.5))


def test_cascade_chain():
    print("\n[7] Цепной захват (без оживления) + режим с оживлением")
    g = dm.Game()
    g.place(0, 0)          # red A
    g.place(25, 25)        # blue X
    g.place(50, 0)         # red B
    g.place(100, 100)      # blue decoy
    g.place(25, 43.30127018922193)  # red C: X захвачен
    g.place(50, 28)        # blue P
    g.place(400, 400)      # red decoy
    g.place(35, -14)       # blue Q
    g.place(450, 450)      # red decoy 2
    r = g.place(65, -14)   # blue R: треугольник PQR вокруг B(50,0)
    check("B захвачен", not is_active(g, 50, 0))
    check("X НЕ ожил (захват окончательный)", not is_active(g, 25, 25))
    check("синий счёт = 1", g.score[dm.BLUE_C] == 1, str(g.score))
    check("красный счёт = 1", g.score[dm.RED_C] == 1, str(g.score))
    # с оживлением: X возвращается
    g2 = dm.Game(reactivation=True)
    for x, y in ((0, 0), (25, 25), (50, 0), (100, 100),
                 (25, 43.30127018922193), (50, 28), (400, 400),
                 (35, -14), (450, 450), (65, -14)):
        g2.place(x, y)
    check("с оживлением: B захвачен", not is_active(g2, 50, 0))
    check("с оживлением: X ожил", is_active(g2, 25, 25))


def test_limits_and_game_over():
    print("\n[8] Лимит точек и конец игры")
    g = dm.Game(max_points=2)
    g.place(0, 0)
    g.place(60, 60)
    r = g.place(10, 10)     # red: лимит; ход переходит к синим (у них ещё есть)
    check("ход у синих (у них есть точки — без pass)",
          g.current == dm.BLUE_C and not r.passed,
          f"current={g.current} passed={r.passed}")
    r = g.place(20, 20)     # blue: лимит -> оба на лимите
    check("игра окончена", r.game_over is True)
    check("после конца ходящий = blue (pass-back к ходившему)",
          g.current == dm.BLUE_C and r.passed)
    check("ничья при 0:0 (winner = None)", r.winner is None, str(r.winner))
    # победитель по счёту
    g2 = dm.Game(max_points=2)
    g2.place(0, 0)          # red
    g2.place(30, 30)        # blue X
    g2.place(50, 0)         # red: лимит (ребро 50, цикла нет)
    r = g2.place(200, 200)  # blue: лимит -> оба на лимите
    check("конец после 2:2", r.game_over is True)
    # Проверяем победителя на игре с захватом
    g3 = dm.Game(max_points=3)
    g3.place(0, 0)
    g3.place(25, 25)
    g3.place(50, 0)
    g3.place(100, 100)
    r = g3.place(25, 43.30127018922193)   # red: 3-я точка = лимит; X захвачен
    check("X захвачен, красный счёт = 1", not is_active(g3, 25, 25)
          and g3.score[dm.RED_C] == 1, str(g3.score))
    r = g3.place(150, 150)  # blue: 3-я точка = лимит -> конец, победа красных
    check("игра окончена", r.game_over is True)
    check("победитель = красные", r.winner == dm.RED_C, str(r.winner))
    r = g3.place(160, 160)  # после конца: точка не ставится
    check("после конца точка не ставится", r.point is None and r.game_over)


def test_undo():
    print("\n[9] Отмена хода")
    g = dm.Game()
    g.place(0, 0)
    g.place(60, 60)
    g.place(50, 0)
    check("3 точки", len(g.points) == 3)
    check("undo 1", g.undo() and len(g.points) == 2)
    check("undo 2", g.undo() and len(g.points) == 1)
    check("undo 3", g.undo() and len(g.points) == 0)
    check("undo пустого", not g.undo())
    check("счёт сброшен", g.score == {dm.RED_C: 0, dm.BLUE_C: 0})
    check("ход снова у красных", g.current == dm.RED_C)
    # undo после захвата восстанавливает активные флаги
    g2 = dm.Game()
    g2.place(0, 0)
    g2.place(25, 25)
    g2.place(50, 0)
    g2.place(100, 100)
    g2.place(25, 43.30127018922193)   # X захвачен
    check("X захвачен до undo", not is_active(g2, 25, 25))
    g2.undo()
    check("X активен после undo", is_active(g2, 25, 25))
    check("счёт восстановлен", g2.score[dm.RED_C] == 0)


def test_geometry_oracle():
    print("\n[10] Оракул: встроенный предикат vs полный перебор циклов")
    import importlib
    if "test_oracle" in sys.modules:
        oracle = importlib.reload(sys.modules["test_oracle"])
    else:
        oracle = importlib.import_module("test_oracle")

    def make_struct(pts, R):
        class P:
            __slots__ = ("x", "y")

            def __init__(s, t):
                s.x = t[0]
                s.y = t[1]
        st = dm.ColorStructure()
        st.rebuild([P(t) for t in pts], R)
        return st

    rng = random.Random(7)
    mism = 0
    total = 0
    for _ in range(350):
        kind = rng.choice(("grid", "clique", "scattered"))
        pts, R, qs = oracle.random_case(kind, rng)
        st = make_struct(pts, R)
        for X in qs:
            total += 1
            try:
                bf = oracle.bf_predicate(X, pts, R)
            except RuntimeError:
                an = oracle.clique_analytic(pts, R, X)
                if an is None:
                    continue
                bf = an
            fast = st.query(X)
            if fast != bf:
                mism += 1
                if mism <= 5:
                    print(f"    mismatch {kind} X={X} fast={fast} bf={bf}")
    check(f"oracle {total} запросов, {mism} расхождений", mism == 0)


def test_performance():
    print("\n[11] Производительность")
    g = dm.Game()
    # плотный кластер: 16 точек в пятне радиуса 25 (почти клика, ~120 рёбер)
    rng = random.Random(3)
    cx, cy = -100, 80
    pts = []
    for i in range(16):
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(0, 24)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    for i, (x, y) in enumerate(pts):
        g.place(x, y) if i % 2 == 0 else g.place(x, y)
    # теперь ход синим (последний ходил кто-то — чередуем)
    t0 = time.time()
    for i in range(6):
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(0, 24)
        g.place(cx + r * math.cos(a), cy + r * math.sin(a))
    dt = time.time() - t0
    check(f"6 ходов в кликовом кластере: {dt * 1000:.0f} мс (< 1500 мс)", dt < 1.5,
          f"{dt:.2f}s")

    # полная случайная игра, 150 ходов
    g2 = dm.Game()
    rng2 = random.Random(99)
    t0 = time.time()
    slow = 0.0
    for i in range(150):
        a = rng2.uniform(0, 2 * math.pi)
        r = rng2.uniform(0, dm.FIELD_RADIUS - 5)
        x, y = r * math.cos(a), r * math.sin(a)
        t1 = time.time()
        g2.place(x, y)
        slow = max(slow, time.time() - t1)
    dt2 = time.time() - t0
    check(f"150 случайных ходов: {dt2:.2f} с всего, макс. ход {slow * 1000:.0f} мс (< 800 мс)",
          dt2 < 8 and slow < 0.8, f"total={dt2:.2f}s max={slow:.2f}s")


def test_last_contour():
    print("\n[12] Визуализация: найден контур-захват")
    g = dm.Game()
    g.place(0, 0)
    g.place(25, 25)
    g.place(50, 0)
    g.place(100, 100)
    r = g.place(25, 43.30127018922193)
    ok = False
    if r.last_contour:
        cyc = r.last_contour
        ok = len(cyc) == 3 and all(math.hypot(p.x - 25, p.y - 25) < 50.1 for p in cyc)
    check("контур-треугольник найден", ok,
          f"contour={[(round(p.x,1),round(p.y,1)) for p in (r.last_contour or [])]}")


def test_ai():
    print("\n[13] ИИ (SimpleAI)")
    # (a) доступный захват: синий замыкает треугольник вокруг красной X
    g = dm.Game()
    g.place(0, 25)         # red X
    g.place(-20, 20)       # blue A
    g.place(200, 200)      # red decoy
    g.place(20, 20)        # blue B (ребро A-B, 40)
    g.place(-200, 200)     # red decoy2  -> ход синих
    ai = dm.SimpleAI(dm.BLUE_C, budget_s=5.0)
    mv = ai.choose(g)
    check("ИИ нашёл ход", mv is not None)
    check("ИИ берёт доступный захват: (0, 65.83)",
          mv is not None and abs(mv[0] - 0) < 0.5
          and abs(mv[1] - 65.8258) < 0.5, str(mv))
    if mv:
        g.place(mv[0], mv[1])
        check("X(0,25) захвачена ходом ИИ", not is_active(g, 0, 25))
        check("счёт синих = 1", g.score[dm.BLUE_C] == 1, str(g.score))

    # (b) самопожертвование только в отчаянии: у красных замкнутый треугольник,
    #     синему есть безопасные ходы — ИИ не должен жертваться
    g2 = dm.Game()
    g2.place(0, 0)
    g2.place(200, 200)
    g2.place(50, 0)
    g2.place(250, 250)
    g2.place(25, 43.30127018922193)   # красный треугольник
    g2.place(200, -200)               # blue: одна точка
    g2.place(-250, 250)               # red decoy -> ход синих
    mv = dm.SimpleAI(dm.BLUE_C, budget_s=5.0).choose(g2)
    check("ИИ нашёл ход (b)", mv is not None)
    if mv:
        sim = g2.clone()
        res = sim.place(mv[0], mv[1])
        check("ход ИИ не самопожертвование", res.point is not None
              and not res.captured_at_birth)
        check("точка ИИ в поле", math.hypot(mv[0], mv[1]) <= dm.FIELD_RADIUS)

    # (c) детерминизм
    g3 = dm.Game()
    for (x, y) in ((0, 0), (-20, 20), (200, 200), (20, 20), (-200, 200)):
        g3.place(x, y)
    m1 = dm.SimpleAI(dm.BLUE_C, budget_s=5.0).choose(g3)
    m2 = dm.SimpleAI(dm.BLUE_C, budget_s=5.0).choose(g3)
    check("детерминизм: одинаковый выбор", m1 == m2, f"{m1} vs {m2}")

    # (d) бюджет времени на средней позиции
    rng = random.Random(42)
    g4 = dm.Game()
    for i in range(40):
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(0, dm.FIELD_RADIUS - 5)
        g4.place(r * math.cos(a), r * math.sin(a))
    t0 = time.time()
    m4 = dm.SimpleAI(g4.current, budget_s=3.0, cap1=40, cap2=20).choose(g4)
    dt = time.time() - t0
    check(f"40 точек: ход ИИ за {dt:.1f} с (< 12 с)", m4 is not None and dt < 12,
          f"{dt:.1f}s")

    # (e) демо: два ИИ доводят партию до лимита без зависаний
    g5 = dm.Game(max_points=6)
    moves = 0
    passes = 0
    t0 = time.time()
    while not (g5.at_limit(dm.RED_C) and g5.at_limit(dm.BLUE_C)) and moves < 12:
        mv = dm.SimpleAI(g5.current, budget_s=2.0, cap1=40, cap2=20).choose(g5)
        if mv is None:
            passes += 1
            if passes >= 2:
                break
            g5.current = dm.other_color(g5.current)
            continue
        passes = 0
        g5.place(mv[0], mv[1])
        moves += 1
    dt = time.time() - t0
    check(f"демо: партия на {moves} ходов за {dt:.1f} с (< 60 с)",
          moves >= 10 and dt < 60, f"moves={moves} {dt:.1f}s")
    check("демо: все точки в поле",
          all(math.hypot(p.x, p.y) <= dm.FIELD_RADIUS + 0.1 for p in g5.points))
    check("демо: игра доведена до лимита",
          g5.at_limit(dm.RED_C) and g5.at_limit(dm.BLUE_C))


def main():
    t0 = time.time()
    test_basic_capture()
    test_suicide()
    test_no_reactivation()
    test_paradox_case()
    test_bridge_not_captured()
    test_on_cycle_edge_captured()
    test_cascade_chain()
    test_limits_and_game_over()
    test_undo()
    test_geometry_oracle()
    test_performance()
    test_last_contour()
    test_ai()
    print(f"\nИТОГ: {PASS} ok, {FAIL} fail, {time.time() - t0:.1f} с")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
