---
name: xhs-invite-batch
description: |
  按KOL表筛选规则批量发送小红书蒲公英邀约，并批量回写进度/发送邀约时间。
  使用全局鉴权环境变量文件，与 xhs-kol-crawl-all 共用同一套认证。

  **触发场景：**
  - 用户说"发送KOL邀约"、"批量邀约"、"run xhs invites"
  - 执行 /xhs-invite-batch 命令

  **前置条件：**
  - ~/.claude/skills/xhs-global.env 包含有效的 XHS 认证参数
  - 飞书认证：~/.claude/skills/xhs-global.env 中的 FEISHU_APP_ID/FEISHU_APP_SECRET
---

# xhs-invite-batch

## 全局鉴权（共享）
默认读取：`~/.claude/skills/xhs-global.env`

必填：
- `XHS_COOKIE`
- `XHS_X_S`
- `XHS_X_S_COMMON`

## 邀约参数（本地可配）
可通过运行参数传入：
- `--invite-content`
- `--contact-info`

## 默认筛选规则
- `进度 = 无操作`
- `KolID` 非空
- `关键词（多选）` 命中：`openclaw/Claude code/codex/chatgpt/OpenAI/Anthropic/DeepSeek`
- `粉丝数 > 10000`
- 按 `阅读中位数（日常）` 倒序

## 批处理规则
- 每批 20 条（`--batch-size`）
- 并发 20（`--concurrency`）
- 成功后批量更新：
  - `进度 = 已私信`
  - `发送邀约时间 = 当前时间`

## 运行示例
```bash
python3 ~/.claude/skills/xhs-invite-batch/scripts/run_invites.py \
  --total 80 \
  --batch-size 20 \
  --concurrency 20 \
  --invite-content "..." \
  --contact-info "19318359809"
```
