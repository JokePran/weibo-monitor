#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
监控微博用户「挖地瓜的超级鹿鼎公」(UID 3962719063)，
在 A 股交易日交易时段（9:30-15:00，含午休）抓取其新微博，
并通过 pushplus 推送到手机。

数据源：sina.cn 移动端镜像页（服务端渲染，稳定、无需登录）。
去重：以每条微博的唯一 mid 为标识，状态存于 state.json。

用法：
    python3 monitor.py              # 正常运行（时段外自动跳过）
    python3 monitor.py --dry-run    # 只抓取解析，不推送（本地测试用）
    python3 monitor.py --force      # 忽略时段与节假日限制，强制检查一次
    python3 monitor.py --init       # 强制把当前最新微博设为已读基准
"""

import os
import re
import sys
import json
import html
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

# ----------------------------- 配置区 -----------------------------
UID = "3962719063"
AUTHOR = "挖地瓜的超级鹿鼎公"
# 重要：裸地址会被 CDN 长期缓存（实测滞后 1 小时以上），
# 必须带查询参数才能拿到实时内容。同时抓多个入口再合并，双保险。
MIRROR_URL = f"http://www.sina.cn/media/{UID}"
MIRROR_URLS = [
    f"https://www.sina.cn/media/{UID}?page=1",   # 实测实时
    f"https://www.sina.cn/media/{UID}?vt=4",     # 实测实时
    f"http://www.sina.cn/media/{UID}",           # 裸地址（可能滞后，作兜底）
]
DETAIL_BASE = "https://www.sina.cn/news/detail"

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "")
PUSHPLUS_URL = "https://www.pushplus.plus/send"

# 北京时间固定 UTC+8（A 股无夏令时）
CST = timezone(timedelta(hours=8))

# 交易时段（北京时间），含午休 11:30-13:00
SESSION_START = (9, 30)
SESSION_END = (15, 0)

# 2026 年 A 股休市日（工作日中休市的日期，来源：沪深交易所官方通知）
# 每年更新一次即可；格式 YYYY-MM-DD
HOLIDAYS_2026 = {
    # 元旦
    "2026-01-01", "2026-01-02",
    # 春节
    "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20", "2026-02-23",
    # 清明
    "2026-04-06",
    # 劳动节
    "2026-05-01", "2026-05-04", "2026-05-05",
    # 端午
    "2026-06-19",
    # 中秋
    "2026-09-25",
    # 国庆
    "2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07",
}

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1")
# --------------------------- 配置区结束 ---------------------------


def log(msg):
    print(f"[{datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def now_bj():
    return datetime.now(CST)


def is_trading_day(d: datetime) -> bool:
    """是否 A 股交易日：周一至周五，且不在法定休市日。"""
    if d.weekday() >= 5:  # 5=周六, 6=周日
        return False
    if d.strftime("%Y-%m-%d") in HOLIDAYS_2026:
        return False
    return True


def in_session(d: datetime) -> bool:
    """是否在交易时段 9:30-15:00（北京时间，含午休）。"""
    t = (d.hour, d.minute)
    return SESSION_START <= t <= SESSION_END


def fetch_html(url: str, retries: int = 3) -> str:
    """带重试的 HTTP GET。"""
    last_err = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml",
            })
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception as e:  # noqa: BLE001
            last_err = e
            log(f"抓取失败({i + 1}/{retries}): {e}")
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"抓取最终失败: {last_err}")


def fetch_all_posts():
    """抓取多个镜像入口，解析后按 mid 合并去重，返回按时间正序的列表。

    任一入口成功即可工作；某个入口滞后时，其他入口的新内容仍能补上。
    """
    merged = {}
    ok_count = 0
    for url in MIRROR_URLS:
        try:
            page = fetch_html(url, retries=2)
        except Exception as e:  # noqa: BLE001
            log(f"入口失败 {url}: {e}")
            continue
        posts = parse_posts(page)
        if not posts:
            log(f"入口无数据 {url}")
            continue
        ok_count += 1
        newest = posts[-1]
        log(f"入口 {url} → {len(posts)} 条，最新 {newest['time']} (mid={newest['mid']})")
        for p in posts:
            merged[p["mid"]] = p
    if ok_count == 0:
        return []
    return sorted(merged.values(), key=lambda p: mid_num(p["mid"]))


def clean(text: str) -> str:
    """去掉 HTML 标签、反转义、压缩空白。"""
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_posts(page: str):
    """从镜像页 HTML 解析微博列表，按时间从旧到新返回。"""
    # 每条微博被 <a class="post-link" href="/news/detail/MID.html"> ... </article></a> 包裹
    chunks = re.findall(
        r'<a class="post-link" href="/news/detail/(\d+)\.html".*?</article>\s*</a>',
        page, re.S,
    )
    posts = []
    for chunk in re.finditer(
        r'<a class="post-link" href="/news/detail/(\d+)\.html"(.*?)</article>\s*</a>',
        page, re.S,
    ):
        mid, body = chunk.group(1), chunk.group(2)
        tm = re.search(r'class="time">\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})', body)
        tx = re.search(r'class="post-text">(.*?)</div>', body, re.S)
        rp = re.search(r'class="post-repost">(.*?)</div>', body, re.S)
        posts.append({
            "mid": mid,
            "time": tm.group(1) if tm else "",
            "text": clean(tx.group(1)) if tx else "",
            "repost": clean(rp.group(1)) if rp else "",
            "link": f"{DETAIL_BASE}/{mid}.html",
        })
    # 页面是时间倒序（最新在前），反转成时间正序，推送时按发文顺序
    posts.reverse()
    return posts


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        log(f"读取 state.json 失败，将重建: {e}")
        return {}


def save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def mid_num(mid: str) -> int:
    try:
        return int(mid)
    except ValueError:
        return 0


def parse_post_time(p: dict):
    """把微博的 'YYYY-MM-DD HH:MM' 解析为北京时间 datetime，失败返回 None。"""
    t = (p.get("time") or "").strip()
    try:
        return datetime.strptime(t, "%Y-%m-%d %H:%M").replace(tzinfo=CST)
    except ValueError:
        return None


def post_in_session(p: dict, now: datetime) -> bool:
    """该微博是否属于「当天交易时段内发布」——只推这类。

    规则：日期必须与当前交易日相同，且时间在 09:30-15:00 之间。
    这样隔夜、开盘前、收盘后发布的微博即使比基准新，也不会被补推。
    时间解析不出来时按「不推」处理（宁可少推，也不要把隔夜内容灌给用户）。
    """
    dt = parse_post_time(p)
    if dt is None:
        return False
    if dt.strftime("%Y-%m-%d") != now.strftime("%Y-%m-%d"):
        return False
    return SESSION_START <= (dt.hour, dt.minute) <= SESSION_END


def build_message(p: dict) -> tuple:
    """构造一条推送的标题与 HTML 正文。"""
    title = f"{AUTHOR} · {p['time'][-5:] if p['time'] else '新微博'}"
    parts = [
        f'<div style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,PingFang SC,sans-serif;'
        f'font-size:15px;line-height:1.7;color:#222;">',
        f'<div style="font-size:12px;color:#888;margin-bottom:8px;">{p["time"]}</div>',
    ]
    if p["text"]:
        parts.append(f'<div style="margin-bottom:10px;">{html.escape(p["text"])}</div>')
    if p["repost"]:
        parts.append(
            f'<div style="border-left:3px solid #ff8200;background:#fafafa;'
            f'padding:8px 12px;margin:8px 0;color:#555;">'
            f'转发：{html.escape(p["repost"])}</div>'
        )
    parts.append(
        f'<div style="margin-top:12px;font-size:13px;">'
        f'<a href="{p["link"]}" style="color:#5c7a99;">查看微博原文 →</a></div>'
    )
    parts.append("</div>")
    return title, "".join(parts)


def push_to_wechat(title: str, content: str) -> int:
    """通过 pushplus 推送（HTML 模板）。

    返回 pushplus 的 code：
        200 = 成功
        900 = 当日请求次数已用尽（配额耗尽，当天不该再试）
        -1  = 网络异常 / 其它未知失败
    """
    if not PUSHPLUS_TOKEN:
        log("未设置 PUSHPLUS_TOKEN 环境变量，跳过推送")
        return -1
    data = json.dumps({
        "token": PUSHPLUS_TOKEN,
        "title": title,
        "content": content,
        "template": "html",
    }).encode("utf-8")
    req = urllib.request.Request(
        PUSHPLUS_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        log(f"推送失败（网络）: {e}")
        return -1
    code = result.get("code")
    if code == 200:
        log(f"推送成功: {title}")
        return 200
    log(f"推送返回异常: {result}")
    return code if isinstance(code, int) else -1


def main():
    args = set(sys.argv[1:])
    dry_run = "--dry-run" in args
    force = "--force" in args
    do_init = "--init" in args

    now = now_bj()

    # 时段与交易日判断
    if not force:
        if not is_trading_day(now):
            log(f"非交易日（{now.strftime('%Y-%m-%d %A')}），跳过")
            return
        if not in_session(now):
            log(f"非交易时段（{now.strftime('%H:%M')}），跳过")
            return

    log(f"开始检查 {AUTHOR} 的微博 ...")
    posts = fetch_all_posts()
    if not posts:
        log("所有入口均未解析到微博，页面结构可能变化，跳过")
        return
    log(f"解析到 {len(posts)} 条微博，最新: {posts[-1]['time']} (mid={posts[-1]['mid']})")

    state = load_state()
    last_mid = state.get("last_mid")
    latest_mid = posts[-1]["mid"]

    # 当日配额已耗尽时不再徒劳尝试；但每小时允许复查一次，
    # 万一配额提前恢复（或只是临时限制）能自动继续推送。
    today = now.strftime("%Y-%m-%d")
    if state.get("quota_blocked") == today and not force:
        blocked_at = state.get("quota_blocked_at")
        try:
            last_try = datetime.fromisoformat(blocked_at) if blocked_at else None
        except ValueError:
            last_try = None
        if last_try and (now - last_try) < timedelta(hours=1):
            log(f"今日 pushplus 请求配额已用尽（{today}），本小时不再尝试推送，稍后复查")
            return
        log("配额熔断满 1 小时，复查一次是否已恢复")

    # 首次运行 / 强制初始化：只记录基准，不推送历史微博
    if do_init or not last_mid:
        save_state({"last_mid": latest_mid,
                    "initialized_at": now.isoformat(),
                    "last_check": now.isoformat()})
        log(f"已初始化已读基准 mid={latest_mid}，本次不推送历史微博")
        return

    # 找出比 last_mid 更新的微博（基准之后的所有候选）
    base = mid_num(last_mid)
    candidates = [p for p in posts if mid_num(p["mid"]) > base]

    if not candidates:
        state["last_check"] = now.isoformat()
        save_state(state)
        log("没有新微博")
        return

    log(f"基准之后共 {len(candidates)} 条，逐条判断是否在交易时段内（09:30-15:00 当天）")

    pushed = 0        # 本轮实际推送条数
    skipped = 0       # 因不在交易时段而跳过条数
    stopped = False   # 遇到推送失败提前中止
    quota_hit = False  # 当日配额耗尽

    for p in candidates:
        in_window = post_in_session(p, now)

        if in_window and not dry_run:
            title, content = build_message(p)
            code = push_to_wechat(title, content)
            if code == 900:
                # 当日请求次数已用尽：继续尝试只会白费，标记后本日停止推送
                quota_hit = True
                stopped = True
                state["quota_blocked"] = today
                state["quota_blocked_at"] = now.isoformat()
                save_state(state)
                log("pushplus 当日配额已用尽（code 900），本日停止推送；该条未送达")
                break
            if code != 200:
                # 其它失败：立刻停止本轮，不推进 last_mid，
                # 下一轮从这条继续，已经推成功的不会重推。
                stopped = True
                log(f"推送失败，本轮中止（{p['time']}），下一轮从此条重试")
                break
            time.sleep(2)  # pushplus 限 5 次/分钟，逐条之间留间隔

        if in_window:
            if dry_run:
                log(f"[DRY-RUN] 将推送: {p['time']} | {p['text'][:60]}")
            pushed += 1
            if not dry_run:
                state["total_pushed"] = state.get("total_pushed", 0) + 1
        else:
            skipped += 1
            log(f"跳过（非交易时段）: {p['time']} mid={p['mid']}")

        # 每条处理完立即推进并落盘：既跨过不推的微博，也防止重复推送
        if not dry_run:
            state["last_mid"] = p["mid"]
            state["last_check"] = now.isoformat()
            save_state(state)

    if dry_run:
        log(f"[DRY-RUN] 将推送 {pushed} 条，跳过 {skipped} 条；不更新状态")
        return

    if skipped and pushed == 0 and not stopped:
        log(f"本轮无交易时段内新微博（跳过 {skipped} 条隔夜/非时段内容）")

    state["last_check"] = now.isoformat()
    save_state(state)
    log(f"本轮结束：推送 {pushed} 条，跳过 {skipped} 条，累计推送 {state.get('total_pushed', 0)} 条")
    if quota_hit:
        log("提示：pushplus 免费额度按自然日重置，明天会自动恢复推送")


if __name__ == "__main__":
    main()
