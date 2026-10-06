#!/usr/bin/env python3
# 锚点公式回归校验：official_footprint_origin + REGISTRY 尺寸表 vs 官方 interactiveParam 中心点
# 33+ 样本全过 = 锚点表与尺寸表联合正确（免平台验证的核心手段）
import json
import sys
from pathlib import Path

from registry_table import ID_MAP, REGISTRY, official_footprint_origin

DATA = Path(__file__).parent.parent.parent / "data"


def check_file(path):
    raw = json.load(open(path, encoding="utf-8"))
    bp = raw["data"]["data"]["bluePrintData"]
    passed, failed, skipped = 0, 0, []
    for n in bp["nodes"]:
        t = n["templateId"]
        if t in ("grid_belt_01", "log_pipe_01"):
            continue
        tr = n.get("transform", {})
        pos = tr.get("position")
        ip = (tr.get("interactiveParam") or {}).get("position")
        if not pos or not ip:
            skipped.append((t, "缺 position/ip"))
            continue
        # 模式变体分流与转换器一致（v6 命名）
        mode = None
        for com in n.get("coms") or []:
            fm = com.get("formulaMan")
            if fm and fm.get("curMode"):
                mode = fm["curMode"]
        def_id = ID_MAP.get(t, t)
        if mode == "liquid" and t in ("furnance_1", "planter_1"):
            def_id = {"furnance_1": "furnance_1_liquid", "planter_1": "planter_1_liquid"}[t]
        if def_id not in REGISTRY:
            skipped.append((t, "注册表无尺寸"))
            continue
        (W, H), _rc, _p = REGISTRY[def_id]
        rot = int((tr.get("rotation") or tr.get("direction") or {}).get("y", 0) or 0) % 360
        ax, az = int(pos["x"]), int(pos["z"])
        x0, z0, w, h = official_footprint_origin(ax, az, rot, W, H)
        cx, cz = x0 + w / 2, z0 + h / 2
        if abs(cx - ip["x"]) < 0.01 and abs(cz - ip["z"]) < 0.01:
            passed += 1
        else:
            failed += 1
            print(f"  ✗ {t} rot={rot} anchor=({ax},{az}) → 算得中心({cx},{cz}) vs 官方({ip['x']},{ip['z']})")
    return passed, failed, skipped


def main():
    files = sorted(DATA.glob("bp_*.json"))
    if not files:
        print("data/ 下无 bp_*.json")
        sys.exit(1)
    total_p, total_f = 0, 0
    for f in files:
        p, fail, skip = check_file(f)
        total_p += p
        total_f += fail
        print(f"{f.name}: 通过 {p} / 失败 {fail}" + (f" / 跳过 {len(skip)}" if skip else ""))
    print(f"\n总计: {total_p} 通过, {total_f} 失败")
    sys.exit(1 if total_f else 0)


if __name__ == "__main__":
    main()
