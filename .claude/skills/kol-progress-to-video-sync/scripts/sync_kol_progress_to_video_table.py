#!/usr/bin/env python3
"""
每日同步：Openclaw BD + Information营销活动 bd表 -> 沉淀（kol视频渠道建设表（总））

规则：
- 同步前先备份目标表（JSON + CSV）
- 来源：
  - Openclaw BD（tblXqkvywXxMMo4U）
  - Information营销活动 bd表（tblyxfUsK16nRE2Y）
- 仅同步来源表中：进度 不为空 且 进度 != "已私信"
- 去重键：名字 + 渠道 + 联系方式
- 仅写入目标表中存在且可写的字段（批量写入，失败自动单条回退）
- 自动写入来源字段：来源表（若不存在会自动创建文本列）
"""

from __future__ import annotations

import csv
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

APP = os.getenv("VIDEO_APP_TOKEN", "S8Zeb8p5VaoXl6slfsscGdXEnou")
TARGET_TBL = os.getenv("VIDEO_TABLE_ID", "tblwB8En3N1gMPTe")  # 沉淀
SOURCE_TABLES = [
    ("Openclaw BD", os.getenv("SOURCE_TABLE_OPENCLAW_BD", "tblXqkvywXxMMo4U")),
    ("Information营销活动 bd表", os.getenv("SOURCE_TABLE_INFO_BD", "tblyxfUsK16nRE2Y")),
]

# Feishu Bitable 字段类型（仅保留常用可写类型）
WRITABLE_TYPES = {1, 2, 3, 5, 7, 13, 15}  # 文本/数字/单选/日期/复选框/电话/超链接


def req(method: str, url: str, data: Optional[dict] = None, headers: Optional[dict] = None, timeout: int = 90) -> dict:
    b = None
    h = dict(headers or {})
    if data is not None:
        b = json.dumps(data, ensure_ascii=False).encode("utf-8")
        h["Content-Type"] = "application/json; charset=utf-8"
    r = urllib.request.Request(url, data=b, headers=h, method=method)
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
        if k and k not in os.environ:
            os.environ[k] = v


def get_auth() -> dict:
    _load_global_env()
    app_id = os.getenv("FEISHU_APP_ID", "").strip()
    app_secret = os.getenv("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        raise RuntimeError("missing FEISHU_APP_ID/FEISHU_APP_SECRET in ~/.claude/skills/xhs-global.env")
    o = req(
        "POST",
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        {"app_id": app_id, "app_secret": app_secret},
    )
    if o.get("code") != 0:
        raise RuntimeError(f"auth failed: {o}")
    return {"Authorization": f"Bearer {o['tenant_access_token']}"}


def list_all_records(table_id: str, H: dict) -> List[dict]:
    out: List[dict] = []
    page_token = None
    while True:
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP}/tables/{table_id}/records?page_size=500"
        if page_token:
            url += "&page_token=" + urllib.parse.quote(page_token)
        o = req("GET", url, headers=H)
        if o.get("code") != 0:
            raise RuntimeError(f"list records failed {table_id}: {o}")
        d = o.get("data") or {}
        out.extend(d.get("items") or [])
        if not d.get("has_more"):
            break
        page_token = d.get("page_token")
    return out


def list_fields(table_id: str, H: dict) -> List[dict]:
    o = req(
        "GET",
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP}/tables/{table_id}/fields?page_size=500",
        headers=H,
    )
    if o.get("code") != 0:
        raise RuntimeError(f"list fields failed {table_id}: {o}")
    return (o.get("data") or {}).get("items") or []


def ensure_source_field(H: dict) -> bool:
    fields = list_fields(TARGET_TBL, H)
    exists = any((f.get("field_name") or "") == "来源表" for f in fields)
    if exists:
        return False
    o = req(
        "POST",
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP}/tables/{TARGET_TBL}/fields",
        data={"field_name": "来源表", "type": 1},
        headers=H,
    )
    if o.get("code") != 0:
        raise RuntimeError(f"create 来源表 failed: {o}")
    return True


def as_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    return str(v).strip()


def cell_text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        return as_str(v.get("text") or v.get("link"))
    if isinstance(v, list):
        if not v:
            return ""
        x = v[0]
        if isinstance(x, dict):
            ta = x.get("text_arr") or []
            return as_str(x.get("text") or (ta[0] if ta else ""))
        return as_str(x)
    return as_str(v)


def _norm_name(v: Any) -> str:
    s = cell_text(v).lower()
    # 仅保留中英文和数字，去掉空格/符号，提升模糊匹配稳定性
    return "".join(ch for ch in s if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


def norm_key(name: Any, channel: Any, contact: Any) -> Tuple[str, str, str]:
    return (_norm_name(name), cell_text(channel).lower(), cell_text(contact).lower())


def fuzzy_name_match(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    # 简单模糊：包含关系且较短名长度>=2，避免过度误匹配
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 2 and short in long_


def norm_by_type(v: Any, ft: int) -> Any:
    if ft == 1:  # 文本
        return cell_text(v)
    if ft == 2:  # 数字
        s = cell_text(v)
        if not s:
            return ""
        try:
            return float(s)
        except Exception:
            return ""
    if ft == 3:  # 单选
        return cell_text(v)
    if ft == 7:  # 复选框
        s = cell_text(v).lower()
        return s in {"true", "1", "yes", "y", "是"}
    if ft == 13:  # 电话
        return cell_text(v)
    if ft == 15:  # URL
        if isinstance(v, dict):
            link = cell_text(v.get("link") or v.get("text"))
            if link.startswith("http://") or link.startswith("https://"):
                return {"link": link, "text": cell_text(v.get("text")) or link}
            return ""
        s = cell_text(v)
        if s.startswith("http://") or s.startswith("https://"):
            return {"link": s, "text": s}
        return ""
    if ft == 5:  # 日期时间
        return cell_text(v)
    return ""


def backup_target(rows: List[dict]) -> Tuple[str, str]:
    default_out = Path(__file__).resolve().parents[1] / "output" / "backups"
    out_dir = Path(os.getenv("KOL_VIDEO_BACKUP_DIR", str(default_out))).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    jp = out_dir / f"kol_video_backup_{ts}.json"
    cp = out_dir / f"kol_video_backup_{ts}.csv"

    jp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    fields = ["名字", "联系方式", "渠道", "进度", "体量", "代表作链接", "简介", "来源表"]
    with cp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            fd = r.get("fields") or {}
            w.writerow(
                {
                    "名字": cell_text(fd.get("名字")),
                    "联系方式": cell_text(fd.get("联系方式")),
                    "渠道": cell_text(fd.get("渠道")),
                    "进度": cell_text(fd.get("进度")),
                    "体量": cell_text(fd.get("体量")),
                    "代表作链接": cell_text(fd.get("代表作链接")),
                    "简介": cell_text(fd.get("简介")),
                    "来源表": cell_text(fd.get("来源表")),
                }
            )
    return str(jp), str(cp)


def batch_update_with_fallback(H: dict, records: List[dict], batch_size: int = 20) -> Tuple[int, int, List[dict]]:
    ok = fail = 0
    errors: List[dict] = []
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP}/tables/{TARGET_TBL}/records/batch_update"

    for i in range(0, len(records), batch_size):
        chunk = records[i : i + batch_size]
        o = req("POST", url, data={"records": chunk}, headers=H)
        if o.get("code") == 0:
            ok += len(chunk)
            continue

        for r in chunk:
            o2 = req("POST", url, data={"records": [r]}, headers=H)
            if o2.get("code") == 0:
                ok += 1
            else:
                fail += 1
                errors.append(
                    {
                        "name": cell_text((r.get("fields") or {}).get("名字")),
                        "code": o2.get("code"),
                        "msg": o2.get("msg"),
                    }
                )
            time.sleep(0.03)
        time.sleep(0.05)

    return ok, fail, errors


def batch_create_with_fallback(H: dict, records: List[dict], batch_size: int = 20) -> Tuple[int, int, List[dict]]:
    ok = fail = 0
    errors: List[dict] = []
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP}/tables/{TARGET_TBL}/records/batch_create"

    for i in range(0, len(records), batch_size):
        chunk = records[i : i + batch_size]
        o = req("POST", url, data={"records": chunk}, headers=H)
        if o.get("code") == 0:
            ok += len(chunk)
            continue

        # 回退单条写，最大化成功率
        for r in chunk:
            o2 = req("POST", url, data={"records": [r]}, headers=H)
            if o2.get("code") == 0:
                ok += 1
            else:
                fail += 1
                errors.append(
                    {
                        "name": cell_text((r.get("fields") or {}).get("名字")),
                        "code": o2.get("code"),
                        "msg": o2.get("msg"),
                    }
                )
            time.sleep(0.03)
        time.sleep(0.05)

    return ok, fail, errors


def main() -> None:
    H = get_auth()

    created_source_field = ensure_source_field(H)

    target_fields = list_fields(TARGET_TBL, H)
    target_field_type: Dict[str, int] = {
        (f.get("field_name") or ""): int(f.get("type") or 0) for f in target_fields
    }
    writable_fields = {k for k, t in target_field_type.items() if t in WRITABLE_TYPES}

    target_rows = list_all_records(TARGET_TBL, H)
    backup_json, backup_csv = backup_target(target_rows)

    existing_keys = set()
    target_by_contact: Dict[Tuple[str, str], dict] = {}
    target_name_channel: List[Tuple[str, str, dict]] = []
    for r in target_rows:
        f = r.get("fields") or {}
        nm = _norm_name(f.get("名字"))
        ch = cell_text(f.get("渠道")).lower()
        ct = cell_text(f.get("联系方式")).lower()
        existing_keys.add((nm, ch, ct))
        if ct:
            target_by_contact[(ch, ct)] = r
        if nm:
            target_name_channel.append((nm, ch, r))

    updates: List[dict] = []
    creates: List[dict] = []
    stats: Dict[str, Dict[str, int]] = {
        name: {"scan": 0, "matched": 0, "new": 0, "dup": 0, "updated": 0} for name, _ in SOURCE_TABLES
    }

    for src_name, src_tbl in SOURCE_TABLES:
        rows = list_all_records(src_tbl, H)
        for r in rows:
            stats[src_name]["scan"] += 1
            f = r.get("fields") or {}
            progress = cell_text(f.get("进度"))
            if not progress or progress == "已私信":
                continue

            stats[src_name]["matched"] += 1

            src_name_norm = _norm_name(f.get("名字"))
            src_channel = cell_text(f.get("渠道")).lower()
            src_contact = cell_text(f.get("联系方式")).lower()
            k = (src_name_norm, src_channel, src_contact)

            out: Dict[str, Any] = {}
            for fn, val in f.items():
                if fn not in writable_fields:
                    continue
                if fn not in target_field_type:
                    continue
                nv = norm_by_type(val, target_field_type[fn])
                if nv in ("", None, [], {}):
                    continue
                out[fn] = nv

            # 强制覆盖字段（保证规则一致）
            if "进度" in writable_fields:
                out["进度"] = "已加微信" if progress == "已加v" else progress
            if "来源表" in writable_fields:
                out["来源表"] = src_name

            if not cell_text(out.get("名字") or f.get("名字")):
                continue

            # 1) 先按 渠道+联系方式 精确命中
            target = target_by_contact.get((src_channel, src_contact)) if src_contact else None

            # 2) 联系方式命不中时，按 名字+渠道 模糊命中
            if target is None and src_name_norm:
                for tn, tch, tr in target_name_channel:
                    if src_channel == tch and fuzzy_name_match(src_name_norm, tn):
                        target = tr
                        break

            if target is not None:
                # 仅提交“需要更新的字段”，不要把目标行完整 fields 原样回写。
                # 原因：读取返回的 Link 字段结构与写入期望结构不同，整行回写会触发 LinkFieldConvFail。
                patch: Dict[str, Any] = {}
                for fn, nv in out.items():
                    if nv not in ("", None, [], {}):
                        patch[fn] = nv

                if patch:
                    updates.append({"record_id": target["record_id"], "fields": patch})
                    stats[src_name]["updated"] += 1
                stats[src_name]["dup"] += 1
                continue

            if k in existing_keys:
                stats[src_name]["dup"] += 1
                continue

            creates.append({"fields": out})
            existing_keys.add(k)
            # 创建后也加入索引，避免同轮重复
            fake = {"record_id": f"pending_{len(creates)}", "fields": out}
            if src_contact:
                target_by_contact[(src_channel, src_contact)] = fake
            if src_name_norm:
                target_name_channel.append((src_name_norm, src_channel, fake))
            stats[src_name]["new"] += 1

    updated_ok, update_failed, update_errors = batch_update_with_fallback(H, updates, batch_size=20)
    created_ok, create_failed, create_errors = batch_create_with_fallback(H, creates, batch_size=20)
    failed = update_failed + create_failed
    error_samples = (update_errors + create_errors)[:20]

    report = {
        "created_source_field": created_source_field,
        "backup_json": backup_json,
        "backup_csv": backup_csv,
        "target_before": len(target_rows),
        "update_planned": len(updates),
        "create_planned": len(creates),
        "updated_ok": updated_ok,
        "created_ok": created_ok,
        "failed": failed,
        "stats": stats,
        "error_samples": error_samples,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
