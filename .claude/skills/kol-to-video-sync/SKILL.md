---
name: kol-to-video-sync
description: |
  将KOL总表中有明确跟进进度（非无操作/已私信）的记录同步到"kol视频渠道建设表（总）"，
  包含备份、去重匹配、批量更新/创建。用于每日飞书KOL到视频渠道表同步。

  **触发场景：**
  - 用户说"同步KOL到视频表"、"跑KOL同步"
  - 执行 /kol-to-video-sync 命令

  **前置条件：**
  - 飞书认证：~/.claude/skills/xhs-global.env 中的 FEISHU_APP_ID/FEISHU_APP_SECRET
---

# kol-to-video-sync

## 运行
```bash
python3 ~/.claude/skills/kol-to-video-sync/scripts/sync_kol_to_video_table.py
```

## 说明
- 脚本会先备份目标表（JSON + CSV），再执行同步
- 仅同步 KOL 表中 进度 不属于 {"无操作", "已私信"} 的记录
- 去重优先"联系方式(小红书号)"，其次"名字"
- 字段映射：
  - 名字 <- KOL
  - 体量 <- 粉丝数
  - 代表作链接 <- 近期笔记
  - 简介 <- 内容方向（多选拼接）
  - 渠道 <- "小红书"
  - 进度 <- 进度
  - 联系方式 <- 小红书号

## 环境变量
- `XHS_KOL_APP_TOKEN` — KOL 总表 app_token（默认 VyT3b5aKRa9WgpsUlQdcKCgQnbd）
- `XHS_KOL_TABLE_ID` — KOL 总表 table_id（默认 tbl1Y0FeR38G5Z8i）
- `VIDEO_APP_TOKEN` — 视频渠道表 app_token（默认 S8Zeb8p5VaoXl6slfsscGdXEnou）
- `VIDEO_TABLE_ID` — 视频渠道表 table_id（默认 tblwB8En3N1gMPTe）
