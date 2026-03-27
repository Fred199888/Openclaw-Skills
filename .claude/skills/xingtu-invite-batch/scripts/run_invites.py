#!/usr/bin/env python3
"""
巨量星图 KOL 批量邀约脚本

流程：
1. 从飞书表读取 KOL（进度=无操作，星图ID非空，粉丝数≥阈值）
2. 逐条：apply_contact_info → 获取 chat_id → send_message 发邀约
3. 写回飞书表（进度→已私信，修改时间→now）
"""

import argparse
import json
import os
import random
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

APP_TOKEN = "H6c2bgUWya8XdEsfBgzclDNLn1b"
TABLE_ID = "tblG6pvpqkPmCkrP"

APPLY_URL = "https://www.xingtu.cn/gw/api/ggeneric/apply_contact_info"
SEND_URL = "https://www.xingtu.cn/gw/api/generic/send_message"


def load_env_file(env_path: Path, *, override: bool = False) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        k, v = k.strip(), v.strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        if k and (override or k not in os.environ):
            os.environ[k] = v


def env_required(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v:
        raise RuntimeError(f"missing env: {name}")
    return v


def req(method: str, url: str, *, data: Optional[dict] = None, headers: Optional[dict] = None, timeout: int = 30) -> dict:
    payload = None
    h = dict(headers or {})
    if data is not None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        h["Content-Type"] = "application/json; charset=utf-8"
    r = urllib.request.Request(url, data=payload, headers=h, method=method)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def req_raw(method: str, url: str, *, data: Optional[dict] = None, headers: Optional[dict] = None, timeout: int = 30) -> Tuple[int, dict]:
    payload = None
    h = dict(headers or {})
    if data is not None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        h["Content-Type"] = "application/json; charset=utf-8"
    r = urllib.request.Request(url, data=payload, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
        except Exception:
            body = {"error": str(e)}
        return e.code, body


def _xingtu_headers(cookie: str, csrf_token: str) -> dict:
    return {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "agw-js-conv": "str",
        "content-type": "application/json",
        "origin": "https://www.xingtu.cn",
        "referer": "https://www.xingtu.cn/ad/creator/chat",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
        ),
        "cookie": cookie,
        "x-secsdk-csrf-token": csrf_token,
        "x-login-source": "1",
    }


def get_chat_id(star_id: str, headers: dict) -> Optional[str]:
    url = f"{APPLY_URL}?dest_id={star_id}&contact_type=1"
    h = dict(headers)
    h.pop("content-type", None)
    code, res = req_raw("GET", url, headers=h)
    if code == 200 and res.get("base_resp", {}).get("status_code") == 0:
        return res.get("chat_id")
    return None


def send_invite(chat_id: str, message_info: dict, headers: dict) -> Tuple[bool, dict]:
    body = {
        "chat_id": chat_id,
        "message": [{
            "type": 8,
            "content": "",
            "message_info": json.dumps(message_info, ensure_ascii=False),
        }],
        "platform": 1,
    }
    code, res = req_raw("POST", SEND_URL, data=body, headers=headers)
    ok = code == 200 and res.get("base_resp", {}).get("status_code") == 0
    return ok, res


def build_message_info() -> dict:
    tomorrow = int(time.time()) // 86400 * 86400 + 86400
    days = int(os.getenv("XINGTU_EXPIRATION_DAYS", "7"))
    return {
        "first_class_category": int(os.getenv("XINGTU_FIRST_CLASS_CATEGORY", "1928")),
        "second_class_category": int(os.getenv("XINGTU_SECOND_CLASS_CATEGORY", "192801")),
        "product_name": os.getenv("XINGTU_PRODUCT_NAME", "Second Me"),
        "promotion_target": int(os.getenv("XINGTU_PROMOTION_TARGET", "1")),
        "task_category": int(os.getenv("XINGTU_TASK_CATEGORY", "1")),
        "budget": int(os.getenv("XINGTU_BUDGET", "1000")),
        "product_information": os.getenv("XINGTU_PRODUCT_INFORMATION", "Second Me"),
        "expiration_time": tomorrow,
        "expiration_time_end": tomorrow + days * 86400,
        "platform_source": 1,
    }


def list_records(auth_header: dict) -> List[dict]:
    out: List[dict] = []
    page_token = None
    while True:
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records?page_size=500"
        if page_token:
            url += "&page_token=" + urllib.parse.quote(page_token)
        o = req("GET", url, headers=auth_header)
        d = o.get("data") or {}
        out.extend(d.get("items") or [])
        if not d.get("has_more"):
            break
        page_token = d.get("page_token")
    return out


def main():
    ap = argparse.ArgumentParser(description="巨量星图 KOL 批量邀约")
    ap.add_argument("--total", type=int, default=int(os.getenv("XINGTU_INVITE_TOTAL", "20")))
    ap.add_argument("--min-followers", type=int, default=int(os.getenv("XINGTU_MIN_FOLLOWERS", "10000")))
    ap.add_argument("--delay-min", type=float, default=float(os.getenv("XINGTU_INVITE_DELAY_MIN", "0.5")))
    ap.add_argument("--delay-max", type=float, default=float(os.getenv("XINGTU_INVITE_DELAY_MAX", "2.0")))
    ap.add_argument("--global-env", default=str(Path.home() / ".claude/skills/xhs-global.env"))
    ap.add_argument("--local-env", default=str(Path(__file__).resolve().parents[1] / ".env"))
    args = ap.parse_args()

    load_env_file(Path(args.global_env))
    load_env_file(Path(args.local_env), override=True)

    cookie = env_required("XINGTU_COOKIE")
    csrf_token = env_required("XINGTU_CSRF_TOKEN")
    xt_headers = _xingtu_headers(cookie, csrf_token)

    # Feishu auth
    app_id = env_required("FEISHU_APP_ID")
    app_secret = env_required("FEISHU_APP_SECRET")
    tk = req("POST", "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
             data={"app_id": app_id, "app_secret": app_secret})["tenant_access_token"]
    Hf = {"Authorization": f"Bearer {tk}"}

    # Read & filter KOLs
    records = list_records(Hf)
    candidates = []
    for r in records:
        f = r.get("fields") or {}
        progress = f.get("进度", "")
        star_id = (f.get("星图ID") or "").strip()
        followers = f.get("粉丝数")
        if progress != "无操作" or not star_id:
            continue
        try:
            fans = float(followers) if followers is not None else 0
        except (ValueError, TypeError):
            fans = 0
        if fans < args.min_followers:
            continue
        candidates.append({
            "record_id": r["record_id"],
            "star_id": star_id,
            "name": (f.get("达人信息") or "").strip(),
            "fans": fans,
        })

    candidates.sort(key=lambda x: x["fans"], reverse=True)
    selected = candidates[: args.total]
    print(f"total_candidates={len(candidates)} selected={len(selected)}")

    if not selected:
        print(json.dumps({"selected": 0, "sent": 0, "success": 0, "failed": 0}))
        return

    message_info = build_message_info()
    results: List[dict] = []

    for i, kol in enumerate(selected):
        time.sleep(random.uniform(args.delay_min, args.delay_max))
        print(f"[{i+1}/{len(selected)}] {kol['name']} (star_id={kol['star_id']}, fans={int(kol['fans'])})")

        # Step 1: get chat_id
        chat_id = get_chat_id(kol["star_id"], xt_headers)
        if not chat_id:
            results.append({**kol, "ok": False, "error": "failed to get chat_id"})
            print(f"  FAIL: no chat_id")
            continue

        # Step 2: send invite
        time.sleep(random.uniform(0.3, 0.8))
        ok, res = send_invite(chat_id, message_info, xt_headers)
        results.append({**kol, "ok": ok, "chat_id": chat_id, "response": res})
        print(f"  {'OK' if ok else 'FAIL'}: {res.get('base_resp', {}).get('status_message', '')}")

    # Write back to Feishu
    succ = [x for x in results if x["ok"]]
    if succ:
        now_ms = int(time.time() * 1000)
        payload = [
            {
                "record_id": x["record_id"],
                "fields": {
                    "进度": "已私信",
                    "修改时间": now_ms,
                },
            }
            for x in succ
        ]
        update_url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records/batch_update"
        for j in range(0, len(payload), 30):
            req("POST", update_url, headers=Hf, data={"records": payload[j: j + 30]})

    report = {
        "selected": len(selected),
        "sent": len(results),
        "success": len(succ),
        "failed": len(results) - len(succ),
        "failed_kols": [
            {"name": x["name"], "star_id": x["star_id"], "error": x.get("error", str(x.get("response", "")))}
            for x in results if not x["ok"]
        ][:20],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
