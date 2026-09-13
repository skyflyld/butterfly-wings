#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把站点产物推到 k286（单次 commit，Git Data API）

用法：
    python3 deploy.py                     # 按 MANIFEST 推送（新/改都推）
    python3 deploy.py --drop old.md ...   # 同时从站点删除文件
    python3 deploy.py --dry               # 只看会推什么

设计：与 build.py 同一纪律 — 产物由源生成，推送清单显式列在这里，
不靠「记得传哪个文件」。token 从 ~/.github-tokens/k286c7hg65-hub.token 读。
"""
import json, base64, os, sys, glob, urllib.request, urllib.error

OWNER, REPO = "k286c7hg65-hub", "butterfly-wings"
ROOT = os.path.dirname(os.path.abspath(__file__))
API = f"https://api.github.com/repos/{OWNER}/{REPO}"
TOKEN_FILE = os.path.expanduser("~/.github-tokens/k286c7hg65-hub.token")

MANIFEST = [
    "index.html",
    "r16-enhanced.html",
    "r16-flipbook.html",
    "materials-2026-09-13.html",
    "butterfly-wings-r16.md",
    "materials/material-candidates-2026-09-13.md",
    "materials/sources/*.txt",
]
MSG = ("素材候选清单上线（14 条 · 一手来源 + 证据等级）+ materials sources 存档\n\n"
       "由 build_materials.py 从 materials/material-candidates-2026-09-13.md 生成")


def api(method, path, body=None):
    req = urllib.request.Request(API + path, method=method)
    req.add_header("Authorization", "Bearer " + token())
    req.add_header("Accept", "application/vnd.github+json")
    data = json.dumps(body).encode() if body is not None else None
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data, timeout=120) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        print("HTTPError", e.code, e.read()[:300]); raise


_tok = None


def token():
    global _tok
    if _tok is None:
        _tok = [l.strip() for l in open(TOKEN_FILE) if l.strip().startswith("ghp_")][0]
    return _tok


def expand():
    out = []
    for item in MANIFEST:
        hits = sorted(glob.glob(os.path.join(ROOT, item)))
        if not hits:
            print("  ⚠️ 清单里的", item, "不存在")
        out += hits
    return out


def main():
    drops = []
    if "--drop" in sys.argv:
        i = sys.argv.index("--drop")
        drops = sys.argv[i + 1:]
    files = expand()
    for f in files:
        print(f"  推送 {os.path.relpath(f, ROOT)} {os.path.getsize(f)} B")
    for d in drops:
        print(f"  删除 {d}")
    if "--dry" in sys.argv:
        return
    head = api("GET", "/git/ref/heads/main")["object"]["sha"]
    base = api("GET", f"/git/commits/{head}")["tree"]["sha"]
    tree = []
    for f in files:
        rel = os.path.relpath(f, ROOT)
        blob = api("POST", "/git/blobs",
                   {"content": base64.b64encode(open(f, "rb").read()).decode(), "encoding": "base64"})
        tree.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    for d in drops:
        tree.append({"path": d, "mode": "100644", "type": "blob", "sha": None})
    t = api("POST", "/git/trees", {"base_tree": base, "tree": tree})
    c = api("POST", "/git/commits", {"message": MSG, "tree": t["sha"], "parents": [head]})
    api("PATCH", "/git/refs/heads/main", {"sha": c["sha"]})
    print("✅ 已推送", len(files), "个文件，commit", c["sha"][:8])


if __name__ == "__main__":
    main()
