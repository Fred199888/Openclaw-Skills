#!/usr/bin/env python3
"""
Query decrypted WeChat messages using sqlcipher.
Requires: /tmp/vx_secret_keys.json (from extract_keys.py), sqlcipher installed.

Usage:
  python3 query_wechat.py recent [N]              # Recent N messages across all chats
  python3 query_wechat.py contacts                 # List all contacts
  python3 query_wechat.py search <keyword>         # Search messages
  python3 query_wechat.py chat <nick_or_wxid> [N]  # Messages from specific contact
  python3 query_wechat.py export <output_dir>      # Export all messages to CSV
"""
import json
import os
import re
import shutil
import subprocess
import sys
import csv
from datetime import datetime

KEYS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "keys.json")
SQLCIPHER = None
WECHAT_BASE = os.path.expanduser(
    "~/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files"
)


def find_sqlcipher():
    global SQLCIPHER
    for path in ["/opt/homebrew/bin/sqlcipher", "/usr/local/bin/sqlcipher"]:
        if os.path.isfile(path):
            SQLCIPHER = path
            return
    which = shutil.which("sqlcipher")
    if which:
        SQLCIPHER = which
        return
    print("ERROR: sqlcipher not found. Install: brew install sqlcipher")
    sys.exit(1)


def load_keys():
    if not os.path.isfile(KEYS_FILE):
        print(f"ERROR: {KEYS_FILE} not found. Run extract_keys.py first.")
        sys.exit(1)
    with open(KEYS_FILE) as f:
        return json.load(f)


def query_db(db_path, key_hex, sql):
    """Run SQL query on encrypted DB, return rows as list of strings."""
    db_copy = f"/tmp/vx_query_{os.path.basename(db_path)}"
    shutil.copy2(db_path, db_copy)
    for ext in ["-wal", "-shm"]:
        src = db_path + ext
        if os.path.isfile(src):
            shutil.copy2(src, db_copy + ext)

    full_sql = f"""PRAGMA key = "x'{key_hex}'";
PRAGMA cipher_compatibility = 4;
.mode csv
.separator |
{sql}"""
    try:
        result = subprocess.run(
            [SQLCIPHER, db_copy],
            input=full_sql, capture_output=True, text=True, timeout=30
        )
        lines = [l for l in result.stdout.strip().split('\n') if l and l != 'ok']
        return lines
    except Exception as e:
        return [f"ERROR: {e}"]
    finally:
        for f in [db_copy, db_copy + "-wal", db_copy + "-shm"]:
            try:
                os.unlink(f)
            except Exception:
                pass


def find_db_key(keys, pattern):
    """Find a DB entry matching pattern."""
    for rel, info in keys.items():
        if pattern in rel:
            return info["path"], info["enc_key"]
    return None, None


def get_all_msg_dbs(keys):
    """Get all message DB paths and keys."""
    dbs = []
    for rel, info in keys.items():
        if re.match(r'.*/message/message_\d+\.db$', info.get("path", "")):
            dbs.append((info["path"], info["enc_key"]))
    return sorted(dbs)


def get_contact_db(keys):
    """Get contact DB path and key."""
    for rel, info in keys.items():
        if "contact/contact.db" in rel:
            return info["path"], info["enc_key"]
    return None, None


def cmd_contacts(keys):
    """List all contacts with nicknames."""
    path, key = get_contact_db(keys)
    if not path:
        print("Contact DB not found"); return
    rows = query_db(path, key, """
SELECT username, nick_name, remark, alias FROM contact
WHERE nick_name IS NOT NULL AND nick_name != ''
ORDER BY id DESC;
""")
    print(f"{'wxid':<30} {'昵称':<20} {'备注':<15} {'微信号'}")
    print("-" * 90)
    for row in rows:
        parts = row.split("|", 3)
        if len(parts) >= 2:
            wxid = parts[0].strip('"')
            nick = parts[1].strip('"')
            remark = parts[2].strip('"') if len(parts) > 2 else ""
            alias = parts[3].strip('"') if len(parts) > 3 else ""
            print(f"{wxid:<30} {nick:<20} {remark:<15} {alias}")


def cmd_recent(keys, n=20):
    """Show most recent N messages across all chats."""
    contact_path, contact_key = get_contact_db(keys)
    # Build wxid -> nickname map
    nick_map = {}
    if contact_path:
        rows = query_db(contact_path, contact_key,
                        "SELECT username, nick_name, remark FROM contact;")
        for row in rows:
            parts = row.split("|", 2)
            if len(parts) >= 2:
                wxid = parts[0].strip('"')
                nick = parts[2].strip('"') if len(parts) > 2 and parts[2].strip('"') else parts[1].strip('"')
                nick_map[wxid] = nick

    msg_dbs = get_all_msg_dbs(keys)
    all_msgs = []
    for db_path, db_key in msg_dbs:
        # Get all Msg_ tables
        tables = query_db(db_path, db_key,
                          "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%';")
        # Get Name2Id mapping
        name2id = {}
        n2i_rows = query_db(db_path, db_key, "SELECT user_name, id FROM Name2Id;")
        for row in n2i_rows:
            parts = row.split("|", 1)
            if len(parts) == 2:
                name2id[parts[0].strip('"')] = parts[1].strip('"')

        # Build table_hash -> username map
        hash2user = {}
        for uname, uid in name2id.items():
            # Table name is Msg_{md5(username)}
            import hashlib
            h = hashlib.md5(uname.encode()).hexdigest()
            hash2user[h] = uname

        for table_row in tables:
            tname = table_row.strip().strip('"')
            table_hash = tname.replace("Msg_", "")
            username = hash2user.get(table_hash, table_hash[:12])
            nick = nick_map.get(username, username)

            rows = query_db(db_path, db_key, f"""
SELECT datetime(create_time, 'unixepoch', 'localtime'),
       substr(message_content, 1, 200),
       local_type
FROM [{tname}]
WHERE message_content IS NOT NULL AND message_content != ''
ORDER BY create_time DESC LIMIT {n};
""")
            for row in rows:
                parts = row.split("|", 2)
                if len(parts) >= 2:
                    ts = parts[0].strip('"')
                    content = parts[1].strip('"')[:150]
                    msg_type = parts[2].strip('"') if len(parts) > 2 else "?"
                    all_msgs.append((ts, nick, content, msg_type))

    # Sort by time desc and take top N
    all_msgs.sort(key=lambda x: x[0], reverse=True)
    for ts, nick, content, mtype in all_msgs[:n]:
        type_str = {"1": "文字", "3": "图片", "34": "语音", "43": "视频", "47": "表情",
                    "49": "链接/文件", "10000": "系统"}.get(mtype, f"type:{mtype}")
        content_clean = re.sub(r'<[^>]+>', '', content).strip()[:100]
        if content_clean:
            print(f"[{ts}] {nick}: {content_clean}  ({type_str})")


def cmd_search(keys, keyword, n=50):
    """Search messages containing keyword."""
    contact_path, contact_key = get_contact_db(keys)
    nick_map = {}
    if contact_path:
        rows = query_db(contact_path, contact_key,
                        "SELECT username, nick_name, remark FROM contact;")
        for row in rows:
            parts = row.split("|", 2)
            if len(parts) >= 2:
                wxid = parts[0].strip('"')
                nick = parts[2].strip('"') if len(parts) > 2 and parts[2].strip('"') else parts[1].strip('"')
                nick_map[wxid] = nick

    msg_dbs = get_all_msg_dbs(keys)
    results = []
    for db_path, db_key in msg_dbs:
        tables = query_db(db_path, db_key,
                          "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%';")
        for table_row in tables:
            tname = table_row.strip().strip('"')
            rows = query_db(db_path, db_key, f"""
SELECT datetime(create_time, 'unixepoch', 'localtime'),
       substr(message_content, 1, 300)
FROM [{tname}]
WHERE message_content LIKE '%{keyword}%'
ORDER BY create_time DESC LIMIT {n};
""")
            for row in rows:
                parts = row.split("|", 1)
                if len(parts) >= 2:
                    ts = parts[0].strip('"')
                    content = re.sub(r'<[^>]+>', '', parts[1].strip('"')).strip()[:150]
                    results.append((ts, tname, content))

    results.sort(key=lambda x: x[0], reverse=True)
    print(f"Found {len(results)} messages containing '{keyword}':")
    for ts, tbl, content in results[:n]:
        print(f"  [{ts}] {content}")


def cmd_chat(keys, target, n=30):
    """Show messages from a specific contact (by nickname, remark, or wxid)."""
    contact_path, contact_key = get_contact_db(keys)
    target_wxid = target

    if contact_path:
        rows = query_db(contact_path, contact_key,
                        "SELECT username, nick_name, remark FROM contact;")
        for row in rows:
            parts = row.split("|", 2)
            if len(parts) >= 2:
                wxid = parts[0].strip('"')
                nick = parts[1].strip('"')
                remark = parts[2].strip('"') if len(parts) > 2 else ""
                if target.lower() in nick.lower() or target.lower() in remark.lower() or target == wxid:
                    target_wxid = wxid
                    print(f"Contact: {nick} ({remark}) [{wxid}]")
                    break

    import hashlib
    table_hash = hashlib.md5(target_wxid.encode()).hexdigest()
    table_name = f"Msg_{table_hash}"

    msg_dbs = get_all_msg_dbs(keys)
    found = False
    for db_path, db_key in msg_dbs:
        tables = query_db(db_path, db_key,
                          f"SELECT name FROM sqlite_master WHERE name='{table_name}';")
        if tables:
            found = True
            rows = query_db(db_path, db_key, f"""
SELECT datetime(create_time, 'unixepoch', 'localtime'),
       message_content,
       local_type
FROM [{table_name}]
WHERE message_content IS NOT NULL AND message_content != ''
ORDER BY create_time DESC LIMIT {n};
""")
            for row in rows:
                parts = row.split("|", 2)
                if len(parts) >= 2:
                    ts = parts[0].strip('"')
                    content = re.sub(r'<[^>]+>', '', parts[1].strip('"')).strip()[:200]
                    if content:
                        print(f"[{ts}] {content}")
            break

    if not found:
        print(f"No chat found for '{target}'")


def main():
    find_sqlcipher()
    keys = load_keys()

    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]
    if cmd == "contacts":
        cmd_contacts(keys)
    elif cmd == "recent":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        cmd_recent(keys, n)
    elif cmd == "search":
        if len(sys.argv) < 3:
            print("Usage: query_wechat.py search <keyword>")
            return
        cmd_search(keys, sys.argv[2])
    elif cmd == "chat":
        if len(sys.argv) < 3:
            print("Usage: query_wechat.py chat <nick_or_wxid> [N]")
            return
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 30
        cmd_chat(keys, sys.argv[2], n)
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == '__main__':
    main()
