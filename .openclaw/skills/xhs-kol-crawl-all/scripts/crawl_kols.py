#!/usr/bin/env python3
import argparse
import csv
import json
import os
import time
import uuid
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Tuple

API_URL = "https://pgy.xiaohongshu.com/api/solar/cooperator/blogger/v2"
NOTE_DETAIL_URL = "https://pgy.xiaohongshu.com/api/solar/note/{note_id}/detail?bizCode={biz_code}"


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


def build_payload(keyword: str, page_num: int, page_size: int, brand_user_id: str, track_id: str) -> dict:
    return {
        "searchType": 1,
        "keyword": keyword,
        "column": "comprehensiverank",
        "sort": "desc",
        "pageNum": page_num,
        "pageSize": page_size,
        "brandUserId": brand_user_id,
        "trackId": track_id,
        "marketTarget": None,
        "audienceGroup": [],
        "personalTags": [],
        "gender": None,
        "location": None,
        "signed": -1,
        "featureTags": [],
        "fansAge": 0,
        "fansGender": 0,
        "fansLocation": None,
        "fansMaritalStatus": -1,
        "fansConsumptionLevel": -1,
        "fansChildAgeInfo": [],
        "fansDevicePrice": [],
        "fansDeviceBrand": [],
        "accumCommonImpMedinNum30d": [],
        "readMidNor30": [],
        "interMidNor30": [],
        "thousandLikePercent30": [],
        "noteType": 0,
        "progressOrderCnt": [],
        "tradeType": "不限",
        "tradeReportBrandIdSet": [],
        "excludedTradeReportBrandId": False,
        "estimateCpuv30d": [],
        "inStar": 0,
        "firstIndustry": "",
        "secondIndustry": "",
        "newHighQuality": 0,
        "filterIntention": False,
        "flagList": [
            {"flagType": "HAS_BRAND_COOP_BUYER_AUTH", "flagValue": "0"},
            {"flagType": "IS_HIGH_QUALITY", "flagValue": "0"},
        ],
        "activityCodes": [],
        "excludeLowActive": False,
        "fansNumUp": 0,
        "excludedTradeReportBrand": False,
        "excludedTradeInviteReportBrand": False,
        "filterList": [],
        "contentSceneLabel": [],
    }


def _auth_headers(cookie: str, x_s: str, x_s_common: str, x_t: str, with_json_content_type: bool = True) -> dict:
    h = {
        "accept": "application/json, text/plain, */*",
        "origin": "https://pgy.xiaohongshu.com",
        "referer": "https://pgy.xiaohongshu.com/solar/pre-trade/note/kol",
        "user-agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Mobile Safari/537.36",
        "cookie": cookie,
        "x-s": x_s,
        "x-s-common": x_s_common,
        "x-t": x_t,
    }
    if with_json_content_type:
        h["content-type"] = "application/json;charset=UTF-8"
    return h


def fetch_page(payload: dict, cookie: str, x_s: str, x_s_common: str, x_t: str) -> dict:
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=_auth_headers(cookie, x_s, x_s_common, x_t, with_json_content_type=True),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore"))


def fetch_note_link(note_id: str, cookie: str, x_s: str, x_s_common: str, x_t: str, biz_code: str = "") -> str:
    if not note_id:
        return ""
    url = NOTE_DETAIL_URL.format(note_id=note_id, biz_code=urllib.parse.quote(biz_code))
    req = urllib.request.Request(
        url,
        headers=_auth_headers(cookie, x_s, x_s_common, x_t, with_json_content_type=False),
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        obj = json.loads(resp.read().decode("utf-8", errors="ignore"))
    if obj.get("code") != 0 or not obj.get("success"):
        return ""
    return ((obj.get("data") or {}).get("noteLink") or "").strip()


def _first_non_empty(*vals):
    for v in vals:
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        return v
    return None


def _extract_recent_note_ids(item: dict, limit: int = 2) -> List[str]:
    notes = item.get("noteList") or []
    out: List[str] = []
    if not isinstance(notes, list):
        return out
    for n in notes:
        note_id = (n or {}).get("noteId")
        if not note_id:
            continue
        note_id = str(note_id).strip()
        if note_id and note_id not in out:
            out.append(note_id)
        if len(out) >= limit:
            break
    return out


def _extract_content_directions(item: dict) -> List[str]:
    out: List[str] = []
    for t in item.get("contentTags") or []:
        if not isinstance(t, dict):
            continue
        t1 = t.get("taxonomy1Tag")
        if isinstance(t1, str) and t1 and t1 not in out:
            out.append(t1)
        for t2 in t.get("taxonomy2Tags") or []:
            if isinstance(t2, str) and t2 and t2 not in out:
                out.append(t2)
    return out


def normalize(item: dict) -> dict:
    # 注意：蒲公英里 fansCount 经常为 0，真实粉丝优先使用 fansNum。
    fans = _first_non_empty(item.get("fansNum"), item.get("fansCount"))
    read_mid = _first_non_empty(
        item.get("readMidNor30"),
        item.get("clickMidNum"),
        item.get("accumCommonImpMedinNum30d"),
    )
    inter_mid = _first_non_empty(
        item.get("interMidNor30"),
        item.get("interMidNum"),
        item.get("mEngagementNum"),
        item.get("mengagementNum"),
    )

    recent_ids = _extract_recent_note_ids(item, limit=2)
    recent_urls = [f"https://www.xiaohongshu.com/explore/{nid}" for nid in recent_ids]
    return {
        "name": item.get("name"),
        "redId": item.get("redId"),
        "userId": item.get("userId"),
        "location": item.get("location"),
        "businessNoteCount": item.get("businessNoteCount"),
        "fansCount": item.get("fansCount"),
        "fansNum": fans,
        "readMidNor30": read_mid,
        "interMidNor30": inter_mid,
        "picturePrice": item.get("picturePrice"),
        "videoPrice": item.get("videoPrice"),
        "lowerPrice": item.get("lowerPrice"),
        "recentNoteId": recent_ids[0] if recent_ids else "",
        "recentNoteId2": recent_ids[1] if len(recent_ids) > 1 else "",
        "recentNoteUrl": recent_urls[0] if recent_urls else "",
        "recentNoteUrl2": recent_urls[1] if len(recent_urls) > 1 else "",
        "recentNoteUrls": recent_urls,
        "contentTags": _extract_content_directions(item),
        "featureTags": item.get("featureTags") or [],
    }


def crawl(keyword: str, page_size: int, max_pages: int) -> Tuple[List[dict], List[dict]]:
    cookie = env_required("XHS_COOKIE")
    x_s = env_required("XHS_X_S")
    x_s_common = env_required("XHS_X_S_COMMON")
    x_t = env_required("XHS_X_T")
    brand_user_id = env_required("XHS_BRAND_USER_ID")
    track_id = os.getenv("XHS_TRACK_ID", "").strip() or f"kolGeneralSearch_{uuid.uuid4().hex}"
    note_detail_biz_code = os.getenv("XHS_NOTE_DETAIL_BIZ_CODE", "").strip()

    uniq: Dict[str, dict] = {}
    page_logs = []

    for page in range(1, max_pages + 1):
        payload = build_payload(keyword=keyword, page_num=page, page_size=page_size, brand_user_id=brand_user_id, track_id=track_id)
        res = fetch_page(payload, cookie=cookie, x_s=x_s, x_s_common=x_s_common, x_t=x_t)

        if res.get("code") != 0 or not res.get("success"):
            raise RuntimeError(f"api failed on page {page}: code={res.get('code')} msg={res.get('msg')}")

        data = res.get("data") or {}
        items = data.get("kols") or []

        if not items:
            page_logs.append({"page": page, "count": 0, "new": 0, "total": len(uniq)})
            break

        before = len(uniq)
        for it in items:
            key = (it.get("redId") or "").strip() or (it.get("userId") or "").strip()
            if not key:
                continue
            if key not in uniq:
                row = normalize(it)
                uid = (row.get("userId") or "").strip()
                row["trackId"] = track_id
                if uid:
                    row["pgyHomeUrl"] = (
                        "https://pgy.xiaohongshu.com/solar/pre-trade/blogger-detail/"
                        f"{uid}?track_id={urllib.parse.quote(track_id)}&source=Advertiser_Kol"
                    )
                else:
                    row["pgyHomeUrl"] = ""
                uniq[key] = row

        new_cnt = len(uniq) - before
        page_logs.append({"page": page, "count": len(items), "new": new_cnt, "total": len(uniq)})

        if new_cnt == 0 and page >= 3:
            break

    # 二次补全：调用 note detail 拿“复制小红书笔记链接”对应的 noteLink（含 xsec_token）
    rows_list = list(uniq.values())
    all_note_ids: List[str] = []
    for row in rows_list:
        for nid in [(row.get("recentNoteId") or "").strip(), (row.get("recentNoteId2") or "").strip()]:
            if nid and nid not in all_note_ids:
                all_note_ids.append(nid)

    note_link_cache: Dict[str, str] = {}
    note_detail_concurrency = max(1, int(os.getenv("XHS_NOTE_DETAIL_CONCURRENCY", "30") or "30"))

    def _fetch_one(nid: str) -> Tuple[str, str]:
        try:
            link = fetch_note_link(
                note_id=nid,
                cookie=cookie,
                x_s=x_s,
                x_s_common=x_s_common,
                x_t=x_t,
                biz_code=note_detail_biz_code,
            )
            return nid, link or ""
        except Exception:
            return nid, ""

    if all_note_ids:
        done = 0
        with ThreadPoolExecutor(max_workers=note_detail_concurrency) as ex:
            futures = [ex.submit(_fetch_one, nid) for nid in all_note_ids]
            for fut in as_completed(futures):
                nid, link = fut.result()
                note_link_cache[nid] = link
                done += 1
                if done % 100 == 0:
                    print(f"note-link progress={done}/{len(all_note_ids)}", flush=True)

    for row in rows_list:
        nid1 = (row.get("recentNoteId") or "").strip()
        nid2 = (row.get("recentNoteId2") or "").strip()
        if nid1 and note_link_cache.get(nid1):
            row["recentNoteUrl"] = note_link_cache[nid1]
        if nid2 and note_link_cache.get(nid2):
            row["recentNoteUrl2"] = note_link_cache[nid2]
        row["recentNoteUrls"] = [u for u in [row.get("recentNoteUrl"), row.get("recentNoteUrl2")] if u]

    return rows_list, page_logs


def write_outputs(rows: List[dict], keyword: str, out_dir: Path) -> Tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    safe_kw = "".join(ch if ch.isalnum() else "_" for ch in keyword).strip("_") or "kw"

    json_path = out_dir / f"kols_{safe_kw}_{ts}.json"
    csv_path = out_dir / f"kols_{safe_kw}_{ts}.csv"

    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    fields = [
        "name",
        "redId",
        "userId",
        "location",
        "businessNoteCount",
        "fansCount",
        "fansNum",
        "readMidNor30",
        "interMidNor30",
        "picturePrice",
        "videoPrice",
        "lowerPrice",
        "recentNoteId",
        "recentNoteId2",
        "recentNoteUrl",
        "recentNoteUrl2",
        "recentNoteUrls",
        "trackId",
        "pgyHomeUrl",
        "contentTags",
        "featureTags",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})

    return json_path, csv_path


def main():
    ap = argparse.ArgumentParser(description="Crawl all KOLs for keyword from XHS Pugongying and export JSON/CSV")
    ap.add_argument("--keyword", required=True)
    ap.add_argument("--page-size", type=int, default=20)
    ap.add_argument("--max-pages", type=int, default=200)
    ap.add_argument("--out-dir", default=str(Path(__file__).resolve().parents[1] / "output"))
    ap.add_argument("--env", default=str(Path(__file__).resolve().parents[1] / ".env"), help="Path to local .env file")
    ap.add_argument("--global-env", default="/Users/songxuexian/.openclaw/workspace-main/scripts/xhs-pgy-global.env", help="Shared global auth .env")
    args = ap.parse_args()

    # shared first, local override second
    load_env_file(Path(args.global_env))
    load_env_file(Path(args.env), override=True)

    rows, logs = crawl(keyword=args.keyword, page_size=args.page_size, max_pages=args.max_pages)
    json_path, csv_path = write_outputs(rows, keyword=args.keyword, out_dir=Path(args.out_dir))

    print(f"keyword={args.keyword}")
    for l in logs:
        print(f"page={l['page']} count={l['count']} new={l['new']} total={l['total']}")
    print(f"done total_unique={len(rows)}")
    print(f"json={json_path}")
    print(f"csv={csv_path}")


if __name__ == "__main__":
    main()
