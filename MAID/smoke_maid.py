#!/usr/bin/env python3
"""Программный smoke-тест UI: события в живой поток main(), проверки состояния.

Без скриншотов и пиксельных проверок: каждое действие — реальное событие
pygame (клик/колесо/драг/клавиша), каждый результат проверяется по
состоянию живого объекта Game (координаты точек, активность, счёт, ход,
конец игры, undo, reset). Камера зеркалится в тесте, поэтому точные
координаты ожидаемых точек вычисляются арифметически.
"""
import math
import os
import sys
import threading
import time
import traceback

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import pygame  # noqa: E402
import dotgame_maid as dm  # noqa: E402

# --- перехват экземпляра Game, созданного main() ---
INSTANCES = []
_RealGame = dm.Game


def _spy_game(*a, **k):
    g = _RealGame(*a, **k)
    INSTANCES.append(g)
    return g


dm.Game = _spy_game

# --- ошибки UI-потока ---
THREAD_ERRORS = []


def _run_main():
    try:
        dm.main()
    except SystemExit:
        pass
    except BaseException:
        THREAD_ERRORS.append(traceback.format_exc())


FAILS = []
OKS = []


def check(label, cond, extra=""):
    if cond:
        OKS.append(label)
        print("  ok  ", label)
    else:
        FAILS.append(label)
        print("  FAIL", label, extra)


def approx(a, b, tol):
    return abs(a - b) <= tol


def find_pt(g, x, y, tol=0.05):
    for p in g.points:
        if (p.x - x) ** 2 + (p.y - y) ** 2 <= tol * tol:
            return p
    return None


def click(x, y, button=1):
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=button, pos=(int(x), int(y))))
    time.sleep(0.05)
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONUP, button=button, pos=(int(x), int(y))))
    time.sleep(0.25)


def key(k):
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=k))
    time.sleep(0.25)
    pygame.event.post(pygame.event.Event(pygame.KEYUP, key=k))
    time.sleep(0.2)


def wheel(dy):
    pygame.event.post(pygame.event.Event(pygame.MOUSEWHEEL, y=dy))
    time.sleep(0.2)


def drag(x1, y1, x2, y2, steps=5):
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=2, pos=(int(x1), int(y1))))
    time.sleep(0.1)
    for i in range(1, steps + 1):
        px = int(x1 + (x2 - x1) * i / steps)
        py = int(y1 + (y2 - y1) * i / steps)
        pygame.event.post(pygame.event.Event(
            pygame.MOUSEMOTION, pos=(px, py), rel=(px, py), buttons=(0, 1, 0)))
        time.sleep(0.05)
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONUP, button=2, pos=(int(x2), int(y2))))
    time.sleep(0.2)


def main():
    dm.MAX_POINTS_PER_PLAYER = 6  # конец игры виден на короткой партии

    t = threading.Thread(target=_run_main, daemon=True)
    t.start()
    time.sleep(2.0)
    check("UI-поток жив, игра создана", len(INSTANCES) == 1)
    g = INSTANCES[0]

    # зеркало камеры (те же операции, что обрабатывает main)
    scale = 1.0
    ox, oy = 0.0, 0.0

    def game_pos(sx, sy):
        return (ox + (sx - 400) / scale, oy + (sy - 400) / scale)

    # ================= фаза 1: базовые ходы и захват =================
    print("\n[1] Базовые ходы (ЛКМ) и захват треугольником")
    click(400, 400)
    p = find_pt(g, *game_pos(400, 400))
    check("red (0,0) поставлен", p is not None and p.color == dm.RED_C)
    check("ход перешёл к синим", g.current == dm.BLUE_C)

    click(425, 425)
    p = find_pt(g, *game_pos(425, 425))
    check("blue X(25,25) поставлен", p is not None and p.color == dm.BLUE_C)

    click(450, 400)
    check("red (50,0) поставлен", find_pt(g, *game_pos(450, 400)) is not None)
    click(500, 500)
    check("blue (100,100) поставлен", find_pt(g, *game_pos(500, 500)) is not None)

    click(425, 443)  # red (25,43): замыкает треугольник (0,0),(50,0),(25,43)
    x = find_pt(g, 25, 25)
    check("X(25,25) захвачена треугольником", x is not None and not x.active)
    check("счёт 1:0 в пользу красных",
          g.score[dm.RED_C] == 1 and g.score[dm.BLUE_C] == 0, str(g.score))
    check("красных 3 точки", g.count_of(dm.RED_C) == 3)
    check("ход синих", g.current == dm.BLUE_C)

    click(350, 400)  # blue (-50,0)
    p = find_pt(g, -50, 0)
    check("blue (-50,0) активна (вне контура)", p is not None and p.active)

    # ================= фаза 2: привязка к линии =================
    print("\n[2] ПКМ: окружность точки + кандидаты на пересечениях")
    # ПКМ по (495,405) = game (95,5): ближайшее — окружность red(50,0) r50 (d=4.7)
    click(495, 405, button=3)
    click(495, 405, button=3)  # повторно -> зелёные кандидаты
    # Кандидаты окружности (50,0): пересечения с окружностями других точек.
    # ЛКМ по (425,356) = game (25,-44): ближайший кандидат — пересечение
    # окружностей (0,0) r50 и (50,0) r50: (25, -43.3013)
    n_before = g.count_of(dm.RED_C)
    click(425, 356)
    check("красный ход поставлен (snap)", g.count_of(dm.RED_C) == n_before + 1)
    pts = g.points_of(dm.RED_C)
    inter = [p for p in pts
             if approx(math_dist(p, 0, 0), 50, 1e-3)
             and approx(math_dist(p, 50, 0), 50, 1e-3)]
    check("точка в точном пересечении окружностей (|p-O1|=50, |p-O2|=50)",
          len(inter) == 1, "кандидатов: %d" % len(inter))
    if inter:
        check("пересечение — нижнее (y<0, клик был снизу)", inter[0].y < 0)
        check("не в точке клика (снап, а не клик)",
              math_dist(inter[0], 25, -44) > 0.2)

    # Теперь выбираем окружность blue(100,100):
    # ПКМ по (520,480) = game (120,80): ближайшее — blue circle (100,100) r50
    click(520, 480, button=3)
    # ЛКМ по (525,485) = game (125,85): проекция на окружность (100,100) r50
    n_before = g.count_of(dm.BLUE_C)
    click(525, 485)
    check("синий ход поставлен (проекция на окружность)",
          g.count_of(dm.BLUE_C) == n_before + 1)
    pts = g.points_of(dm.BLUE_C)
    proj = [p for p in pts if approx(math_dist(p, 100, 100), 50, 0.05)]
    check("точка на окружности blue(100,100) r50", len(proj) == 1)
    if proj:
        check("проекция активна (вне красных контуров)", proj[0].active)
        check("не в точке клика", math_dist(proj[0], 125, 85) > 5)

    # ================= фаза 3: зум + панорама =================
    print("\n[3] Камера: зум, панорама, точность трансформов")
    wheel(2)
    scale *= 1.1
    wheel(1)
    scale *= 1.1
    drag(400, 400, 500, 450)
    ox -= 100.0 / scale
    oy -= 50.0 / scale
    click(480, 350)
    ex, ey = game_pos(480, 350)
    p = find_pt(g, ex, ey, 0.05)
    check("красная точка в координате с учётом зума/панорамы (%.2f,%.2f)" % (ex, ey),
          p is not None and p.color == dm.RED_C)
    check("эта точка вне контура — активна", p is not None and p.active)

    wheel(-1)
    scale /= 1.1
    wheel(-1)
    scale /= 1.1
    click(400, 400)
    ex, ey = game_pos(400, 400)
    p = find_pt(g, ex, ey, 0.05)
    check("синяя точка после вылета зума (%.2f,%.2f)" % (ex, ey),
          p is not None and p.color == dm.BLUE_C)

    # ================= фаза 4: самопожертвование + конец игры =================
    print("\n[4] Лимит точек (6) и самопожертвование")
    click(633, 441)
    check("красных 6 — у красных лимит", g.count_of(dm.RED_C) == 6 and g.at_limit(dm.RED_C))
    check("ход у синих (красные не в лимите... синие 5<6)", g.current == dm.BLUE_C)

    # синий ходит ВНУТРЬ красного треугольника: game (23.36, 19.68)
    click(506, 461)
    ex, ey = game_pos(506, 461)
    p = find_pt(g, ex, ey, 0.05)
    check("синяя точка внутри контура поставлена", p is not None)
    check("самопожертвование: точка захвачена сразу",
          p is not None and not p.active)
    check("счёт 2:0", g.score[dm.RED_C] == 2 and g.score[dm.BLUE_C] == 0,
          str(g.score))
    check("обе стороны в лимите — игра окончена",
          g.at_limit(dm.RED_C) and g.at_limit(dm.BLUE_C))
    check("победитель — красные", g._winner() == dm.RED_C)

    n_total = len(g.points)
    click(300, 300)
    check("после конца точки не ставятся", len(g.points) == n_total)

    # ================= фаза 5: undo =================
    print("\n[5] Отмена ходов (Z)")
    key(pygame.K_z)
    check("undo: 11 точек", len(g.points) == 11, "fакт: %d" % len(g.points))
    check("undo: самопожертвование отменено, счёт 1:0",
          g.score[dm.RED_C] == 1 and g.score[dm.BLUE_C] == 0)
    check("undo: ход синих (ходившей до отмены стороне)", g.current == dm.BLUE_C)
    key(pygame.K_z)
    check("undo2: 10 точек", len(g.points) == 10, "fакт: %d" % len(g.points))
    check("undo2: ход красных", g.current == dm.RED_C)

    # ================= фаза 6: reset =================
    print("\n[6] Новая игра (R) и движение после сброса")
    key(pygame.K_r)
    check("reset: 0 точек", len(g.points) == 0)
    check("reset: счёт 0:0, ход красных",
          g.score[dm.RED_C] == 0 and g.current == dm.RED_C)
    click(400, 400)
    p = find_pt(g, 0, 0)
    check("после reset: камера сброшена, red (0,0)", p is not None and p.color == dm.RED_C)
    check("ход синих", g.current == dm.BLUE_C)

    # ================= фаза 7: справка =================
    print("\n[7] Справка (H) не ломает состояние")
    key(pygame.K_h)
    time.sleep(0.3)
    key(pygame.K_h)
    time.sleep(0.3)
    check("после H/H: состояние не изменилось", len(g.points) == 1)

    # завершаем горячую игру, чтобы открыть окно для режима --ai
    pygame.event.post(pygame.event.Event(pygame.QUIT))
    t.join(timeout=15)
    check("UI-поток (hotseat) завершился", not t.is_alive())

    # ================= фаза 8: режим --ai =================
    print("\n[8] Режим --ai: компьютер отвечает на ходы человека")
    argv_saved = sys.argv
    sys.argv = ["dotgame_maid.py", "--ai"]
    t2 = threading.Thread(target=_run_main, daemon=True)
    t2.start()
    time.sleep(2.0)
    g2 = INSTANCES[-1]
    check("игра в режиме --ai создана", len(INSTANCES) == 2)

    def wait_ai(g_, n_blue, timeout=20.0):
        deadline = time.time() + timeout
        while time.time() < deadline and g_.count_of(dm.BLUE_C) < n_blue:
            time.sleep(0.2)
        return g_.count_of(dm.BLUE_C) >= n_blue

    click(400, 400)          # человек: red (0,0)
    time.sleep(0.5)
    check("человеческая точка поставлена", g2.count_of(dm.RED_C) == 1)
    check("компьютер ответил своим ходом", wait_ai(g2, 1))
    bps = g2.points_of(dm.BLUE_C)
    check("точка компьютера в поле",
          bps and all(math.hypot(p.x, p.y) <= dm.FIELD_RADIUS for p in bps))
    check("точка компьютера активна (не жертва)",
          bps and all(p.active for p in bps))

    click(430, 370)          # человек: red (30,-30)
    click(550, 550)          # лишний клик — должен быть проигнорирован (ход компа)
    time.sleep(0.2)
    check("лишний клик в ход компьютера проигнорирован",
          g2.count_of(dm.RED_C) == 2)
    check("компьютер сделал второй ход", wait_ai(g2, 2))
    check("красных по-прежнему 2", g2.count_of(dm.RED_C) == 2)

    pygame.event.post(pygame.event.Event(pygame.QUIT))
    t2.join(timeout=20)
    check("UI-поток (--ai) завершился", not t2.is_alive())
    check("исключений в UI-потоке (--ai) не было", not THREAD_ERRORS,
          THREAD_ERRORS[0] if THREAD_ERRORS else "")
    sys.argv = argv_saved

    # ================= финиш =================
    print("\nИТОГ: %d ok, %d fail" % (len(OKS), len(FAILS)))
    if FAILS:
        print("провалы:")
        for f in FAILS:
            print("  -", f)
        sys.exit(1)


def math_dist(p, x, y):
    return ((p.x - x) ** 2 + (p.y - y) ** 2) ** 0.5


if __name__ == "__main__":
    main()
