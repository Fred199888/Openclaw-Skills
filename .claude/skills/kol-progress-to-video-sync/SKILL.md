---
name: kol-progress-to-video-sync
description: |
  将Openclaw BD与Information营销活动bd表中有效进度数据同步沉淀到"kol视频渠道建设表（总）"，
  包含备份、去重、字段兼容写入与失败回退。用于每日飞书进度沉淀同步。

  **触发场景：**
  - 用户说"同步活动进度到视频表"、"跑进度沉淀"
  - 执行 /kol-progress-to-video-sync 命令

  **前置条件：**
  - 飞书认证：~/.claude/skills/xhs-global.env 中的 FEISHU_APP_ID/FEISHU_APP_SECRET
---

# kol-progress-to-video-sync

## 运行
```bash
python3 ~/.claude/skills/kol-progress-to-video-sync/scripts/sync_kol_progress_to_video_table.py
```

## 说明
- 同步前自动备份目标表（JSON + CSV）
- 来源表：
  - Openclaw BD（tblXqkvywXxMMo4U）
  - Information营销活动 bd表（tblyxfUsK16nRE2Y）
- 仅同步：进度不为空 且 进度 != "已私信"
- 去重键：名字 + 渠道 + 联系方式（支持模糊名字匹配）
- 自动维护"来源表"字段并写入来源信息
- 批量写入失败自动回退到单条重试

## 环境变量
- `VIDEO_APP_TOKEN` — 目标表 app_token（默认 S8Zeb8p5VaoXl6slfsscGdXEnou）
- `VIDEO_TABLE_ID` — 目标表 table_id（默认 tblwB8En3N1gMPTe）
- `SOURCE_TABLE_OPENCLAW_BD` — 来源表1 table_id（默认 tblXqkvywXxMMo4U）
- `SOURCE_TABLE_INFO_BD` — 来源表2 table_id（默认 tblyxfUsK16nRE2Y）
