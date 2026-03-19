#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

TARGET_KWS = {"openclaw", "Claude code", "codex", "chatgpt", "OpenAI", "Anthropic", "DeepSeek"}
APP_TOKEN = os.getenv("XHS_KOL_APP_TOKEN", "VyT3b5aKRa9WgpsUlQdcKCgQnbd")
TABLE_ID = os.getenv("XHS_KOL_TABLE_ID", "tbl1Y0FeR38G5Z8i")


def load_env_file(path: Path, override=False):
    if not path.exists():
        return
    for ln in path.read_text(encoding="utf-8").splitlines():
        s = ln.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        k, v = k.strip(), v.strip()
        if not k:
            continue
        if override or k not in os.environ:
            os.environ[k] = v


def req(method, url, data=None, headers=None, timeout=60):
    payload = None
    h = dict(headers or {})
    if data is not None:
        payload = json.dumps(data, ensure_ascii=False).encode()
        h["Content-Type"] = "application/json; charset=utf-8"
    r = urllib.request.Request(url, data=payload, headers=h, method=method)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def req_raw(method, url, data=None, headers=None, timeout=60):
    payload = None
    h = dict(headers or {})
    if data is not None:
        payload = json.dumps(data, ensure_ascii=False).encode()
        h["Content-Type"] = "application/json;charset=UTF-8"
    r = urllib.request.Request(url, data=payload, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            body = resp.read().decode()
            return resp.status, json.loads(body)
    except urllib.error.HTTPError as e:
        body = e.read().decode() if hasattr(e, "read") else ""
        try:
            obj = json.loads(body)
        except Exception:
            obj = {"raw": body}
        return e.code, obj


def list_records(auth_header):
    items, page_token = [], None
    while True:
        u = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records?page_size=500"
        if page_token:
            u += "&page_token=" + urllib.parse.quote(page_token)
        o = req("GET", u, headers=auth_header)
        d = o.get("data") or {}
        items.extend(d.get("items") or [])
        if not d.get("has_more"):
            break
        page_token = d.get("page_token")
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--global-env", default=os.getenv("XHS_GLOBAL_ENV", str(Path.home()/".openclaw/env/global.env")))
    ap.add_argument("--local-env", default=str(Path(__file__).resolve().parents[1] / ".env"))
    ap.add_argument("--total", type=int, default=20)
    ap.add_argument("--batch-size", type=int, default=20)
    ap.add_argument("--concurrency", type=int, default=20)
    ap.add_argument("--invite-content", default="")
    ap.add_argument("--contact-info", default="19318359809")
    args = ap.parse_args()

    load_env_file(Path(args.global_env))
    load_env_file(Path(args.local_env), override=True)

    invite_content = args.invite_content.strip() or os.getenv("XHS_INVITE_CONTENT", "").strip()
    if not invite_content:
        raise RuntimeError("missing invite content")

    for k in ["XHS_COOKIE", "XHS_X_S", "XHS_X_S_COMMON"]:
        if not os.getenv(k, "").strip():
            raise RuntimeError(f"missing env: {k}")

    cfg = json.loads(Path.home().joinpath(".openclaw/openclaw.json").read_text())
    ch = cfg.get("channels", {}).get("feishu", {})
    tk = req("POST", "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal", data={"app_id": ch["appId"], "app_secret": ch["appSecret"]})["tenant_access_token"]
    Hf = {"Authorization": f"Bearer {tk}"}

    rows = []
    for it in list_records(Hf):
        f = it.get("fields") or {}
        if f.get("进度") != "无操作":
            continue
        kolid = (f.get("KolID") or "").strip() if isinstance(f.get("KolID"), str) else ""
        if not kolid:
            continue
        try:
            fans = float(f.get("粉丝数"))
        except Exception:
            continue
        if fans <= 10000:
            continue
        kws = set(f.get("关键词（多选）") or [])
        if not kws.intersection(TARGET_KWS):
            continue
        try:
            read_mid = float(f.get("阅读中位数（日常）"))
        except Exception:
            read_mid = 0.0
        rows.append({"record_id": it["record_id"], "KOL": f.get("KOL"), "KolID": kolid, "read": read_mid})

    rows.sort(key=lambda x: x["read"], reverse=True)
    selected = rows[: args.total]

    today = dt.date.today()
    end = today + dt.timedelta(days=7)
    base_h = {
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://pgy.xiaohongshu.com",
        "Referer": "https://pgy.xiaohongshu.com/solar/pre-trade/invite-form",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        "X-s": os.getenv("XHS_X_S", "").strip(),
        "X-s-common": os.getenv("XHS_X_S_COMMON", "").strip(),
        "Cookie": os.getenv("XHS_COOKIE", "").strip(),
    }

    all_results = []
    for i in range(0, len(selected), args.batch_size):
        batch = selected[i : i + args.batch_size]

        def send_one(r):
            time.sleep(random.uniform(0.05, 0.35))
            h = dict(base_h)
            h["X-t"] = str(int(time.time() * 1000))
            h["X-b3-traceid"] = os.urandom(8).hex()
            body = {
                "kolId": r["KolID"],
                "cooperateBrandId": os.getenv("XHS_COOPERATE_BRAND_ID", "650d7baf0000000012007130"),
                "cooperateBrandName": os.getenv("XHS_COOPERATE_BRAND_NAME", "Second Me 心识宇宙"),
                "inviteType": 1,
                "productName": "SecondMe",
                "expectedPublishTimeStart": str(today),
                "expectedPublishTimeEnd": str(end),
                "inviteContent": invite_content,
                "contactInfo": args.contact_info,
                "contactType": 2,
                "sellerId": "",
                "kolType": 0,
                "brandUserId": os.getenv("XHS_BRAND_USER_ID", "650d7baf0000000012007130"),
            }
            code, res = req_raw("POST", "https://pgy.xiaohongshu.com/api/solar/invite/initiate_invite", data=body, headers=h, timeout=25)
            ok = code == 200 and res.get("success") is True and (res.get("data") or {}).get("inviteSucceed") is True
            return {"record_id": r["record_id"], "KOL": r["KOL"], "ok": ok, "code": code, "hint": (res.get("data") or {}).get("hint")}

        with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
            futs = [ex.submit(send_one, r) for r in batch]
            for f in as_completed(futs):
                all_results.append(f.result())

        succ = [x for x in all_results if x["ok"] and x["record_id"] in {b["record_id"] for b in batch}]
        if succ:
            now_ms = int(time.time() * 1000)
            payload = [{"record_id": x["record_id"], "fields": {"进度": "已私信", "发送邀约时间": now_ms}} for x in succ]
            u = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records/batch_update"
            for j in range(0, len(payload), 30):
                req("POST", u, headers=Hf, data={"records": payload[j : j + 30]})

    print(json.dumps({
        "selected": len(selected),
        "sent": len(all_results),
        "success": sum(1 for x in all_results if x["ok"]),
        "failed": sum(1 for x in all_results if not x["ok"]),
        "failed_kols": [x for x in all_results if not x["ok"]][:20],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
