#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""诊断脚本：在 GitHub Actions 里实测抓取到的页面新鲜度。用完可删。"""
import time
import urllib.request
import json
import os

UID = "3962719063"
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1")


def fetch(url, extra_headers=None):
    h = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"}
    if extra_headers:
        h.update(extra_headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=25) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
        hdrs = dict(resp.headers)
        return body, resp.status, hdrs


def newest(page, n=3):
    import re
    out = []
    for m in re.finditer(r'class="post-link" href="/news/detail/(\d+)\.html"(.*?)</article>', page, re.S):
        mid, body = m.group(1), m.group(2)
        tm = re.search(r'class="time">\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})', body)
        out.append((mid, tm.group(1) if tm else "NA"))
        if len(out) >= n:
            break
    return out


print("=" * 60)
print("1) 直接抓 http://www.sina.cn/media/3962719063")
try:
    b1, s1, h1 = fetch(f"http://www.sina.cn/media/{UID}")
    print(f"   HTTP {s1} | 长度 {len(b1)}")
    print(f"   x-cache: {h1.get('X-Cache')} | age: {h1.get('Age')} | cache-control: {h1.get('Cache-Control')}")
    print(f"   date: {h1.get('Date')}")
    print("   最新3条:", newest(b1))
except Exception as e:
    print("   失败:", e)

print("=" * 60)
print("2) 加时间戳破缓存")
try:
    ts = int(time.time())
    b2, s2, h2 = fetch(f"http://www.sina.cn/media/{UID}?t={ts}",
                        {"Cache-Control": "no-cache", "Pragma": "no-cache"})
    print(f"   HTTP {s2} | 长度 {len(b2)}")
    print(f"   x-cache: {h2.get('X-Cache')} | age: {h2.get('Age')}")
    print("   最新3条:", newest(b2))
except Exception as e:
    print("   失败:", e)

print("=" * 60)
print("3) 对比：解析出多少条")
try:
    import re
    print("   直接抓:", len(re.findall(r'class="post-link" href="/news/detail/\d+\.html"', b1)), "条")
except Exception:
    pass

print("=" * 60)
print("4) 仓库 state.json")
try:
    print("  ", json.load(open("state.json", encoding="utf-8")))
except Exception as e:
    print("   读取失败:", e)

print("=" * 60)
print("5) pushplus 连通性（不发消息，只测 token 有效性用无效 payload）")
try:
    req = urllib.request.Request(
        "https://www.pushplus.plus/send",
        data=json.dumps({"token": os.environ.get("PUSHPLUS_TOKEN", ""), "title": "", "content": ""}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        print("   HTTP", r.status, r.read().decode()[:200])
except Exception as e:
    print("   失败:", e)
