#!/usr/bin/env python3
"""Сравнение: fast_py (Python-предикат) vs fast_js (JS-предикат) vs ref (перебор).
Проверяет и верность порта (py==js), и корректность (js==ref)."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
cases = json.load(open(os.path.join(HERE, "cases.json")))
ref_py = json.load(open(os.path.join(HERE, "ref_py.json")))
ref_js = json.load(open(os.path.join(HERE, "ref_js.json")))

py_js_mismatch = 0
js_ref_mismatch = 0
py_ref_mismatch = 0
compared = 0
ray_py = 0
ray_js = 0
examples = []

for ci, (case, rpy, rjs) in enumerate(zip(cases, ref_py, ref_js)):
    for qi, (X, (fpy, ref), fjs) in enumerate(zip(case["qs"], rpy, rjs)):
        if fpy is None:
            ray_py += 1
        if fjs is None:
            ray_js += 1
        # верность порта: py == js (сравниваем, когда оба не None)
        if fpy is not None and fjs is not None:
            if fpy != fjs:
                py_js_mismatch += 1
                if len(examples) < 8:
                    examples.append(("py!=js", ci, X, fpy, fjs))
        # корректность: js == ref (когда есть эталон)
        if ref is not None and fjs is not None:
            compared += 1
            if fjs != ref:
                js_ref_mismatch += 1
                if len(examples) < 8:
                    examples.append(("js!=ref", ci, X, fjs, ref))
        # sanity: py == ref
        if ref is not None and fpy is not None:
            if fpy != ref:
                py_ref_mismatch += 1

print(f"сравнено с эталоном: {compared}")
print(f"ray-ошибок: py={ray_py} js={ray_js}")
print(f"py != js (верность порта): {py_js_mismatch}")
print(f"js != ref (корректность JS): {js_ref_mismatch}")
print(f"py != ref (sanity Python): {py_ref_mismatch}")
for e in examples:
    print("  ", e)

ok = py_js_mismatch == 0 and js_ref_mismatch == 0 and py_ref_mismatch == 0 and ray_js == 0
print("ИТОГ:", "PASS" if ok else "FAIL")
raise SystemExit(0 if ok else 1)
