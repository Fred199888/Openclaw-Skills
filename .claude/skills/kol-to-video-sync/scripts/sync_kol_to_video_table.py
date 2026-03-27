#!/usr/bin/env python3
"""
每日同步：KOL -> kol视频渠道建设表（总）

规则：
- 同步前先备份目标表（kol视频渠道建设表（总））
- 仅同步 KOL 表中 进度 不属于 {"无操作", "已私信"} 的记录
- 字段映射：
  - 名字 <- KOL
  - 体量 <- 粉丝数
  - 代表作链接 <- 近期笔记
  - 简介 <- 内容方向（多选拼接）
  - 渠道 <- 小红书
  - 进度 <- 进度
  - 联系方式 <- 小红书号（用于去重键）
- 其他字段不动
- 去重：优先按 联系方式（小红书号）匹配；其次按 名字 精确匹配
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

KOL_APP = os.getenv("XHS_KOL_APP_TOKEN", "VyT3b5aKRa9WgpsUlQdcKCgQnbd")
KOL_TBL = os.getenv("XHS_KOL_TABLE_ID", "tbl1Y0FeR38G5Z8i")
VIDEO_APP = os.getenv("VIDEO_APP_TOKEN", "S8Zeb8p5VaoXl6slfsscGdXEnou")
VIDEO_TBL = os.getenv("VIDEO_TABLE_ID", "tblwB8En3N1gMPTe")


def req(method: str, url: str, data: Optional[dict] = None, headers: Optional[dict] = None, timeout: int = 60) -> dict:
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


def list_all(app: str, tbl: str, H: dict) -> List[dict]:
    out: List[dict] = []
    page_token = None
    while True:
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app}/tables/{tbl}/records?page_size=500"
        if page_token:
            url += "&page_token=" + urllib.parse.quote(page_token)
        o = req("GET", url, headers=H)
        if o.get("code") != 0:
            raise RuntimeError(f"list failed {app}/{tbl}: {o}")
        d = o.get("data") or {}
        out.extend(d.get("items") or [])
        if not d.get("has_more"):
            break
        page_token = d.get("page_token")
    return out


def as_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    return str(v).strip()


def as_list(v: Any) -> List[str]:
    if not isinstance(v, list):
        return []
    out = []
    for x in v:
        s = as_str(x)
        if s:
            out.append(s)
    return out


def norm_url(v: Any) -> str:
    if isinstance(v, dict):
        return as_str(v.get("link") or v.get("text"))
    return as_str(v)


def backup_video_table(rows: List[dict]) -> Tuple[str, str]:
    default_out = Path(__file__).resolve().parents[1] / "output" / "backups"
    out_dir = Path(os.getenv("KOL_VIDEO_BACKUP_DIR", str(default_out))).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    jp = out_dir / f"kol_video_backup_{ts}.json"
    cp = out_dir / f"kol_video_backup_{ts}.csv"

    jp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    fields = ["名字", "联系方式", "渠道", "进度", "体量", "代表作链接", "简介"]
    with cp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            fd = r.get("fields") or {}
            w.writerow(
                {
                    "名字": as_str(fd.get("名字")),
                    "联系方式": as_str(fd.get("联系方式")),
                    "渠道": as_str(fd.get("渠道")),
                    "进度": as_str(fd.get("进度")),
                    "体量": as_str(fd.get("体量")),
                    "代表作链接": norm_url(fd.get("代表作链接")),
                    "简介": as_str(fd.get("简介")),
                }
            )
    return str(jp), str(cp)


def batch_update(app: str, tbl: str, H: dict, records: List[dict], batch_size: int = 30) -> Tuple[int, int]:
    ok = fail = 0
    for i in range(0, len(records), batch_size):
        chunk = records[i : i + batch_size]
        o = req(
            "POST",
            f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app}/tables/{tbl}/records/batch_update",
            data={"records": chunk},
            headers=H,
        )
        if o.get("code") == 0:
            ok += len(chunk)
        else:
            fail += len(chunk)
        time.sleep(0.05)
    return ok, fail


def batch_create(app: str, tbl: str, H: dict, records: List[dict], batch_size: int = 30) -> Tuple[int, int]:
    ok = fail = 0
    for i in range(0, len(records), batch_size):
        chunk = records[i : i + batch_size]
        o = req(
            "POST",
            f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app}/tables/{tbl}/records/batch_create",
            data={"records": chunk},
            headers=H,
        )
        if o.get("code") == 0:
            ok += len(chunk)
        else:
            fail += len(chunk)
        time.sleep(0.05)
    return ok, fail


def main() -> None:
    H = get_auth()

    video_rows = list_all(VIDEO_APP, VIDEO_TBL, H)
    backup_json, backup_csv = backup_video_table(video_rows)

    # index destination
    by_contact: Dict[str, dict] = {}
    by_name: Dict[str, dict] = {}
    for r in video_rows:
        f = r.get("fields") or {}
        contact = as_str(f.get("联系方式"))
        name = as_str(f.get("名字"))
        if contact and contact not in by_contact:
            by_contact[contact] = r
        if name and name not in by_name:
            by_name[name] = r

    kol_rows = list_all(KOL_APP, KOL_TBL, H)

    updates: List[dict] = []
    creates: List[dict] = []

    selected = 0
    skip_progress = {"无操作", "已私信"}
    for r in kol_rows:
        f = r.get("fields") or {}
        progress = as_str(f.get("进度"))
        if not progress or progress in skip_progress:
            continue

        selected += 1
        name = as_str(f.get("KOL"))
        redid = as_str(f.get("小红书号"))
        fans = as_str(f.get("粉丝数"))
        note = norm_url(f.get("近期笔记"))
        directions = as_list(f.get("内容方向"))

        mapped = {
            "名字": name,
            "体量": fans,
            "代表作链接": {"link": note, "text": "近期笔记"} if note else "",
            "简介": " / ".join(directions),
            "渠道": "小红书",
            "进度": progress,
            "联系方式": redid,
        }

        target = (by_contact.get(redid) if redid else None) or (by_name.get(name) if name else None)
        if target:
            updates.append({"record_id": target["record_id"], "fields": mapped})
        else:
            creates.append({"fields": mapped})

    up_ok, up_fail = batch_update(VIDEO_APP, VIDEO_TBL, H, updates, 30)
    cr_ok, cr_fail = batch_create(VIDEO_APP, VIDEO_TBL, H, creates, 30)

    report = {
        "backup_json": backup_json,
        "backup_csv": backup_csv,
        "kol_total": len(kol_rows),
        "kol_selected_progress_syncable": selected,
        "update_planned": len(updates),
        "create_planned": len(creates),
        "updated_ok": up_ok,
        "created_ok": cr_ok,
        "failed": up_fail + cr_fail,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
