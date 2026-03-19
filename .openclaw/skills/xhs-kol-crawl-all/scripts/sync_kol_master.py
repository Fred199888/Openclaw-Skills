#!/usr/bin/env python3
"""
KOL 总表同步脚本（Feishu Bitable）

能力：
- 读取抓取 JSON（kols_<keyword>_*.json）
- 按“优先小红书号，其次KOL”匹配已有记录去重
- 关键词写入“关键词（多选）”，并做并集追加
- 进度字段保持已有值；新记录默认“无操作”
- 指标字段（粉丝/阅读中位数/互动中位数/全部报价）按最新抓取更新
- URL 字段使用“中文文本 + 超链接”形式写入
- 批量 API（batch_update / batch_create）写回，减少网络往返

用法示例：
python3 scripts/sync_kol_master.py \
  --keyword openclaw \
  --source /path/to/kols_openclaw_xxx.json \
  --app-token VyT3b5aKRa9WgpsUlQdcKCgQnbd \
  --table-id tbl1Y0FeR38G5Z8i
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from collections import defaultdict
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


def load_feishu_auth() -> Tuple[str, str]:
    cfg = json.loads(Path.home().joinpath(".openclaw/openclaw.json").read_text(encoding="utf-8"))
    ch = cfg.get("channels", {}).get("feishu", {})
    app_id = ch.get("appId")
    app_secret = ch.get("appSecret")
    if not app_id or not app_secret:
        raise RuntimeError("missing feishu appId/appSecret in ~/.openclaw/openclaw.json")
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
    fans = row.get("fansNum") if row.get("fansNum") not in (None, "") else row.get("fansCount")
    now_ms = int(time.time() * 1000)
    f = {
        "KOL": strv(row.get("name")),
        "关键词（多选）": [keyword],
        "进度": "无操作",
        "修改时间": now_ms,
        "近期笔记": url_link(row.get("recentNoteUrl") or "", "近期笔记1"),
        "近期笔记2": url_link(row.get("recentNoteUrl2") or "", "近期笔记2"),
        "蒲公英主页": url_link(row.get("pgyHomeUrl") or "", "蒲公英主页"),
        "粉丝数": as_num(fans),
        "阅读中位数（日常）": as_num(row.get("readMidNor30")),
        "互动中位数（日常）": as_num(row.get("interMidNor30")),
        "全部报价": as_num(row.get("lowerPrice")),
        "小红书号": strv(row.get("redId")),
        "KolID": strv(row.get("userId")),
        "地区": strv(row.get("location")),
        "内容方向": listv(row.get("contentTags")),
        "人设标签": listv(row.get("featureTags")),
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
        # 简单重试，避免偶发 429/5xx
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
    ap.add_argument("--batch-size", type=int, default=30, help="Feishu 批量写入大小（默认30）")
    ap.add_argument("--write-concurrency", type=int, default=20, help="Feishu 并行写入批次数（默认20）")
    ap.add_argument("--snapshot-dir", default="scripts/output", help="本地快照目录")
    args = ap.parse_args()

    keyword = args.keyword.strip()
    src_raw = json.loads(Path(args.source).read_text(encoding="utf-8"))

    # 本地先按小红书号去重（保留最后一条，视为最新）
    dedup_map: Dict[str, dict] = {}
    no_redid_rows: List[dict] = []
    for r in src_raw:
        red = strv(r.get("redId"))
        if red:
            dedup_map[red] = r
        else:
            no_redid_rows.append(r)
    src_rows = list(dedup_map.values()) + no_redid_rows

    app_id, app_secret = load_feishu_auth()
    tk = tenant_token(app_id, app_secret)
    H = {"Authorization": f"Bearer {tk}"}

    existing = list_all_records(args.app_token, args.table_id, H)

    # 保存飞书表快照到本地
    snap_dir = Path(args.snapshot_dir)
    snap_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    (snap_dir / f"kol_table_snapshot_{ts}.json").write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")

    by_kolid: Dict[str, dict] = {}
    by_red: Dict[str, dict] = {}
    by_kol: Dict[str, dict] = {}
    for r in existing:
        f = r.get("fields") or {}
        kolid = strv(f.get("KolID"))
        red = strv(f.get("小红书号"))
        kol = strv(f.get("KOL"))
        if kolid and kolid not in by_kolid:
            by_kolid[kolid] = r
        if red and red not in by_red:
            by_red[red] = r
        if kol and kol not in by_kol:
            by_kol[kol] = r

    updates: List[dict] = []
    creates: List[dict] = []
    changed_metrics: List[dict] = []

    for row in src_rows:
        kolid = strv(row.get("userId"))
        red = strv(row.get("redId"))
        kol = strv(row.get("name"))
        if not kolid and not red and not kol:
            continue

        target = by_kolid.get(kolid) or by_red.get(red) or by_kol.get(kol)
        new_fields = build_new_fields(row, keyword)

        if target:
            old = target.get("fields") or {}

            # 关键词并集
            old_kw = listv(old.get("关键词（多选）"))
            merged_kw = merge_unique(old_kw + [keyword])
            if merged_kw:
                new_fields["关键词（多选）"] = merged_kw

            # 进度保留已有
            old_progress = old.get("进度")
            if old_progress not in (None, ""):
                new_fields["进度"] = old_progress

            # 指标变化审计
            metric_diff = {}
            for m in ["全部报价", "阅读中位数（日常）", "互动中位数（日常）"]:
                ov, nv = as_num(old.get(m)), as_num(new_fields.get(m))
                if nv is not None and ov != nv:
                    metric_diff[m] = [ov, nv]
            if metric_diff:
                changed_metrics.append({"KOL": kol, "小红书号": red, "changes": metric_diff})

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
