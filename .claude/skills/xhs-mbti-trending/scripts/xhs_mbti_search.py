#!/usr/bin/env python3
"""小红书 MBTI 热帖采集脚本

从 Chrome 浏览器提取小红书 cookies，注入到 Playwright 有头浏览器中，
在搜索框输入 MBTI 搜索，滚动加载帖子，逐条获取详情。

依赖: pip3 install playwright pycookiecheat
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta

from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout
from pycookiecheat import chrome_cookies

# 输出目录：Skill 目录下的 data/
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
XHS_DOMAIN = "https://www.xiaohongshu.com"

TARGET_COUNT = 50
MAX_SCROLL_ROUNDS = 40
SCROLL_PAUSE = 2.5
DETAIL_PAUSE = 2.0


def parse_count(text: str) -> int:
    if not text:
        return 0
    text = text.strip()
    if "万" in text:
        try:
            return int(float(text.replace("万", "")) * 10000)
        except ValueError:
            return 0
    try:
        return int(text)
    except ValueError:
        return 0


def parse_relative_time(text: str) -> str | None:
    if not text:
        return None
    text = text.strip()
    now = datetime.now()

    if "刚刚" in text:
        return now.strftime("%Y-%m-%d %H:%M")
    m = re.match(r"(\d+)\s*分钟前", text)
    if m:
        return (now - timedelta(minutes=int(m.group(1)))).strftime("%Y-%m-%d %H:%M")
    m = re.match(r"(\d+)\s*小时前", text)
    if m:
        return (now - timedelta(hours=int(m.group(1)))).strftime("%Y-%m-%d %H:%M")
    m = re.match(r"(\d+)\s*天前", text)
    if m:
        return (now - timedelta(days=int(m.group(1)))).strftime("%Y-%m-%d %H:%M")
    m = re.match(r"昨天\s*(\d{1,2}):(\d{2})", text)
    if m:
        dt = now - timedelta(days=1)
        return dt.strftime(f"%Y-%m-%d {m.group(1).zfill(2)}:{m.group(2)}")
    m = re.match(r"前天\s*(\d{1,2}):(\d{2})", text)
    if m:
        dt = now - timedelta(days=2)
        return dt.strftime(f"%Y-%m-%d {m.group(1).zfill(2)}:{m.group(2)}")
    m = re.match(r"(\d{1,2})-(\d{1,2})$", text)
    if m:
        return f"{now.year}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)} 00:00"
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)} 00:00"
    return text


def is_within_week(time_str: str) -> bool:
    if not time_str:
        return True
    try:
        dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
        return dt >= datetime.now() - timedelta(days=7)
    except ValueError:
        return True


def inject_chrome_cookies(context):
    """从 Chrome 提取小红书 cookies 并注入到 Playwright context"""
    print("从 Chrome 提取小红书 cookies...")
    raw_cookies = chrome_cookies(XHS_DOMAIN)
    print(f"  获取到 {len(raw_cookies)} 个 cookie")

    pw_cookies = []
    for name, value in raw_cookies.items():
        pw_cookies.append({
            "name": name,
            "value": value,
            "domain": ".xiaohongshu.com",
            "path": "/",
        })
    context.add_cookies(pw_cookies)
    print("  cookies 已注入到浏览器")


def dismiss_popup(page):
    """关闭弹窗/遮罩"""
    page.evaluate("""() => {
        document.querySelectorAll('.reds-mask, [class*="login-mask"], [class*="overlay"]').forEach(el => el.remove());
        document.querySelectorAll('[class*="login-container"], [class*="login-modal"], [class*="sign-"]').forEach(el => el.remove());
        document.querySelectorAll('.close-button, [class*="close"], [aria-label*="关闭"]').forEach(el => {
            try { el.click(); } catch(e) {}
        });
    }""")
    time.sleep(0.3)
    page.keyboard.press("Escape")
    time.sleep(0.3)


def collect_search_results(page) -> list[dict]:
    """从搜索结果页收集帖子基本信息"""
    posts = []
    seen_ids = set()

    for scroll_round in range(MAX_SCROLL_ROUNDS):
        cards = page.query_selector_all("section.note-item")

        for card in cards:
            try:
                link_el = card.query_selector('a[href*="/explore/"]')
                if not link_el:
                    continue
                href = link_el.get_attribute("href") or ""
                note_id_match = re.search(r"/explore/([a-f0-9]{24})", href)
                if not note_id_match:
                    continue
                note_id = note_id_match.group(1)
                if note_id in seen_ids:
                    continue
                seen_ids.add(note_id)

                cover_link = card.query_selector("a.cover")
                detail_href = ""
                if cover_link:
                    detail_href = cover_link.get_attribute("href") or ""
                    if detail_href.startswith("/"):
                        detail_href = f"{XHS_DOMAIN}{detail_href}"

                title_el = card.query_selector(".footer .title span")
                title = title_el.inner_text().strip() if title_el else ""

                name_el = card.query_selector(".author .name")
                author = name_el.inner_text().strip() if name_el else ""

                author_link_el = card.query_selector("a.author")
                author_url = ""
                if author_link_el:
                    au_href = author_link_el.get_attribute("href") or ""
                    if au_href.startswith("/"):
                        au_href = f"{XHS_DOMAIN}{au_href}"
                    author_url = au_href

                count_el = card.query_selector(".like-wrapper .count")
                likes = parse_count(count_el.inner_text()) if count_el else 0

                img_el = card.query_selector("a.cover img")
                cover_url = img_el.get_attribute("src") or "" if img_el else ""

                post_url = detail_href or f"{XHS_DOMAIN}/explore/{note_id}"

                posts.append({
                    "note_id": note_id,
                    "title": title,
                    "author": author,
                    "author_url": author_url,
                    "likes": likes,
                    "cover_url": cover_url,
                    "post_url": post_url,
                })
            except Exception:
                continue

        print(f"  第 {scroll_round + 1} 轮滚动，已收集 {len(posts)} 条帖子（去重后）")

        if len(posts) >= TARGET_COUNT * 2:
            break

        page.evaluate("window.scrollBy(0, window.innerHeight)")
        time.sleep(SCROLL_PAUSE)

    return posts


def fetch_post_detail(context, post: dict) -> dict:
    """新开 tab 获取详情"""
    detail_page = context.new_page()
    try:
        detail_page.goto(post["post_url"], wait_until="domcontentloaded", timeout=15000)
        time.sleep(DETAIL_PAUSE)
        dismiss_popup(detail_page)

        time_el = detail_page.query_selector("span.date, [class*='date']")
        raw_time = time_el.inner_text().strip() if time_el else ""
        post["publish_time"] = parse_relative_time(raw_time) or ""

        content_el = detail_page.query_selector("#detail-desc, [class*='desc'], .note-text")
        text = content_el.inner_text().strip() if content_el else ""
        post["summary"] = text[:200] if text else ""

        like_el = detail_page.query_selector(".like-wrapper .count, [class*='like'] .count")
        if like_el:
            post["likes"] = max(post["likes"], parse_count(like_el.inner_text()))

        collect_el = detail_page.query_selector(".collect-wrapper .count, [class*='collect'] .count")
        post["collects"] = parse_count(collect_el.inner_text()) if collect_el else 0

        comment_el = detail_page.query_selector(".chat-wrapper .count, [class*='chat'] .count")
        post["comments"] = parse_count(comment_el.inner_text()) if comment_el else 0

        if not post.get("author"):
            a = detail_page.query_selector(".username, [class*='username']")
            if a:
                post["author"] = a.inner_text().strip()
        if not post.get("title"):
            t = detail_page.query_selector("#detail-title, [class*='title']")
            if t:
                post["title"] = t.inner_text().strip()

    except PwTimeout:
        print(f"    详情页超时: {post['note_id']}")
        _defaults(post)
    except Exception as e:
        print(f"    详情页异常: {post['note_id']}: {e}")
        _defaults(post)
    finally:
        detail_page.close()
    return post


def _defaults(post):
    post.setdefault("publish_time", "")
    post.setdefault("summary", "")
    post.setdefault("collects", 0)
    post.setdefault("comments", 0)


def generate_markdown(data: dict) -> str:
    lines = [
        f"# 小红书 MBTI 热帖 Top {data['total_posts']}",
        "", f"- 采集时间: {data['fetch_time']}",
        f"- 关键词: {data['keyword']}",
        f"- 时间范围: {data['time_range']}",
        f"- 帖子总数: {data['total_posts']}", "", "---", "",
    ]
    for p in data["posts"]:
        lines.extend([
            f"## {p['rank']}. {p['title'] or '(无标题)'}", "",
            f"- 作者: [{p['author'] or '未知'}]({p.get('author_url', '')})",
            f"- 发布时间: {p.get('publish_time', '未知')}",
            f"- 点赞: {p['likes']} | 评论: {p.get('comments', 0)} | 收藏: {p.get('collects', 0)}",
            f"- 链接: [{p['note_id']}]({p['post_url']})", "",
        ])
        if p.get("summary"):
            s = p["summary"][:100] + ("..." if len(p["summary"]) > 100 else "")
            lines.extend([f"> {s}", ""])
        lines.extend(["---", ""])
    return "\n".join(lines)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")

    print("开始采集小红书 MBTI 热帖...")
    print(f"目标: 近一周 Top {TARGET_COUNT}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )

        # 从 Chrome 提取 cookies 注入
        inject_chrome_cookies(context)

        page = context.new_page()

        # 打开小红书首页
        print("打开小红书首页...")
        page.goto(XHS_DOMAIN, wait_until="networkidle", timeout=30000)
        time.sleep(2)
        dismiss_popup(page)

        # 在搜索框中输入 MBTI 并搜索
        print("在搜索框中搜索 MBTI...")
        search_input = page.query_selector(
            '#search-input, input[placeholder*="搜索"], input[class*="search"]'
        )
        if search_input:
            try:
                search_input.click(timeout=5000)
                time.sleep(0.5)
                search_input.fill("MBTI")
                time.sleep(0.5)
                search_input.press("Enter")
                print("  搜索已提交")
                time.sleep(3)
            except Exception as e:
                print(f"  搜索框操作失败({e})，使用 URL 导航...")
                page.goto(
                    f"{XHS_DOMAIN}/search_result?keyword=MBTI&type=1",
                    wait_until="networkidle", timeout=30000,
                )
                time.sleep(3)
        else:
            print("  未找到搜索框，使用 URL 导航...")
            page.goto(
                f"{XHS_DOMAIN}/search_result?keyword=MBTI&type=1",
                wait_until="networkidle", timeout=30000,
            )
            time.sleep(3)

        dismiss_popup(page)

        # 确认搜索结果加载
        page.wait_for_selector("section.note-item", timeout=10000)
        print("搜索结果已加载")

        print("开始滚动加载帖子...")
        raw_posts = collect_search_results(page)
        print(f"搜索页共收集 {len(raw_posts)} 条帖子")

        if not raw_posts:
            debug_path = os.path.join(OUTPUT_DIR, "debug_screenshot.png")
            page.screenshot(path=debug_path)
            print(f"未收集到帖子，截图已保存: {debug_path}")
            browser.close()
            sys.exit(1)

        # 获取详情
        print("开始获取帖子详情...")
        detailed = []
        for i, post in enumerate(raw_posts):
            label = post["title"][:30] if post.get("title") else post["note_id"]
            print(f"  [{i+1}/{len(raw_posts)}] {label}")
            post = fetch_post_detail(context, post)
            detailed.append(post)

            week = [p for p in detailed if is_within_week(p.get("publish_time", ""))]
            if len(week) >= TARGET_COUNT + 10:
                print(f"  已有 {len(week)} 条近一周帖子，停止")
                break

        week_posts = [p for p in detailed if is_within_week(p.get("publish_time", ""))]
        week_posts.sort(key=lambda x: x.get("likes", 0), reverse=True)
        top = week_posts[:TARGET_COUNT]
        for i, post in enumerate(top):
            post["rank"] = i + 1

        browser.close()

    data = {
        "fetch_time": now.isoformat(timespec="seconds"),
        "keyword": "MBTI",
        "total_posts": len(top),
        "time_range": "近一周",
        "posts": top,
    }

    json_path = os.path.join(OUTPUT_DIR, f"mbti_trending_{timestamp}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"JSON: {json_path}")

    md_path = os.path.join(OUTPUT_DIR, f"mbti_trending_{timestamp}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(generate_markdown(data))
    print(f"Markdown: {md_path}")

    latest_path = os.path.join(OUTPUT_DIR, "latest.json")
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"latest.json: {latest_path}")

    print(f"\n{'=' * 60}")
    print(f"采集完成！共 {len(top)} 条近一周 MBTI 热帖")
    print(f"{'=' * 60}")
    print(f"\nTop 10:")
    for post in top[:10]:
        print(f"  {post['rank']:2d}. [{post['likes']:>6d} 赞] {post.get('title', '(无标题)')[:40]}")

    return data


if __name__ == "__main__":
    main()
