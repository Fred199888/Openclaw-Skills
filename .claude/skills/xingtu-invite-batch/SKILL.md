---
name: xingtu-invite-batch
description: |
  按飞书多维表筛选规则批量发送巨量星图KOL邀约，并批量回写进度。
  使用全局鉴权环境变量文件，与 xingtu-kol-crawl-all 共用同一套认证。

  **触发场景：**
  - 用户说"发送星图邀约"、"批量星图邀约"、"run xingtu invites"
  - 执行 /xingtu-invite-batch 命令

  **前置条件：**
  - ~/.claude/skills/xhs-global.env 包含有效的 XINGTU_COOKIE / XINGTU_CSRF_TOKEN
  - 飞书认证：~/.claude/skills/xhs-global.env 中的 FEISHU_APP_ID/FEISHU_APP_SECRET
---

# xingtu-invite-batch

## 标准流程

### 1) 检查认证
确认 `~/.claude/skills/xhs-global.env` 中的 `XINGTU_COOKIE` 和 `XINGTU_CSRF_TOKEN` 有效。

### 2) 配置邀约参数
本地 `.env` 中的邀约参数可按需调整：
- `XINGTU_PRODUCT_NAME` — 产品名称
- `XINGTU_BUDGET` — 预算（元）
- `XINGTU_FIRST_CLASS_CATEGORY` / `XINGTU_SECOND_CLASS_CATEGORY` — 类目
- `XINGTU_EXPIRATION_DAYS` — 合作有效期（天）
- `XINGTU_MIN_FOLLOWERS` — 粉丝数筛选阈值
- `XINGTU_INVITE_TOTAL` — 每批邀约数量

### 3) 执行邀约
```bash
python3 ~/.claude/skills/xingtu-invite-batch/scripts/run_invites.py --total 20
```

可选参数：
- `--total N` — 邀约数量（默认 20）
- `--min-followers N` — 粉丝数阈值（默认 10000）
- `--delay-min F` — 最小延迟秒数（默认 0.5）
- `--delay-max F` — 最大延迟秒数（默认 2.0）

### 4) 筛选规则
从飞书表「巨量星图KOL」（app_token: H6c2bgUWya8XdEsfBgzclDNLn1b, table_id: tblG6pvpqkPmCkrP）读取，筛选条件：
- `进度 == "无操作"`
- `星图ID` 非空
- `粉丝数 ≥ min_followers`
- 按粉丝数降序排序，取前 N 条

### 5) 邀约流程（逐条）
1. `apply_contact_info?dest_id={星图ID}&contact_type=1` → 获取 chat_id
2. `send_message` → 发送 type=8 邀约消息（参数从 .env 读取）
3. 成功 → 飞书表更新：进度="已私信"，修改时间=now

### 6) 输出
JSON 报告：selected / sent / success / failed / failed_kols
