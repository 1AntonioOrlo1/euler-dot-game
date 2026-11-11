#!/usr/bin/env python3
"""Дифференциальный тест логики Game: случайные партии в Python, те же ходы
в JS, сравнение (счёт, точки, чей ход, game_over). Вывод: moves.json + game_py.json."""
import json
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "MAID"))
import dotgame_maid as dm  # noqa: E402


def main():
    rng = random.Random(12345)
    n_games = 60
    n_moves = 40
    all_moves = []   # список партий: список (x, y)
    game_py = []     # финальные состояния
    for g in range(n_games):
        game = dm.Game()  # без оживления, без лимита
        moves = []
        for _ in range(n_moves):
            a = rng.uniform(0, 2 * math.pi)
            r = rng.uniform(0, dm.FIELD_RADIUS - 2)
            x, y = r * math.cos(a), r * math.sin(a)
            game.place(x, y)
            moves.append([round(x, 6), round(y, 6)])
        # финальное состояние
        state = {
            "score": game.score,
            "current": game.current,
            "points": [[p.x, p.y, p.color, p.active] for p in game.points],
        }
        all_moves.append(moves)
        game_py.append(state)
    json.dump(all_moves, open(os.path.join(HERE, "moves.json"), "w"))
    json.dump(game_py, open(os.path.join(HERE, "game_py.json"), "w"))
    print(f"games={n_games} moves_each={n_moves}")


if __name__ == "__main__":
    main()
