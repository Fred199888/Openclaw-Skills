# kol-progress-to-video-sync - 使用文档

来源：.openclaw/skills/kol-progress-to-video-sync/SKILL.md

---
name: kol-progress-to-video-sync
description: 将Openclaw BD与Information营销活动bd表中有效进度数据同步沉淀到“kol视频渠道建设表（总）”，包含备份、去重、字段兼容写入与失败回退。用于每日飞书进度沉淀同步。
---

# kol-progress-to-video-sync

运行：
```bash
python3 scripts/sync_kol_progress_to_video_table.py
```

说明：
- 同步前自动备份目标表。
- 自动维护“来源表”字段并写入来源信息。
