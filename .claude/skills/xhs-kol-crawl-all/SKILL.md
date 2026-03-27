---
name: xhs-kol-crawl-all
description: |
  关键词全量抓取小红书蒲公英KOL，并同步到飞书多维表。支持同关键词重复执行更新（重抓+重写），认证参数通过 .env 热更新。
  支持多关键词整包执行（run_pack.py），包含抓取+同步+备份完整流程。

  **触发场景：**
  - 用户说"抓取小红书KOL"、"跑KOL抓取"、"run xhs crawl"
  - 用户提供关键词要求抓取蒲公英数据
  - 执行 /xhs-kol-crawl-all 命令

  **前置条件：**
  - ~/.claude/skills/xhs-global.env 或 xhs-kol-crawl-all/.env 包含有效的 XHS 认证参数
  - 飞书认证：~/.claude/skills/xhs-global.env 中的 FEISHU_APP_ID/FEISHU_APP_SECRET
---

# xhs-kol-crawl-all

标准流程（端到端）如下：

## 1) 准备认证参数（必需）
认证参数优先读取全局：`~/.claude/skills/xhs-global.env`；
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
python3 ~/.claude/skills/xhs-kol-crawl-all/scripts/crawl_kols.py --keyword "openclaw" --page-size 20 --max-pages 200
```

## 2.1) 执行整包（多关键词抓取+同步+备份）
```bash
python3 ~/.claude/skills/xhs-kol-crawl-all/scripts/run_pack.py --max-pages 60 --workers 2 --note-concurrency 20 --write-concurrency 20 --batch-size 30
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
- 近期笔记先取 `noteList` 的前 2 个 `noteId`，再调用 note detail 获取 `noteLink`
- 蒲公英主页按公式拼接

当前输出字段：
- `name`, `redId`, `userId`, `location`, `businessNoteCount`
- `fansCount`, `fansNum`, `readMidNor30`, `interMidNor30`
- `picturePrice`, `videoPrice`, `lowerPrice`
- `recentNoteId`, `recentNoteId2`
- `recentNoteUrl`, `recentNoteUrl2`, `recentNoteUrls`
- `trackId`, `pgyHomeUrl`, `contentTags`, `featureTags`

## 4) 飞书表同步规则（通用）
- 表名 = 关键词（如 `openclaw` / `AI`）
- 列模板固定 13 列：KOL / 近期笔记 / 近期笔记2 / 蒲公英主页 / 粉丝数 / 阅读中位数（日常）/ 互动中位数（日常）/ 全部报价 / 微信号 / 小红书号 / 地区 / 内容方向 / 人设标签

## 5) 同关键词重复调用（更新策略）
1. 重抓最新全量数据
2. 按"优先小红书号，其次KOL"匹配已有记录
3. 关键词做并集追加，进度保留已有值
4. 指标字段按最新抓取更新

## 6) 并发策略（固定）
- 全流程并发固定为 `30`
- note detail 二次查询并发：`30`
- 飞书写入并发：`30`

## 7) 故障排查
- `permission denied` / 401 / 403：更新 `.env` 认证参数后重试
- 连接慢或超时：重试并汇报进度
- 字段空值：先检查原始 JSON 是否含该字段
