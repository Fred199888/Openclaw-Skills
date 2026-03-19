---
name: kol-to-video-sync
description: 将KOL总表中有明确跟进进度（非无操作/已私信）的记录同步到“kol视频渠道建设表（总）”，包含备份、去重匹配、批量更新/创建。用于每日飞书KOL到视频渠道表同步。
---

# kol-to-video-sync

运行：
```bash
python3 scripts/sync_kol_to_video_table.py
```

说明：
- 脚本会先备份目标表，再执行同步。
- 去重优先“联系方式(小红书号)”，其次“名字”。
