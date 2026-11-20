#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""诊断2：测试多个数据入口在 GitHub 云端的新鲜度。用完可删。"""
import re
import time
import json
import urllib.parse
import urllib.request

UID = "3962719063"
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1")
UA_PC = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def get(url, ua=UA, timeout=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/json,*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", errors="ignore")


def probe_html(page):
    """返回 (条数, 最新mid, 最新时间)"""
    ms = list(re.finditer(r'class="post-link" href="/news/detail/(\d+)\.html"(.*?)</article>', page, re.S))
    if not ms:
        return 0, "-", "-"
    mid, body = ms[0].group(1), ms[0].group(2)
    tm = re.search(r'class="time">\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})', body)
    return len(ms), mid, (tm.group(1) if tm else "NA")


targets = [
    ("sina.cn http 原入口", f"http://www.sina.cn/media/{UID}", UA),
    ("sina.cn https", f"https://www.sina.cn/media/{UID}", UA),
    ("sina.cn PC-UA", f"https://www.sina.cn/media/{UID}", UA_PC),
    ("m.sina.cn", f"https://m.sina.cn/media/{UID}", UA),
    ("k.sina.cn", f"http://k.sina.cn/media/{UID}", UA),
    ("sina.cn ?vt=4", f"https://www.sina.cn/media/{UID}?vt=4", UA),
    ("sina.cn ?page=1", f"https://www.sina.cn/media/{UID}?page=1", UA),
]

for name, url, ua in targets:
    try:
        st, page = get(url, ua)
        n, mid, tm = probe_html(page)
        print(f"[{name}] HTTP {st} len={len(page)} 条数={n} 最新={mid} @ {tm}")
    except Exception as e:
        print(f"[{name}] 失败: {type(e).__name__} {e}")

print("-" * 60)
print("微博官方 JSON 接口:")
try:
    st, body = get(f"https://m.weibo.cn/api/container/getIndex?type=uid&value={UID}&containerid=107603{UID}", UA)
    d = json.loads(body)
    cards = d.get("data", {}).get("cards", [])
    print(f"  HTTP {st} ok={d.get('ok')} cards={len(cards)}")
    for c in cards[:2]:
        mb = c.get("mblog", {})
        print("   ", mb.get("id"), mb.get("created_at"), (mb.get("text", "")[:30]))
except Exception as e:
    print(f"  失败: {type(e).__name__} {e}")

print("-" * 60)
print("第三方代理 r.jina.ai:")
try:
    st, body = get(f"https://r.jina.ai/http://www.sina.cn/media/{UID}", UA_PC, timeout=40)
    n, mid, tm = probe_html(body)
    print(f"  HTTP {st} len={len(body)} 条数={n} 最新={mid} @ {tm}")
    if n == 0:
        print("  片段:", body[:300].replace("\n", " "))
except Exception as e:
    print(f"  失败: {type(e).__name__} {e}")

print("-" * 60)
print("60 秒后复查原入口（判断是否为静态快照）:")
time.sleep(60)
try:
    st, page = get(f"http://www.sina.cn/media/{UID}")
    n, mid, tm = probe_html(page)
    print(f"  HTTP {st} len={len(page)} 条数={n} 最新={mid} @ {tm}")
except Exception as e:
    print(f"  失败: {e}")
