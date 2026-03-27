---
name: xingtu-kol-crawl-all
description: |
  关键词全量抓取巨量星图KOL，并同步到飞书多维表。支持同关键词重复执行更新（重抓+重写），认证参数通过 .env 热更新。
  支持多关键词整包执行（run_pack.py），包含抓取+同步+备份完整流程。

  **触发场景：**
  - 用户说"抓取星图KOL"、"跑星图抓取"、"run xingtu crawl"
  - 用户提供关键词要求抓取巨量星图数据
  - 执行 /xingtu-kol-crawl-all 命令

  **前置条件：**
  - ~/.claude/skills/xhs-global.env 包含有效的 XINGTU_COOKIE / XINGTU_CSRF_TOKEN
  - 飞书认证：~/.claude/skills/xhs-global.env 中的 FEISHU_APP_ID/FEISHU_APP_SECRET
---

# xingtu-kol-crawl-all

标准流程（端到端）如下：

## 1) 准备认证参数（必需）
认证参数优先读取全局：`~/.claude/skills/xhs-global.env`；
本地 `xingtu-kol-crawl-all/.env` 仅作覆盖。

必填：
- `XINGTU_COOKIE` — 从浏览器 Network 请求中复制完整 cookie
- `XINGTU_CSRF_TOKEN` — `x-secsdk-csrf-token` header 值

> 说明：星图参数会失效，失效后只需更新 `.env` 再重跑，不改脚本。

## 2) 执行抓取（Python）
```bash
python3 ~/.claude/skills/xingtu-kol-crawl-all/scripts/crawl_kols.py --keyword "openclaw" --page-size 20 --max-pages 200
```

## 2.1) 执行整包（多关键词抓取+同步+备份）
```bash
python3 ~/.claude/skills/xingtu-kol-crawl-all/scripts/run_pack.py --max-pages 60 --workers 2 --write-concurrency 20 --batch-size 30
```

可选参数：
- `--env /path/to/.env`
- `--out-dir ./output`

输出文件：
- `kols_<keyword>_<timestamp>.json`
- `kols_<keyword>_<timestamp>.csv`

## 3) 字段口径（当前实现）
- 粉丝数: `follower`
- 播放中位数: `vv_median_30d`（30天）
- 互动中位数: `interaction_median_30d`（30天）
- 互动率: `interact_rate_within_30d`（小数，如 0.0184）
- 完播率: `play_over_rate_within_30d`（小数，如 0.2381）
- 报价: `price_1_20` / `price_20_60` / `price_60`（单位：元，直接使用）
- 近期视频: `last_10_items` JSON 解析后取前2条 item_id → 拼接 `https://www.douyin.com/video/{item_id}`
- 星图主页: `https://www.xingtu.cn/ad/creator/author/douyin/{star_id}`
- 内容方向: `content_theme_labels_180d` JSON 解析

当前输出字段：
- `name`, `starId`, `coreUserId`, `follower`, `location`
- `vvMedian30d`, `interactionMedian30d`, `interactRate30d`, `playOverRate30d`
- `fansIncrement30d`, `expectedPlayNum`
- `price1_20`, `price20_60`, `price60`
- `spreadIndex`, `shoppingIndex`, `convertIndex`
- `contentTags`, `authorType`
- `recentVideoUrl`, `recentVideoUrl2`, `xingtHomeUrl`

## 4) 飞书表同步规则
- 表名: 巨量星图KOL
- app_token: `H6c2bgUWya8XdEsfBgzclDNLn1b`
- table_id: `tblG6pvpqkPmCkrP`
- 列（27列）:
  - 达人信息（文本）/ 关键词（多选）/ 进度（单选）
  - 星图主页（URL）/ 近期视频（URL）/ 近期视频2（URL）
  - 达人类型（多选，如"科技数码"）/ 内容主题（多选，如"AI应用","科技科普"）
  - 连接用户数 / 粉丝数 / 预期CPM / 预期播放量
  - 互动率（百分比）/ 完播率（百分比）/ 30天涨粉
  - 1-20s报价 / 21-60s报价 / 60s+报价
  - 传播指数 / 种草指数 / 转化指数
  - 地区 / 星图ID / 抖音UID / vx号（手动填写）
  - 创建时间（日期）/ 修改时间（日期）

## 5) 去重与更新策略
1. 重抓最新全量数据
2. 按「星图ID → 抖音UID → 达人信息」三级优先匹配已有记录
3. **匹配到 → 更新**：所有抓取字段全部覆盖（关键词做并集追加），仅保留以下手动填写字段不覆盖：
   - `进度`（BD跟进状态）
   - `vx号`（手动填写）
   - `创建时间`（首次写入时间）
4. **未匹配 → 新增**：创建新记录，进度默认"无操作"
5. 修改时间每次同步自动更新
