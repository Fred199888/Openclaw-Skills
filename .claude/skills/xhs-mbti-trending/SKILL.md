---
name: xhs-mbti
description: 小红书 MBTI 热帖采集 - 自动抓取近一周最火的 50 条 MBTI 相关帖子
user-invocable: true
---

# 小红书 MBTI 热帖采集

从 Chrome 浏览器提取小红书登录态，自动搜索 MBTI 关键词，采集近一周最火的 50 条帖子。

## 前置条件
- Chrome 浏览器中已登录小红书账号
- `pip3 install playwright pycookiecheat`
- `playwright install chromium`

## 脚本路径
- 采集脚本: `~/.claude/skills/xhs-mbti-trending/scripts/xhs_mbti_search.py`

## 执行流程

### Step 1: 运行采集
```bash
python3 ~/.claude/skills/xhs-mbti-trending/scripts/xhs_mbti_search.py
```

脚本会自动：
1. 从 Chrome 提取小红书 cookies（通过 pycookiecheat）
2. 打开 Chromium 有头浏览器，注入 cookies
3. 在搜索框输入 MBTI 搜索
4. 滚动加载 100+ 条帖子
5. 逐条访问详情页获取完整数据
6. 过滤近一周 + 按点赞排序 → Top 50

### Step 2: 输出结果
采集完成后：
1. 读取 `~/.claude/skills/xhs-mbti-trending/data/latest.json`
2. 向用户展示 Top 10 帖子摘要（标题 + 点赞数）
3. 告知完整结果文件路径

## 输出文件（Skill 目录下 data/）
- `~/.claude/skills/xhs-mbti-trending/data/mbti_trending_{YYYYMMDD_HHmmss}.json` — 结构化数据
- `~/.claude/skills/xhs-mbti-trending/data/mbti_trending_{YYYYMMDD_HHmmss}.md` — Markdown 报告
- `~/.claude/skills/xhs-mbti-trending/data/latest.json` — 最新结果（覆盖更新）

## 注意事项
- 需要 Chrome 浏览器已登录小红书（cookies 从 Chrome 提取）
- 采集期间会弹出一个 Chromium 窗口自动操作，不影响用户的 Chrome
- 采集过程约需 3-5 分钟（需逐条访问详情页）
- 历史数据不会被覆盖，支持累积分析
