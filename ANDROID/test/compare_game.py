#!/usr/bin/env python3
"""Сравнение финальных состояний партий: Python vs JS."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
game_py = json.load(open(os.path.join(HERE, "game_py.json")))
game_js = json.load(open(os.path.join(HERE, "game_js.json")))

bad = 0
for gi, (py, js) in enumerate(zip(game_py, game_js)):
    if py["score"] != js["score"]:
        bad += 1
        if bad <= 5:
            print(f"  game {gi}: score py={py['score']} js={js['score']}")
    if py["current"] != js["current"]:
        bad += 1
        if bad <= 5:
            print(f"  game {gi}: current py={py['current']} js={js['current']}")
    if len(py["points"]) != len(js["points"]):
        bad += 1
        if bad <= 5:
            print(f"  game {gi}: n_points py={len(py['points'])} js={len(js['points'])}")
        continue
    for pi, (pp, jp) in enumerate(zip(py["points"], js["points"])):
        # [x, y, color, active]
        if (abs(pp[0] - jp[0]) > 1e-6 or abs(pp[1] - jp[1]) > 1e-6 or
                pp[2] != jp[2] or pp[3] != jp[3]):
            bad += 1
            if bad <= 5:
                print(f"  game {gi} pt {pi}: py={pp} js={jp}")
            break

print(f"партий: {len(game_py)}, расхождений: {bad}")
print("ИТОГ:", "PASS" if bad == 0 else "FAIL")
raise SystemExit(0 if bad == 0 else 1)
