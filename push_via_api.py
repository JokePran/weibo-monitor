#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通过 GitHub REST API 提交文件（本机 git 协议不可用时的替代方案）。

用法：GH_TOKEN=xxx python3 push_via_api.py <文件1> <文件2> ... --message "提交说明"
"""
import json
import os
import sys
import base64
import urllib.request
import urllib.error

TOKEN = os.environ["GH_TOKEN"]
REPO = os.environ.get("GH_REPO", "JokePran/weibo-monitor")
API = "https://api.github.com"


def req(path, method="GET", payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(f"{API}{path}", data=data, method=method, headers={
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "workbuddy",
    })
    try:
        with urllib.request.urlopen(r, timeout=40) as resp:
            body = resp.read().decode()
            return resp.status, (json.loads(body) if body.strip() else {})
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def main():
    argv = sys.argv[1:]
    msg = "chore: update files"
    if "--message" in argv:
        i = argv.index("--message")
        msg = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    files = argv

    st, ref = req(f"/repos/{REPO}/git/ref/heads/main")
    head = ref["object"]["sha"]
    st, commit = req(f"/repos/{REPO}/git/commits/{head}")
    base_tree = commit["tree"]["sha"]
    print(f"head={head[:8]} base_tree={base_tree[:8]}")

    entries = []
    for f in files:
        content = open(f, "rb").read()
        st, blob = req(f"/repos/{REPO}/git/blobs", "POST", {
            "content": base64.b64encode(content).decode(), "encoding": "base64"})
        if st not in (200, 201):
            print(f"✗ blob 失败 {f}: {st} {blob.get('message')}")
            sys.exit(1)
        entries.append({"path": f, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        print(f"  blob OK {f} ({len(content)}B)")

    st, tree = req(f"/repos/{REPO}/git/trees", "POST", {"base_tree": base_tree, "tree": entries})
    if st not in (200, 201):
        print(f"✗ tree 失败: {st} {tree.get('message')}")
        sys.exit(1)

    st, nc = req(f"/repos/{REPO}/git/commits", "POST",
                 {"message": msg, "tree": tree["sha"], "parents": [head]})
    if st not in (200, 201):
        print(f"✗ commit 失败: {st} {nc.get('message')}")
        sys.exit(1)

    st, upd = req(f"/repos/{REPO}/git/refs/heads/main", "PATCH",
                  {"sha": nc["sha"], "force": False})
    print(f"✓ 提交成功 {nc['sha'][:8]} | ref 更新 HTTP {st}")


if __name__ == "__main__":
    main()
