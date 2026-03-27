---
name: article-fetch
description: |
  抓取网页文章的完整内容和关键图片。用于：
  (1) 给定 URL，提取文章标题、正文、关键图片
  (2) 下载文章中的关键图表/示意图到本地
  (3) 输出结构化的文章摘要供后续 skill 使用

  **触发场景：**
  - 用户提供一个文章 URL 需要提取内容
  - article-to-video 编排器调用
  - 需要理解一篇在线文章的完整内容
---

# article-fetch

## Instructions

1. 全程输出中文。
2. 接收参数：`url`（文章地址）、`output_dir`（图片保存目录，通常为项目的 `images/` 子目录）。

### 步骤 1：抓取网页

使用 WebFetch 获取文章内容。如果返回 403/被拦截，降级为 curl：

```bash
curl -sL \
  -H "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36" \
  -H "Accept: text/html,application/xhtml+xml" \
  -H "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8" \
  -c /tmp/cookies.txt \
  "<url>" -o /tmp/article_raw.html
```

### 步骤 2：提取正文

从 HTML 中提取：
- **标题**：`<h1>` 或 `<title>`
- **作者**：meta 标签或 byline
- **正文段落**：主要内容区域的 `<p>` 标签文本
- **关键图片 URL**：`<img>` 标签的 `src`，保留图表/架构图/流程图，过滤 logo/头像/装饰图

输出纯文本摘要（不超过 3000 字），包含所有关键论点和数据。

### 步骤 3：下载图片

将关键图片下载到 `output_dir/`（即项目的 `images/` 目录），命名为 `fig1_<desc>.png`、`fig2_<desc>.png` 等。

选择标准：
- 优先：图表、架构图、流程图、示意图
- 排除：logo、头像、背景图、广告
- 如有 dark/light 变体，选深色版本（PPT 背景为深色）
- 通常 4-6 张即可

**注意：** 手机竖屏模式下，幻灯片不直接嵌入文章原图（桌面图表缩到手机上文字太小），改用大字体自绘简化版。图片仅供内容理解参考。

### 输出

```
═══════════ article-fetch 完成 ═══════════
标题：<title>
作者：<author>
正文：<约 N 字>
图片：<N> 张已下载至 <output_dir>/
  - fig1_xxx.png: <描述>
  - fig2_xxx.png: <描述>
```
