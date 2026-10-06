#!/usr/bin/env python3
"""P4 对齐回归：TS 导入器输出 vs Python 修正版输出 深度 diff。

用法：python compare_ts_python.py
  1. 对 data/ 下 8 份 fixture 分别跑 Python 修正版（v6 语义）与 TS 版转换
  2. 归一化（剥 blueprintId/createdAt/updatedAt）后深度对比 entities/entityOrder/slotLinks
  3. 全部一致 → exit 0；任一差异 → 打印差异 → exit 1

TS 侧转换经 vendor/IndustrialPlanner/src/scripts/dump-official-blueprint-conversion.ts（tsx 运行）。
Python 原型已归档至 archive/python-converter/（v6 语义修正版，仅供回归参照）。
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
VENDOR = ROOT / "vendor" / "IndustrialPlanner"
TS_DUMP = VENDOR / "src" / "scripts" / "dump-official-blueprint-conversion.ts"
sys.path.insert(0, str(ROOT / "archive" / "python-converter"))

from convert_v5 import Converter, load_blueprint  # noqa: E402

RECIPES_PATH = ROOT / "archive" / "python-converter" / "recipes.json"
_RECIPES_CACHE: dict | None = None


def load_recipes() -> dict:
    global _RECIPES_CACHE
    if _RECIPES_CACHE is None:
        _RECIPES_CACHE = json.loads(RECIPES_PATH.read_text(encoding="utf-8"))
    return _RECIPES_CACHE

FIXTURES = [
    "bp_simple",
    "bp_test",
    "bp_user",
    "bp_EF0108131aE82iAIE179",
    "bp_EF013Eou8uo47auUu0579",
    "bp_EF01I43ouo3OA979O5o08",
    "bp_EF0170iUeUi6855u2O0Ai",
    "bp_EF010819a91uOi12iE179",
]

# 归一化字段（两版各自生成，不参与对比）
VOLATILE_TOP_LEVEL = ("blueprintId", "createdAt", "updatedAt")


def python_convert(fixture: str) -> dict:
    bp = load_blueprint(ROOT / "data" / f"{fixture}.json")
    conv = Converter(bp, recipes=load_recipes())
    conv.run()
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        doc = conv.emit(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    return doc


def ts_convert(fixture: str) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    npx = "npx.cmd" if sys.platform == "win32" else "npx"
    try:
        result = subprocess.run(
            [npx, "tsx", "--tsconfig", "tsconfig.app.json",
             str(TS_DUMP), str(ROOT / "data" / f"{fixture}.json"), str(tmp_path)],
            cwd=VENDOR, capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(f"TS 转换失败: {result.stderr[-500:]}")
        return json.loads(tmp_path.read_text(encoding="utf-8"))
    finally:
        tmp_path.unlink(missing_ok=True)


def normalize(doc: dict) -> dict:
    out = {k: v for k, v in doc.items() if k not in VOLATILE_TOP_LEVEL}
    return out


def deep_diff(path: str, a, b, diffs: list, max_diffs: int = 20):
    if len(diffs) >= max_diffs:
        return
    if type(a) is not type(b):
        diffs.append(f"{path}: 类型不同 {type(a).__name__} vs {type(b).__name__} (PY={a!r:.80} TS={b!r:.80})")
        return
    if isinstance(a, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a:
                diffs.append(f"{path}.{key}: 仅 TS 存在")
            elif key not in b:
                diffs.append(f"{path}.{key}: 仅 PY 存在")
            else:
                deep_diff(f"{path}.{key}", a[key], b[key], diffs, max_diffs)
    elif isinstance(a, list):
        if len(a) != len(b):
            diffs.append(f"{path}: 长度 {len(a)} vs {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            deep_diff(f"{path}[{i}]", x, y, diffs, max_diffs)
    elif a != b:
        diffs.append(f"{path}: PY={a!r:.80} TS={b!r:.80}")


def main() -> int:
    total_fail = 0
    for fixture in FIXTURES:
        py_doc = normalize(python_convert(fixture))
        ts_doc = normalize(ts_convert(fixture))
        diffs: list = []
        deep_diff(fixture, py_doc, ts_doc, diffs)
        if diffs:
            total_fail += 1
            print(f"✗ {fixture}: {len(diffs)} 处差异（前 10）")
            for d in diffs[:10]:
                print(f"    {d}")
        else:
            print(f"✓ {fixture}: diff 为空（实体 {len(py_doc['entities'])} / 连接数一致）")
    if total_fail:
        print(f"\n{total_fail}/{len(FIXTURES)} 份存在差异")
        return 1
    print(f"\n全部 {len(FIXTURES)} 份 fixture diff 为空")
    return 0


if __name__ == "__main__":
    sys.exit(main())
