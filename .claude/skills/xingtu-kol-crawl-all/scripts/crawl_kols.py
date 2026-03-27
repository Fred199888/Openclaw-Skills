#!/usr/bin/env python3
"""
巨量星图 KOL 全量抓取脚本

API: POST https://www.xingtu.cn/gw/api/gsearch/search_for_author_square
鉴权: Cookie + x-secsdk-csrf-token
分页: page_param.page (从1开始), page_param.limit
"""

import argparse
import csv
import json
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Tuple

API_URL = "https://www.xingtu.cn/gw/api/gsearch/search_for_author_square"


def load_env_file(env_path: Path, *, override: bool = False) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        k = k.strip()
        v = v.strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        if not k:
            continue
        if override or k not in os.environ:
            os.environ[k] = v


def env_required(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v:
        raise RuntimeError(f"missing env: {name}")
    return v


def build_payload(keyword: str, page: int, limit: int) -> dict:
    return {
        "scene_param": {
            "platform_source": 1,
            "search_scene": 1,
            "display_scene": 1,
            "task_category": 1,
            "marketing_target": 1,
            "first_industry_id": 0,
        },
        "page_param": {
            "page": str(page),
            "limit": str(limit),
        },
        "sort_param": {
            "sort_field": {"field_name": "score"},
            "sort_type": 2,
        },
        "attribute_filter": [
            {
                "field": {"field_name": "price_by_video_type__ge", "rel_id": "2"},
                "field_value": "0",
            }
        ],
        "search_param": {
            "seach_type": 3,
            "keyword": keyword,
            "time_range_days": 180,
            "is_new_content_query": True,
        },
    }


def _auth_headers(cookie: str, csrf_token: str) -> dict:
    return {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "agw-js-conv": "str",
        "content-type": "application/json",
        "origin": "https://www.xingtu.cn",
        "referer": "https://www.xingtu.cn/ad/creator/market",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
        ),
        "cookie": cookie,
        "x-secsdk-csrf-token": csrf_token,
        "x-login-source": "1",
    }


def fetch_page(payload: dict, cookie: str, csrf_token: str) -> dict:
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=_auth_headers(cookie, csrf_token),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore"))


CONTACT_URL = "https://www.xingtu.cn/gw/api/ggeneric/apply_contact_info"


def fetch_wechat(star_id: str, cookie: str, csrf_token: str) -> str:
    url = f"{CONTACT_URL}?dest_id={star_id}&contact_type=3"
    h = _auth_headers(cookie, csrf_token)
    h.pop("content-type", None)
    r = urllib.request.Request(url, headers=h, method="GET")
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            obj = json.loads(resp.read().decode("utf-8", errors="ignore"))
        if obj.get("base_resp", {}).get("status_code") == 0:
            return (obj.get("wechat") or "").strip()
    except Exception:
        pass
    return ""


def _safe_int(v) -> int:
    if v is None or v == "":
        return 0
    try:
        return int(float(str(v)))
    except (ValueError, TypeError):
        return 0


def _safe_float(v) -> float:
    if v is None or v == "":
        return 0.0
    try:
        return float(str(v))
    except (ValueError, TypeError):
        return 0.0


def _parse_json_str(s):
    if not s or not isinstance(s, str):
        return None
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return None


def _extract_content_tags(attr: dict) -> List[str]:
    raw = attr.get("content_theme_labels_180d", "")
    items = _parse_json_str(raw)
    if not isinstance(items, list):
        return []
    out: List[str] = []
    for item in items:
        if isinstance(item, str):
            s = item.strip()
            if s and s not in out:
                out.append(s)
        elif isinstance(item, dict):
            label = item.get("label", "")
            if label and label not in out:
                out.append(label)
    return out


def _extract_author_category(attr: dict) -> str:
    raw = attr.get("tags_relation", "")
    obj = _parse_json_str(raw)
    if isinstance(obj, dict):
        keys = list(obj.keys())
        if keys:
            return keys[0]
    return ""


def _extract_recent_videos(attr: dict, limit: int = 2) -> List[dict]:
    raw = attr.get("last_10_items", "")
    items = _parse_json_str(raw)
    if not isinstance(items, list):
        return []
    out: List[dict] = []
    for item in items[:limit]:
        if isinstance(item, dict):
            item_id = str(item.get("item_id", "")).strip()
            if item_id:
                out.append({
                    "item_id": item_id,
                    "title": item.get("item_title", ""),
                    "url": f"https://www.douyin.com/video/{item_id}",
                })
    return out


def normalize(author: dict) -> dict:
    star_id = str(author.get("star_id", "")).strip()
    attr = author.get("attribute_datas") or {}

    videos = _extract_recent_videos(attr, limit=2)
    content_tags = _extract_content_tags(attr)
    author_category = _extract_author_category(attr)

    province = (attr.get("province") or "").strip()
    city = (attr.get("city") or "").strip()
    location = f"{province} {city}".strip()

    return {
        "name": (attr.get("nick_name") or "").strip(),
        "starId": star_id,
        "coreUserId": (attr.get("core_user_id") or "").strip(),
        "follower": _safe_int(attr.get("follower")),
        "location": location,
        "authorCategory": author_category,
        "contentTags": content_tags,
        "linkedUserCount": _safe_int(attr.get("link_link_cnt_by_industry")),
        "expectedCpm": _safe_float(attr.get("prospective_20_60_cpm")),
        "expectedPlayNum": _safe_int(attr.get("expected_play_num")),
        "interactRate30d": _safe_float(attr.get("interact_rate_within_30d")),
        "playOverRate30d": _safe_float(attr.get("play_over_rate_within_30d")),
        "fansIncrement30d": _safe_int(attr.get("fans_increment_within_30d")),
        "price1_20": _safe_int(attr.get("price_1_20")),
        "price20_60": _safe_int(attr.get("price_20_60")),
        "price60": _safe_int(attr.get("price_60")),
        "spreadIndex": _safe_float(attr.get("link_spread_index")),
        "shoppingIndex": _safe_float(attr.get("link_shopping_index")),
        "convertIndex": _safe_float(attr.get("link_convert_index")),
        "recentVideoUrl": videos[0]["url"] if videos else "",
        "recentVideoUrl2": videos[1]["url"] if len(videos) > 1 else "",
        "xingtHomeUrl": f"https://www.xingtu.cn/ad/creator/author/douyin/{star_id}" if star_id else "",
    }


def crawl(keyword: str, page_size: int, max_pages: int) -> Tuple[List[dict], List[dict]]:
    cookie = env_required("XINGTU_COOKIE")
    csrf_token = env_required("XINGTU_CSRF_TOKEN")

    uniq: Dict[str, dict] = {}
    page_logs: List[dict] = []
    consecutive_empty = 0

    for page in range(1, max_pages + 1):
        payload = build_payload(keyword=keyword, page=page, limit=page_size)
        res = fetch_page(payload, cookie=cookie, csrf_token=csrf_token)

        base_resp = res.get("base_resp") or {}
        if base_resp.get("status_code") != 0:
            raise RuntimeError(f"api failed on page {page}: {base_resp}")

        pagination = res.get("pagination") or {}
        authors = res.get("authors") or []

        if not authors:
            page_logs.append({"page": page, "count": 0, "new": 0, "total": len(uniq)})
            consecutive_empty += 1
            if consecutive_empty >= 3:
                break
            continue

        consecutive_empty = 0
        before = len(uniq)
        for author in authors:
            row = normalize(author)
            key = row.get("starId", "").strip()
            if not key:
                continue
            if key not in uniq:
                uniq[key] = row

        new_cnt = len(uniq) - before
        page_logs.append({
            "page": page,
            "count": len(authors),
            "new": new_cnt,
            "total": len(uniq),
            "total_available": pagination.get("total_count", 0),
        })

        if not pagination.get("has_more", False):
            break

        if new_cnt == 0 and page >= 3:
            consecutive_empty += 1
            if consecutive_empty >= 3:
                break

    # 批量获取微信号（并发20）
    rows_list = list(uniq.values())
    wechat_concurrency = max(1, int(os.getenv("XINGTU_WECHAT_CONCURRENCY", "20")))

    def _fetch_wx(star_id: str) -> Tuple[str, str]:
        try:
            return star_id, fetch_wechat(star_id, cookie, csrf_token)
        except Exception:
            return star_id, ""

    star_ids = [r["starId"] for r in rows_list if r.get("starId")]
    if star_ids:
        done = 0
        wx_cache: Dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=wechat_concurrency) as ex:
            futures = [ex.submit(_fetch_wx, sid) for sid in star_ids]
            for fut in as_completed(futures):
                sid, wx = fut.result()
                if wx:
                    wx_cache[sid] = wx
                done += 1
                if done % 100 == 0:
                    print(f"wechat progress={done}/{len(star_ids)} found={len(wx_cache)}", flush=True)
        print(f"wechat done: {len(wx_cache)}/{len(star_ids)} found", flush=True)
        for row in rows_list:
            row["wechat"] = wx_cache.get(row.get("starId", ""), "")

    return rows_list, page_logs


def write_outputs(rows: List[dict], keyword: str, out_dir: Path) -> Tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    safe_kw = "".join(ch if ch.isalnum() else "_" for ch in keyword).strip("_") or "kw"

    json_path = out_dir / f"kols_{safe_kw}_{ts}.json"
    csv_path = out_dir / f"kols_{safe_kw}_{ts}.csv"

    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    fields = [
        "name", "starId", "coreUserId", "follower", "location",
        "authorCategory", "contentTags", "linkedUserCount",
        "expectedCpm", "expectedPlayNum",
        "interactRate30d", "playOverRate30d", "fansIncrement30d",
        "price1_20", "price20_60", "price60",
        "spreadIndex", "shoppingIndex", "convertIndex",
        "recentVideoUrl", "recentVideoUrl2", "xingtHomeUrl",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})

    return json_path, csv_path


def main():
    ap = argparse.ArgumentParser(description="Crawl KOLs from Xingtu (巨量星图)")
    ap.add_argument("--keyword", required=True)
    ap.add_argument("--page-size", type=int, default=20)
    ap.add_argument("--max-pages", type=int, default=200)
    ap.add_argument("--out-dir", default=str(Path(__file__).resolve().parents[1] / "output"))
    ap.add_argument("--env", default=str(Path(__file__).resolve().parents[1] / ".env"))
    ap.add_argument("--global-env", default=str(Path.home() / ".claude/skills/xhs-global.env"))
    args = ap.parse_args()

    load_env_file(Path(args.global_env))
    load_env_file(Path(args.env), override=True)

    rows, logs = crawl(keyword=args.keyword, page_size=args.page_size, max_pages=args.max_pages)
    json_path, csv_path = write_outputs(rows, keyword=args.keyword, out_dir=Path(args.out_dir))

    print(f"keyword={args.keyword}")
    for lg in logs:
        print(f"page={lg['page']} count={lg['count']} new={lg['new']} total={lg['total']}")
    print(f"done total_unique={len(rows)}")
    print(f"json={json_path}")
    print(f"csv={csv_path}")


if __name__ == "__main__":
    main()
