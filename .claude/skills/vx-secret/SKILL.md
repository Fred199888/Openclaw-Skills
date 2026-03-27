---
name: vx-secret
description: >
  macOS 微信(WeChat)聊天记录提取与查询。从微信进程内存中提取 SQLCipher 加密密钥，
  解密本地数据库，支持查看联系人、最近消息、按联系人查看、搜索关键词等。
  触发场景：(1) 用户要求查看/读取/搜索微信聊天记录 (2) 用户说"查微信消息"、
  "看看和某某的聊天"、"搜索微信里的xxx" (3) 执行 /vx-secret 命令。
  仅支持 macOS + WeChat 4.x。
---

# VX Secret — 微信消息提取

## 前置条件

- macOS (Apple Silicon 或 Intel)
- WeChat 4.x 已安装
- `sqlcipher` CLI: `brew install sqlcipher`

## 流程

### Phase 1: 环境准备

1. 检查微信是否运行: `pgrep -x WeChat`
2. 若未运行，提示用户打开微信并登录
3. 检查微信是否已重签（移除 hardened runtime）:

```bash
codesign -d --flags - /Applications/WeChat.app 2>&1 | grep -q "runtime"
```

若含 `runtime` 标志，需重签:

```bash
sudo codesign --force --deep --sign - /Applications/WeChat.app
```

重签后**必须重启微信**（kill + reopen），用户需重新登录。

4. 确认数据库已打开（用户已登录）:

```bash
lsof -p $(pgrep -x WeChat) | grep "\.db"
```

若无 .db 文件，提示用户先登录微信。

### Phase 2: 提取密钥

运行密钥提取脚本（需 sudo）:

```bash
sudo python3 scripts/extract_keys.py
```

脚本通过 Mach VM API (`task_for_pid` + `mach_vm_read`) 扫描微信进程内存，
使用 HMAC-SHA512 验证候选密钥（SQLCipher 4），输出到 `/tmp/vx_secret_keys.json`。

若 `task_for_pid` 失败，说明未重签或未用 sudo。

### Phase 3: 查询消息

用 `scripts/query_wechat.py` 或直接用 sqlcipher 查询:

```bash
# 列出联系人
python3 scripts/query_wechat.py contacts

# 最近 N 条消息
python3 scripts/query_wechat.py recent 30

# 搜索关键词
python3 scripts/query_wechat.py search "关键词"

# 查看与某人的聊天（支持昵称/备注/wxid）
python3 scripts/query_wechat.py chat "昵称" 50
```

### 直接 sqlcipher 查询

从 `/tmp/vx_secret_keys.json` 获取 key，然后:

```bash
sqlcipher <db_path> <<EOF
PRAGMA key = "x'<64位hex密钥>'";
PRAGMA cipher_compatibility = 4;
<SQL语句>
EOF
```

## 数据库结构

WeChat 4.x 数据目录:
`~/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/{wxid}/db_storage/`

| 数据库 | 内容 |
|--------|------|
| `message/message_0~9.db` | 聊天消息（按 hash 分库） |
| `contact/contact.db` | 联系人信息 |
| `group/group.db` | 群聊信息 |

**消息表**: 每个聊天对应一个 `Msg_{md5(username)}` 表:
- `message_content` — 消息内容（文字/XML）
- `create_time` — Unix 时间戳
- `local_type` — 1:文字 3:图片 34:语音 43:视频 47:表情 49:链接/文件 10000:系统

**联系人表** `contact`:
- `username` — wxid
- `nick_name` — 昵称
- `remark` — 备注名
- `alias` — 微信号

**Name2Id 表**: 消息库中 `user_name` → 表 hash 的映射。
