#!/usr/bin/env python3
"""备份 KOL 总表到本地（JSON + CSV）。"""

import csv
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

APP_TOKEN = os.getenv("XHS_KOL_APP_TOKEN", "VyT3b5aKRa9WgpsUlQdcKCgQnbd")
TABLE_ID = os.getenv("XHS_KOL_TABLE_ID", "tbl1Y0FeR38G5Z8i")


def req(method, url, data=None, headers=None, timeout=60):
    b = None
    h = dict(headers or {})
    if data is not None:
        b = json.dumps(data, ensure_ascii=False).encode("utf-8")
        h["Content-Type"] = "application/json; charset=utf-8"
    r = urllib.request.Request(url, data=b, headers=h, method=method)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _load_global_env():
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


def main():
    _load_global_env()
    app_id = os.getenv("FEISHU_APP_ID", "").strip()
    app_secret = os.getenv("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        raise RuntimeError("missing FEISHU_APP_ID/FEISHU_APP_SECRET in ~/.claude/skills/xhs-global.env")

    auth = req('POST', 'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal', {
        'app_id': app_id,
        'app_secret': app_secret,
    })
    token = auth['tenant_access_token']
    H = {'Authorization': f'Bearer {token}'}

    rows = []
    page_token = None
    while True:
        url = f'https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records?page_size=500'
        if page_token:
            url += '&page_token=' + urllib.parse.quote(page_token)
        o = req('GET', url, headers=H)
        d = o.get('data') or {}
        rows.extend(d.get('items') or [])
        if not d.get('has_more'):
            break
        page_token = d.get('page_token')

    default_out = Path(__file__).resolve().parents[1] / "output" / "backups"
    out_dir = Path(os.getenv("XHS_BACKUP_DIR", str(default_out))).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime('%Y%m%d_%H%M%S')

    json_path = out_dir / f'kols_table_backup_{ts}.json'
    csv_path = out_dir / f'kols_table_backup_{ts}.csv'

    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')

    # 简单扁平化导出 CSV（常用字段）
    fields = [
        'KOL', '关键词（多选）', '进度', '蒲公英主页', '近期笔记', '近期笔记2',
        '粉丝数', '阅读中位数（日常）', '互动中位数（日常）', '全部报价',
        '微信号', '小红书号', '地区', '内容方向', '人设标签'
    ]
    with csv_path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            fds = r.get('fields') or {}

            def norm(v):
                if isinstance(v, dict):
                    return v.get('link') or v.get('text') or ''
                if isinstance(v, list):
                    return ' | '.join(str(x) for x in v)
                return v if v is not None else ''

            w.writerow({k: norm(fds.get(k)) for k in fields})

    print(json.dumps({
        'total_records': len(rows),
        'json': str(json_path),
        'csv': str(csv_path),
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
