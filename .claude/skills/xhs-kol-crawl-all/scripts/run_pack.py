#!/usr/bin/env python3
"""
Run multi-keyword XHS KOL crawl + sync to Feishu master table.
"""

import argparse
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

DEFAULT_KEYWORDS = [
    "openclaw",
    "Claude code",
    "codex",
    "chatgpt",
    "OpenAI",
    "Anthropic",
    "DeepSeek",
    "Agent",
]

SKILL_DIR = Path(__file__).resolve().parents[1]
CRAWL_SCRIPT = SKILL_DIR / "scripts" / "crawl_kols.py"
SYNC_SCRIPT = SKILL_DIR / "scripts" / "sync_kol_master.py"
BACKUP_SCRIPT = SKILL_DIR / "scripts" / "backup_kol_table.py"
OUT_DIR = SKILL_DIR / "output"

APP_TOKEN = os.getenv("XHS_KOL_APP_TOKEN", "VyT3b5aKRa9WgpsUlQdcKCgQnbd")
TABLE_ID = os.getenv("XHS_KOL_TABLE_ID", "tbl1Y0FeR38G5Z8i")


def run(cmd, cwd=None, env=None):
    p = subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{p.stderr}")
    return p.stdout


def latest_json(keyword: str) -> Path:
    safe = "".join(ch if ch.isalnum() else "_" for ch in keyword).strip("_") or "kw"
    files = sorted(OUT_DIR.glob(f"kols_{safe}_*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise FileNotFoundError(f"no json output found for keyword={keyword}")
    return files[-1]


def run_one_keyword(kw: str, args) -> dict:
    crawl_env = dict(os.environ)
    crawl_env["XHS_NOTE_DETAIL_CONCURRENCY"] = str(args.note_concurrency)

    run(
        [
            "python3",
            str(CRAWL_SCRIPT),
            "--keyword",
            kw,
            "--page-size",
            str(args.page_size),
            "--max-pages",
            str(args.max_pages),
        ],
        cwd=str(SKILL_DIR),
        env=crawl_env,
    )

    src = latest_json(kw)
    out = run(
        [
            "python3",
            str(SYNC_SCRIPT),
            "--keyword",
            kw,
            "--source",
            str(src),
            "--app-token",
            args.app_token,
            "--table-id",
            args.table_id,
            "--batch-size",
            str(args.batch_size),
            "--write-concurrency",
            str(args.write_concurrency),
        ],
        cwd=str(SKILL_DIR),
    )

    report = None
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    if lines:
        try:
            report = json.loads("\n".join(lines[-30:]))
        except Exception:
            report = None

    return {"keyword": kw, "source": str(src), "report": report, "ok": True}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-token", default=os.getenv("XHS_KOL_APP_TOKEN", APP_TOKEN))
    ap.add_argument("--table-id", default=os.getenv("XHS_KOL_TABLE_ID", TABLE_ID))
    ap.add_argument("--keywords", nargs="*", default=DEFAULT_KEYWORDS)
    ap.add_argument("--page-size", type=int, default=20)
    ap.add_argument("--max-pages", type=int, default=60)
    ap.add_argument("--note-concurrency", type=int, default=20)
    ap.add_argument("--write-concurrency", type=int, default=20)
    ap.add_argument("--batch-size", type=int, default=30)
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args()

    keywords = list(dict.fromkeys(args.keywords))
    workers = max(1, min(args.workers, len(keywords)))

    summary = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(run_one_keyword, kw, args): kw for kw in keywords}
        for fut in as_completed(futs):
            kw = futs[fut]
            try:
                summary.append(fut.result())
            except Exception as e:
                summary.append({"keyword": kw, "ok": False, "error": str(e)})

    order = {k: i for i, k in enumerate(keywords)}
    summary.sort(key=lambda x: order.get(x.get("keyword", ""), 999))

    print("===== ALL DONE =====")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    print("\n===== BACKUP KOL TABLE =====", flush=True)
    backup_out = run(["python3", str(BACKUP_SCRIPT)], cwd=str(SKILL_DIR))
    print(backup_out)


if __name__ == "__main__":
    main()
