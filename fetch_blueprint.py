#!/usr/bin/env python3
# 蓝图码 → 官方解析 JSON（熵增 Endfield-API，文档：Entropy-Increase-Team/endfield-plugin API.md）
# 用法: python fetch_blueprint.py EF013Eou8uo47auUu0579 [更多码...]
# 输出: data/bp_<code>.json（官方解析格式，convert_v5.py 的输入）
import json
import sys
import urllib.request
import uuid
from pathlib import Path

API_BASE = "https://end-api.shallow.ink"
TOKEN_CACHE = Path(__file__).parent / ".anon_token"


def get_token():
    if TOKEN_CACHE.exists():
        cached = json.loads(TOKEN_CACHE.read_text(encoding="utf-8"))
        return cached["token"]
    fp = uuid.uuid4().hex + uuid.uuid4().hex[:8]
    req = urllib.request.Request(
        f"{API_BASE}/api/v1/auth/anonymous-token",
        data=json.dumps({"fingerprint": fp}).encode(),
        headers={"Content-Type": "application/json"})
    resp = json.load(urllib.request.urlopen(req, timeout=15))
    token = resp["data"]["token"]
    TOKEN_CACHE.write_text(json.dumps({"token": token}), encoding="utf-8")
    return token


def fetch(code, token):
    req = urllib.request.Request(
        f"{API_BASE}/api/blueprint/get?code={code}",
        headers={"X-Anonymous-Token": token})
    return json.load(urllib.request.urlopen(req, timeout=20))


def main():
    codes = sys.argv[1:]
    if not codes:
        print("用法: python fetch_blueprint.py <蓝图码>...")
        sys.exit(1)
    token = get_token()
    out_dir = Path(__file__).parent / "data"
    for code in codes:
        try:
            raw = fetch(code, token)
        except Exception as e:
            # token 过期（2h）则重建一次
            TOKEN_CACHE.unlink(missing_ok=True)
            raw = fetch(code, get_token())
        bp = raw["data"]["data"]["bluePrintData"]
        dst = out_dir / f"bp_{code}.json"
        json.dump(raw, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"{code} → {dst.name} | {bp.get('name')} | {bp.get('xSize')}x{bp.get('zSize')} | nodes={len(bp['nodes'])}")


if __name__ == "__main__":
    main()
