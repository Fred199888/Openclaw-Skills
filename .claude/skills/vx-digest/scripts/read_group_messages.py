#!/usr/bin/env python3
"""
读取指定微信群的消息，支持增量读取（从上次时间戳之后开始）。
依赖 vx-secret skill 的 keys.json 和 sqlcipher。

Usage:
  python3 read_group_messages.py "群名1,群名2" [--after TIMESTAMP] [--limit 200]

Output: JSON to stdout
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VX_SECRET_DIR = os.path.join(os.path.dirname(SKILL_DIR), "vx-secret")
KEYS_FILE = os.path.join(VX_SECRET_DIR, "keys.json")
WECHAT_BASE = os.path.expanduser(
    "~/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files"
)
SQLCIPHER = None
MAX_MESSAGES = 200


def find_sqlcipher():
    global SQLCIPHER
    for p in ["/opt/homebrew/bin/sqlcipher", "/usr/local/bin/sqlcipher"]:
        if os.path.isfile(p):
            SQLCIPHER = p
            return
    w = shutil.which("sqlcipher")
    if w:
        SQLCIPHER = w
        return
    print("ERROR: sqlcipher not found", file=sys.stderr)
    sys.exit(1)


def load_keys():
    if not os.path.isfile(KEYS_FILE):
        print(f"ERROR: {KEYS_FILE} not found", file=sys.stderr)
        sys.exit(1)
    with open(KEYS_FILE) as f:
        return json.load(f)


def query_db(db_path, key_hex, sql):
    db_copy = f"/tmp/vx_digest_{os.path.basename(db_path)}"
    shutil.copy2(db_path, db_copy)
    for ext in ["-wal", "-shm"]:
        src = db_path + ext
        if os.path.isfile(src):
            shutil.copy2(src, db_copy + ext)

    full_sql = f'PRAGMA key = "x\'{key_hex}\'";\nPRAGMA cipher_compatibility = 4;\n.mode list\n.separator †\n{sql}'
    try:
        result = subprocess.run(
            [SQLCIPHER, db_copy], input=full_sql.encode('utf-8'),
            capture_output=True, timeout=30
        )
        stdout = result.stdout.decode('utf-8', errors='replace')
        return [l for l in stdout.strip().split('\n') if l and l != 'ok']
    except Exception as e:
        return []
    finally:
        for f in [db_copy, db_copy + "-wal", db_copy + "-shm"]:
            try:
                os.unlink(f)
            except:
                pass


def get_contact_db(keys):
    for rel, info in keys.items():
        if "contact/contact.db" in rel:
            return info["path"], info["enc_key"]
    return None, None


def get_msg_dbs(keys):
    dbs = []
    for rel, info in keys.items():
        if re.match(r'.*/message/message_\d+\.db$', info.get("path", "")):
            dbs.append((info["path"], info["enc_key"]))
    return sorted(dbs)


def build_nick_map(keys):
    """Build wxid -> nickname map from contact DB."""
    nick_map = {}
    path, key = get_contact_db(keys)
    if not path:
        return nick_map
    rows = query_db(path, key, "SELECT username, nick_name, remark FROM contact;")
    for row in rows:
        parts = row.split("†", 2)
        if len(parts) >= 2:
            wxid = parts[0].strip('"')
            nick = parts[1].strip('"')
            remark = parts[2].strip('"') if len(parts) > 2 and parts[2].strip('"') else ""
            nick_map[wxid] = remark if remark else nick
    return nick_map


def find_group_chatroom_id(keys, group_name, nick_map):
    """Find chatroom ID by group name from contact DB."""
    path, key = get_contact_db(keys)
    if not path:
        return None
    rows = query_db(path, key,
        f"SELECT username, nick_name FROM contact WHERE nick_name LIKE '%{group_name}%' AND username LIKE '%@chatroom';")
    if rows:
        parts = rows[0].split("†", 1)
        return parts[0].strip('"')
    return None


def read_group_messages(keys, chatroom_id, nick_map, after_ts=0, limit=MAX_MESSAGES):
    """Read messages from a group chat after given timestamp."""
    table_hash = hashlib.md5(chatroom_id.encode()).hexdigest()
    table_name = f"Msg_{table_hash}"

    msg_dbs = get_msg_dbs(keys)
    messages = []

    for db_path, db_key in msg_dbs:
        # Check if table exists
        tables = query_db(db_path, db_key,
            f"SELECT name FROM sqlite_master WHERE name='{table_name}';")
        if not tables:
            continue

        # Query messages after timestamp
        where = f"WHERE message_content IS NOT NULL AND message_content != '' AND create_time > {after_ts}"
        rows = query_db(db_path, db_key, f"""
SELECT create_time,
       replace(replace(message_content, char(10), '⏎'), char(13), ''),
       local_type
FROM [{table_name}]
{where}
ORDER BY create_time ASC
LIMIT {limit};
""")
        for row in rows:
            parts = row.split("†", 2)
            if len(parts) < 2:
                continue
            ts = parts[0].strip('"')
            content = parts[1].strip('"')
            msg_type = parts[2].strip('"') if len(parts) > 2 else "1"

            # Extract sender from group message (format: wxid:\ncontent)
            sender = ""
            actual_content = content
            if msg_type == "1":  # text
                # Group messages have sender prefix
                if ":⏎" in content:
                    sender_id, actual_content = content.split(":⏎", 1)
                    sender = nick_map.get(sender_id, sender_id)
                # Clean XML tags
                actual_content = re.sub(r'<[^>]+>', '', actual_content).strip()
            elif msg_type == "3":
                actual_content = "[图片]"
            elif msg_type == "34":
                actual_content = "[语音]"
            elif msg_type == "43":
                actual_content = "[视频]"
            elif msg_type == "47":
                actual_content = "[表情]"
            elif msg_type == "49":
                actual_content = "[链接/文件]"
            elif msg_type == "10000":
                actual_content = re.sub(r'<[^>]+>', '', content).strip()
                sender = "[系统]"
            else:
                actual_content = f"[type:{msg_type}]"

            if actual_content:
                try:
                    time_str = datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d %H:%M:%S')
                except:
                    time_str = ts

                messages.append({
                    "timestamp": int(ts) if ts.isdigit() else 0,
                    "time": time_str,
                    "sender": sender,
                    "content": actual_content[:500],
                    "type": msg_type
                })
        break  # Found the table, no need to check other DBs

    return messages[:limit]


def main():
    find_sqlcipher()
    keys = load_keys()
    nick_map = build_nick_map(keys)

    # Parse args
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} \"群名1,群名2\" [--after TIMESTAMP] [--limit N]", file=sys.stderr)
        sys.exit(1)

    group_names = [g.strip() for g in sys.argv[1].split(",") if g.strip()]
    after_ts = 0
    limit = MAX_MESSAGES

    for i, arg in enumerate(sys.argv[2:], 2):
        if arg == "--after" and i + 1 < len(sys.argv):
            after_ts = int(sys.argv[i + 1])
        elif arg == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])

    results = {}
    for name in group_names:
        chatroom_id = find_group_chatroom_id(keys, name, nick_map)
        if not chatroom_id:
            results[name] = {"error": f"群 '{name}' 未找到", "messages": []}
            continue

        msgs = read_group_messages(keys, chatroom_id, nick_map, after_ts, limit)
        results[name] = {
            "chatroom_id": chatroom_id,
            "message_count": len(msgs),
            "messages": msgs,
            "first_ts": msgs[0]["timestamp"] if msgs else 0,
            "last_ts": msgs[-1]["timestamp"] if msgs else 0,
            "last_time": msgs[-1]["time"] if msgs else "",
        }

    json.dump(results, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
