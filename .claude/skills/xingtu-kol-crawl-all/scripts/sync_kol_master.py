#!/usr/bin/env python3
"""
巨量星图 KOL 总表同步脚本（Feishu Bitable）

去重匹配优先级: 星图ID → 抖音UID → KOL名称
关键词做并集追加，进度保留已有值，指标按最新抓取更新。
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def req(method: str, url: str, *, data: Optional[dict] = None, headers: Optional[dict] = None, timeout: int = 60) -> dict:
    payload = None
    h = dict(headers or {})
    if data is not None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        h["Content-Type"] = "application/json; charset=utf-8"
    r = urllib.request.Request(url, data=payload, headers=h, method=method)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _load_global_env() -> None:
    genv = Path.home() / ".claude/skills/xhs-global.env"
    if not genv.exists():
        return
    for line in genv.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        k, v = k.strip(), v.strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        if k and k not in os.environ:
            os.environ[k] = v


def load_feishu_auth() -> Tuple[str, str]:
    _load_global_env()
    app_id = os.getenv("FEISHU_APP_ID", "").strip()
    app_secret = os.getenv("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        raise RuntimeError("missing feishu auth: set FEISHU_APP_ID/FEISHU_APP_SECRET in ~/.claude/skills/xhs-global.env")
    return app_id, app_secret


def tenant_token(app_id: str, app_secret: str) -> str:
    o = req(
        "POST",
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        data={"app_id": app_id, "app_secret": app_secret},
    )
    if o.get("code") != 0:
        raise RuntimeError(f"tenant token failed: {o}")
    return o["tenant_access_token"]


def list_all_records(app_token: str, table_id: str, auth_header: dict) -> List[dict]:
    out: List[dict] = []
    page_token = None
    while True:
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records?page_size=500"
        if page_token:
            url += "&page_token=" + urllib.parse.quote(page_token)
        o = req("GET", url, headers=auth_header)
        if o.get("code") != 0:
            raise RuntimeError(f"list records failed: {o}")
        d = o.get("data") or {}
        out.extend(d.get("items") or [])
        if not d.get("has_more"):
            break
        page_token = d.get("page_token")
    return out


def as_num(v: Any) -> Optional[float]:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except Exception:
        return None


def strv(v: Any) -> str:
    return v.strip() if isinstance(v, str) else ""


def listv(v: Any) -> List[str]:
    if not isinstance(v, list):
        return []
    out: List[str] = []
    for x in v:
        s = str(x).strip()
        if s and s not in out:
            out.append(s)
    return out


def url_link(url: str, text: str) -> Optional[dict]:
    u = strv(url)
    if not u:
        return None
    return {"link": u, "text": text}


def merge_unique(values: List[str]) -> List[str]:
    out: List[str] = []
    for v in values:
        s = str(v).strip()
        if s and s not in out:
            out.append(s)
    return out


def build_new_fields(row: dict, keyword: str) -> dict:
    f = {
        "达人信息": strv(row.get("name")),
        "关键词（多选）": [keyword],
        "进度": "无操作",
        "星图主页": url_link(row.get("xingtHomeUrl") or "", "星图主页"),
        "近期视频": url_link(row.get("recentVideoUrl") or "", "近期视频1"),
        "近期视频2": url_link(row.get("recentVideoUrl2") or "", "近期视频2"),
        "达人类型": [strv(row.get("authorCategory"))] if strv(row.get("authorCategory")) else [],
        "内容主题": listv(row.get("contentTags")),
        "连接用户数": as_num(row.get("linkedUserCount")),
        "粉丝数": as_num(row.get("follower")),
        "预期CPM": as_num(row.get("expectedCpm")),
        "预期播放量": as_num(row.get("expectedPlayNum")),
        "互动率": as_num(row.get("interactRate30d")),
        "完播率": as_num(row.get("playOverRate30d")),
        "30天涨粉": as_num(row.get("fansIncrement30d")),
        "1-20s报价": as_num(row.get("price1_20")),
        "21-60s报价": as_num(row.get("price20_60")),
        "60s+报价": as_num(row.get("price60")),
        "传播指数": as_num(row.get("spreadIndex")),
        "种草指数": as_num(row.get("shoppingIndex")),
        "转化指数": as_num(row.get("convertIndex")),
        "地区": strv(row.get("location")),
        "星图ID": strv(row.get("starId")),
        "抖音UID": strv(row.get("coreUserId")),
        "vx号": strv(row.get("wechat")),
        "创建时间": int(time.time() * 1000),
        "修改时间": int(time.time() * 1000),
    }
    return {k: v for k, v in f.items() if v not in (None, "", [], {})}


def diff_fields(old_fields: dict, new_fields: dict) -> dict:
    diff = {}
    for k, v in new_fields.items():
        ov = old_fields.get(k)
        if isinstance(v, dict):
            if not isinstance(ov, dict) or ov.get("link") != v.get("link") or ov.get("text") != v.get("text"):
                diff[k] = v
        elif isinstance(v, list):
            if (ov if isinstance(ov, list) else []) != v:
                diff[k] = v
        else:
            if ov != v:
                diff[k] = v
    return diff


def _parallel_batches(url: str, auth_header: dict, payload: List[dict], batch_size: int, write_concurrency: int) -> Tuple[int, int]:
    chunks = [payload[i : i + batch_size] for i in range(0, len(payload), batch_size)]
    if not chunks:
        return 0, 0

    def _send(ch: List[dict]) -> Tuple[int, int]:
        for _ in range(3):
            o = req("POST", url, data={"records": ch}, headers=auth_header)
            if o.get("code") == 0:
                return len(ch), 0
            time.sleep(0.3)
        return 0, len(ch)

    ok, fail = 0, 0
    with ThreadPoolExecutor(max_workers=max(1, write_concurrency)) as ex:
        futs = [ex.submit(_send, ch) for ch in chunks]
        for fut in as_completed(futs):
            a, b = fut.result()
            ok += a
            fail += b
    return ok, fail


def batch_update(app_token: str, table_id: str, auth_header: dict, payload: List[dict], batch_size: int, write_concurrency: int) -> Tuple[int, int]:
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_update"
    return _parallel_batches(url, auth_header, payload, batch_size, write_concurrency)


def batch_create(app_token: str, table_id: str, auth_header: dict, payload: List[dict], batch_size: int, write_concurrency: int) -> Tuple[int, int]:
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create"
    return _parallel_batches(url, auth_header, payload, batch_size, write_concurrency)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keyword", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--app-token", required=True)
    ap.add_argument("--table-id", required=True)
    ap.add_argument("--batch-size", type=int, default=30)
    ap.add_argument("--write-concurrency", type=int, default=20)
    ap.add_argument("--snapshot-dir", default="scripts/output")
    args = ap.parse_args()

    keyword = args.keyword.strip()
    src_raw = json.loads(Path(args.source).read_text(encoding="utf-8"))

    # 本地按星图ID去重（保留最后一条）
    dedup_map: Dict[str, dict] = {}
    no_id_rows: List[dict] = []
    for r in src_raw:
        sid = strv(r.get("starId"))
        if sid:
            dedup_map[sid] = r
        else:
            no_id_rows.append(r)
    src_rows = list(dedup_map.values()) + no_id_rows

    app_id, app_secret = load_feishu_auth()
    tk = tenant_token(app_id, app_secret)
    H = {"Authorization": f"Bearer {tk}"}

    existing = list_all_records(args.app_token, args.table_id, H)

    # 保存快照
    snap_dir = Path(args.snapshot_dir)
    snap_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    (snap_dir / f"kol_table_snapshot_{ts}.json").write_text(
        json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    by_star_id: Dict[str, dict] = {}
    by_uid: Dict[str, dict] = {}
    by_kol: Dict[str, dict] = {}
    for r in existing:
        f = r.get("fields") or {}
        sid = strv(f.get("星图ID"))
        uid = strv(f.get("抖音UID"))
        kol = strv(f.get("达人信息"))
        if sid and sid not in by_star_id:
            by_star_id[sid] = r
        if uid and uid not in by_uid:
            by_uid[uid] = r
        if kol and kol not in by_kol:
            by_kol[kol] = r

    updates: List[dict] = []
    creates: List[dict] = []
    changed_metrics: List[dict] = []

    for row in src_rows:
        sid = strv(row.get("starId"))
        uid = strv(row.get("coreUserId"))
        kol = strv(row.get("name"))
        if not sid and not uid and not kol:
            continue

        target = by_star_id.get(sid) or by_uid.get(uid) or by_kol.get(kol)
        new_fields = build_new_fields(row, keyword)

        if target:
            old = target.get("fields") or {}

            # 关键词并集
            old_kw = listv(old.get("关键词（多选）"))
            merged_kw = merge_unique(old_kw + [keyword])
            if merged_kw:
                new_fields["关键词（多选）"] = merged_kw

            # 进度、vx号保留已有（手动填写字段）
            for keep_field in ["进度", "vx号"]:
                old_val = old.get(keep_field)
                if old_val not in (None, ""):
                    new_fields[keep_field] = old_val

            # 创建时间保留已有，只更新修改时间
            new_fields.pop("创建时间", None)

            # 指标变化审计
            metric_diff = {}
            for m in ["粉丝数", "预期CPM", "预期播放量", "1-20s报价", "21-60s报价", "60s+报价"]:
                ov, nv = as_num(old.get(m)), as_num(new_fields.get(m))
                if nv is not None and ov != nv:
                    metric_diff[m] = [ov, nv]
            if metric_diff:
                changed_metrics.append({"KOL": kol, "星图ID": sid, "changes": metric_diff})

            diff = diff_fields(old, new_fields)
            if diff:
                updates.append({"record_id": target["record_id"], "fields": diff})
        else:
            creates.append({"fields": new_fields})

    up_ok, up_fail = batch_update(args.app_token, args.table_id, H, updates, args.batch_size, args.write_concurrency)
    cr_ok, cr_fail = batch_create(args.app_token, args.table_id, H, creates, args.batch_size, args.write_concurrency)

    report = {
        "source_total_raw": len(src_raw),
        "source_total_after_local_dedupe": len(src_rows),
        "batch_size": args.batch_size,
        "write_concurrency": args.write_concurrency,
        "updated": up_ok,
        "created": cr_ok,
        "failed": up_fail + cr_fail,
        "metric_changes": len(changed_metrics),
        "metric_change_samples": changed_metrics[:20],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
