---
name: article-to-video
description: |
  文章转视频的全流程编排器。给定一个文章 URL，自动完成：
  抓取文章 → 生成解说词 → TTS 语音 → PPT 幻灯片 → 合成视频。

  **触发场景：**
  - 用户提供文章 URL 并要求生成视频
  - 执行 /article-to-video 命令
  - 用户说"把这篇文章做成视频"

  **依赖的 Skills：**
  article-fetch, narration-gen, tts-gen, video-assemble

  **前置条件：**
  - 环境变量 VOLCANO_APPID 和 VOLCANO_TOKEN（TTS 凭据）
  - pip install requests pydub Pillow
  - ffmpeg 已安装
  - 系统中文字体（macOS: /System/Library/Fonts/STHeiti Medium.ttc）
---

# article-to-video

编排器 skill，负责驱动全流程，不执行具体子步骤细节。

## 执行流程

```
article-to-video (本 skill)
  ↓ 步骤1
article-fetch → 文章正文 + 图片
  ↓ 步骤2
narration-gen → narration.txt（分段解说词）
  ↓ 步骤3
tts-gen → seg_01.mp3 ... seg_N.mp3
  ↓ 步骤4
Claude 生成 PPT → slide_01.png ... slide_M.png
  ↓ 步骤5
video-assemble → 最终 .mp4 视频
```

## 项目目录结构

**根目录：** `~/Desktop/workspace/videoGen/projects/`

每个文章 URL 对应一个独立的项目文件夹，按 URL slug 命名：

```
~/Desktop/workspace/videoGen/projects/
├── harness-engineering/           # openai.com/.../harness-engineering
│   ├── narration.txt              # 解说词
│   ├── generate_ppt.py            # PPT 渲染脚本
│   ├── <文章标题>.mp4              # 最终视频（以文章标题命名）
│   ├── audio/                     # TTS 音频
│   │   ├── seg_01.mp3
│   │   └── ...
│   ├── slides/                    # 幻灯片 PNG
│   │   ├── slide_01.png
│   │   └── ...
│   └── images/                    # 文章原图
│       ├── fig1_xxx.png
│       └── ...
├── effective-harnesses/           # anthropic.com/.../effective-harnesses
│   └── ...
└── <another-slug>/
    └── ...
```

**slug 生成规则：**
- 从 URL 最后一段路径提取，如 `harness-engineering`
- 去除特殊字符，用连字符连接
- 保持简短可读

## Instructions

全程输出中文。严格按步骤执行，每步完成后输出进度。

### 步骤 0：初始化项目

0-A. 从 URL 提取 slug，创建项目目录：
```bash
PROJECT_DIR=~/Desktop/workspace/videoGen/projects/<slug>
mkdir -p "$PROJECT_DIR"/{audio,slides,images}
```

0-B. 检查 TTS 凭据：
```bash
echo "APPID=${VOLCANO_APPID:-(未设置)}" && echo "TOKEN=${VOLCANO_TOKEN:+(已设置)}"
```
如未设置，提示用户并等待。

0-C. 检查依赖：
```bash
python3 -c "import requests; from pydub import AudioSegment; from PIL import Image; print('OK')"
ffmpeg -version 2>&1 | head -1
```

### 步骤 1：抓取文章

调用 article-fetch skill：
- 输入：`url`、`output_dir=$PROJECT_DIR/images/`
- 产出：文章正文（变量保留在上下文）+ 图片文件

### 步骤 2：生成解说词

调用 narration-gen skill：
- 输入：步骤 1 的文章正文、`output_path=$PROJECT_DIR/narration.txt`
- 产出：分段解说词文件

### 步骤 3：生成 TTS 音频

调用 tts-gen skill：
- 输入：`$PROJECT_DIR/narration.txt`、`output_dir=$PROJECT_DIR/audio/`
- 产出：`audio/seg_01.mp3` ... `audio/seg_N.mp3`

### 步骤 4：生成竖屏幻灯片（区块高亮风格）

**使用 `slide_renderer.py` 模块**，所有项目统一调用，不手写 Pillow 代码。

**核心原则：少跳转，多停留。** 约 10 张视觉设计，每张停留 20-40 秒，字幕随音频变化。同一视觉的多段音频通过区块高亮（Block Highlight）区分当前讲解内容。

4-A. 解析区块聚焦映射：
- 读取 narration.txt 末尾的「区块聚焦映射」注释
- 使用 `SlideRenderer.parse_block_focus_mapping()` 解析为结构化数据
- 每条映射 = 一张 PNG（seg → slide + focus）

4-B. 编写 Python 渲染脚本 `$PROJECT_DIR/generate_ppt.py`，调用 `slide_renderer.py`：

```python
import sys, os
sys.path.insert(0, os.path.expanduser("~/.claude/skills/article-to-video/scripts"))
from slide_renderer import SlideRenderer

PROJECT = os.path.dirname(os.path.abspath(__file__))
renderer = SlideRenderer(output_dir=os.path.join(PROJECT, "slides"))

# 读取字幕（从 narration.txt 按 === 分割）
with open(os.path.join(PROJECT, "narration.txt"), "r") as f:
    content = f.read().split("# 幻灯片映射")[0]  # 去掉尾部注释
SUBTITLES = [s.strip() for s in content.strip().split("===") if s.strip()]

# 解析区块聚焦映射
mappings = SlideRenderer.parse_block_focus_mapping(
    os.path.join(PROJECT, "narration.txt"))

# 封面
renderer.render_cover(
    title="文章标题",
    subtitle="副标题",
    source="来源",
    seg_index=0,
    subtitle_text=SUBTITLES[0],
)

# 内容页：遍历映射，按 slide 分组渲染
for m in mappings:
    if m["focus"] == "none" and m["slide"] == 1:
        continue  # 封面已处理
    # focus 转 index
    focus = m["focus"]
    if focus == "none":
        focus_index = -1
    elif focus == "all":
        focus_index = 999
    else:
        focus_index = int(focus.split("_")[1]) - 1  # block_1 → 0

    renderer.render_block_slide(
        title=m["title"],
        blocks=[{"title": b, "desc": "从文章提取的描述..."} for b in m["blocks"]],
        accent_color=renderer.colors.BLUE,  # 按主题选色
        focus_index=focus_index,
        seg_index=m["seg"],
        subtitle_text=SUBTITLES[m["seg"]],
    )

# 结尾
renderer.render_closing(
    title="核心启示",
    quote="核心金句...",
    sub_text="次级文本",
    seg_index=len(SUBTITLES) - 1,
    subtitle_text=SUBTITLES[-1],
)
```

4-C. 运行脚本生成 PNG。

**区块高亮设计规范（Block Highlight）：**

| 属性       | 普通状态                  | 高亮状态（active）        |
|-----------|--------------------------|--------------------------|
| 卡片填充   | `(32, 38, 52)` CARD      | `(42, 48, 62)` CARD+10   |
| 标题颜色   | `(225, 225, 230)` OFF_WHITE | `(255, 255, 255)` WHITE |
| 描述颜色   | `(140, 140, 155)` DIM_TEXT  | `(180, 180, 195)` SOFT_WHITE |
| 边框       | 无                       | accent_color × 40%, 2px  |
| 左侧色条   | accent_color 100%         | 不变                     |

**色板：**
- BG: `(22, 26, 36)` | CARD: `(32, 38, 52)` | CARD_ACTIVE: `(42, 48, 62)`
- 强调色：蓝`(60,130,255)` 绿`(40,215,150)` 紫`(150,90,255)` 琥珀`(255,185,50)` 红`(255,80,80)` 青`(40,210,210)`
- 字幕区：底部60px，半透明黑底`(0,0,0,160)`，白字34pt居中

**字体尺寸：**
- 页面标题：52pt+
- 区块标题：34pt+
- 区块描述：26pt+
- 字幕：34pt

**绝对禁止：**
- 不用 focus_ring（双层高亮环太重）
- 不变暗非活跃卡片（所有卡片保持正常亮度）
- 不改变非活跃卡片大小/位置
- 不做渐进揭示（progressive reveal）— 所有区块始终可见
- 不手写 Pillow 代码 — 必须调用 `slide_renderer.py`
- 不使用文章原图（桌面图表在手机上文字太小）

### 步骤 5：合成视频

调用 video-assemble skill：
- 输入：`slides_dir=$PROJECT_DIR/slides/`、`audio_dir=$PROJECT_DIR/audio/`、`output=$PROJECT_DIR/<文章标题>.mp4`
- 分辨率：`--resolution 1080x1920`
- 产出：`<文章标题>.mp4`（文件名使用步骤 1 提取的文章标题，去除文件系统不允许的字符如 `/`）

**映射规则（1:1）：**
- 每张幻灯片对应一段音频，映射为 `{"1":[1], "2":[2], ..., "N":[N]}`
- 无需复杂映射，因为步骤 4 已按音频段数生成幻灯片

### 步骤 6：输出总结

```
═══════════ 全流程完成 ═══════════

文章：<title>
项目目录：~/Desktop/workspace/videoGen/projects/<slug>/
视频：<文章标题>.mp4
时长：X 分 Y 秒
大小：N MB
视觉设计：K 张（画面切换 K 次）
音频段：N 段（字幕变化 N 次）

目录结构：
  <slug>/
  ├── narration.txt
  ├── generate_ppt.py
  ├── <文章标题>.mp4
  ├── audio/   (N 个 mp3)
  ├── slides/  (N 个 png，K 种视觉)
  └── images/  (M 个 png)
```

## 容错

- 文章抓取 403 → 降级为 curl + browser headers
- TTS 凭据未设置 → 提示用户设置后继续
- 单段 TTS 失败 → 重试 3 次（脚本内置）
- ffmpeg 失败 → 输出 stderr 供排查
- PPT 渲染中文引号语法错误 → 改用单引号包裹或替换为 `「」`
