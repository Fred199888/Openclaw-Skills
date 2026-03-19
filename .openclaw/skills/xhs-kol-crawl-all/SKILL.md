---
name: xhs-kol-crawl-all
description: 关键词全量抓取小红书蒲公英KOL，并同步到飞书多维表。支持同关键词重复执行更新（重抓+重写），认证参数通过 .env 热更新。
---

# xhs-kol-crawl-all

标准流程（端到端）如下：

## 1) 准备认证参数（必需）
认证参数建议优先读取全局：`~/.openclaw/env/global.env`；
本地 `xhs-kol-crawl-all/.env` 仅作覆盖。

必填：
- `XHS_COOKIE`
- `XHS_X_S`
- `XHS_X_S_COMMON`
- `XHS_X_T`
- `XHS_BRAND_USER_ID`

可选：
- `XHS_TRACK_ID`（不传自动生成）

> 说明：小红书参数会失效，失效后只需要更新 `.env` 再重跑，不改脚本。

## 2) 执行抓取（Python）
```bash
python3 scripts/crawl_kols.py --keyword "openclaw" --page-size 20 --max-pages 200
```

## 2.1) 执行整包（多关键词抓取+同步+备份）
```bash
python3 scripts/run_pack.py --max-pages 60 --workers 2 --note-concurrency 20 --write-concurrency 20 --batch-size 30
```

可选参数：
- `--env /path/to/.env`
- `--out-dir ./output`

输出文件：
- `kols_<keyword>_<timestamp>.json`
- `kols_<keyword>_<timestamp>.csv`

## 3) 字段口径（当前实现）
脚本会做标准化，重点规则：
- 粉丝数优先 `fansNum`（`fansCount` 常为 0）
- 阅读中位数优先 `readMidNor30`
- 互动中位数优先 `interMidNor30`
- 近期笔记先取 `noteList` 的前 2 个 `noteId`，再调用：
  - `GET /api/solar/note/{noteId}/detail?bizCode=`
  - 取返回 `data.noteLink`（带 `xsec_token`）
  - 分别写入 `recentNoteUrl` / `recentNoteUrl2`
- 蒲公英主页按公式拼接：
  - `https://pgy.xiaohongshu.com/solar/pre-trade/blogger-detail/{userId}?track_id={trackId}&source=Advertiser_Kol`

当前输出字段：
- `name`, `redId`, `userId`, `location`, `businessNoteCount`
- `fansCount`, `fansNum`, `readMidNor30`, `interMidNor30`
- `picturePrice`, `videoPrice`, `lowerPrice`
- `recentNoteId`, `recentNoteId2`
- `recentNoteUrl`, `recentNoteUrl2`, `recentNoteUrls`
- `trackId`, `pgyHomeUrl`, `contentTags`, `featureTags`

## 4) 飞书表同步规则（通用）
- 表名 = 关键词（如 `openclaw` / `AI`）
- 权限 = 全公司可编辑（同租户可编辑，外部关闭）
- 列模板固定：
  1) KOL
  2) 近期笔记
  3) 近期笔记2
  4) 蒲公英主页
  5) 粉丝数
  6) 阅读中位数（日常）
  7) 互动中位数（日常）
  8) 全部报价
  9) 微信号
  10) 小红书号
  11) 地区
  12) 内容方向
  13) 人设标签

写入映射：
- `近期笔记` <- `recentNoteUrl`
- `近期笔记2` <- `recentNoteUrl2`
- `蒲公英主页` <- `pgyHomeUrl`

## 5) 同关键词重复调用（更新策略）
当再次调用相同关键词：
1. 重抓最新全量数据
2. 先清空该关键词表旧记录
3. 按最新抓取结果全量写回

这样确保表内容总是和“最新一轮抓取”一致，避免脏数据累计。

## 6) 并发策略（固定）
- 全流程并发固定为 `30`（用户要求）
- note detail 二次查询并发：`30`
- 飞书写入并发：`30`
- 需要重试/退避时，保持并发上限不变，仅做请求级重试

## 7) 故障排查
- `permission denied` / 401 / 403：更新 `.env` 认证参数后重试
- 连接慢或超时：重试并汇报进度（建议每 100 条播报一次）
- 字段空值：先检查原始 JSON 是否含该字段，再扩展映射
