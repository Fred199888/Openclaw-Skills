---
name: video-assemble
description: |
  将 PPT 幻灯片 PNG 和分段音频合成 MP4 视频。用于：
  (1) 已有 slide_01.png ... 和 seg_01.mp3 ...
  (2) 建立音频-幻灯片语义映射（卡点）
  (3) 合成视频，幻灯片随音频自动切换

  **触发场景：**
  - 已有幻灯片和音频，需要合成视频
  - article-to-video 编排器调用

  **前置条件：**
  - ffmpeg 已安装
  - pip install pydub
---

# video-assemble

## Instructions

1. 全程输出中文。
2. 接收参数：`slides_dir`（项目 `slides/`）、`audio_dir`（项目 `audio/`）、`output_path`（项目 `<文章标题>.mp4`）、`slide_audio_map`、`resolution`（默认 `1080x1920`）。

### 步骤 1：建立音频-幻灯片映射（最关键）

必须确保每段音频内容与对应幻灯片主题一致。

**当前采用 1:1 映射**（手机竖屏模式）：每张幻灯片对应一段音频，幻灯片在步骤 4 已按音频段数生成。

```python
# 1:1 映射（默认）
SLIDE_AUDIO_MAP = {
    "1": [1], "2": [2], "3": [3], ..., "N": [N]
}
```

如果映射未给定且无法使用 1:1，需自行分析：
1. 获取每段音频时长
2. 理解每段音频内容（读项目 `narration.txt`）
3. 理解每张幻灯片主题
4. 建立语义映射

**映射原则：**
- 所有音频段必须被映射，不能遗漏
- 顺序连续，不能跳跃或交叉

### 步骤 2：合成视频

运行 `scripts/assemble_video.py`：

```bash
python3 ~/.claude/skills/video-assemble/scripts/assemble_video.py \
  --slides-dir "<slides_dir>" \
  --audio-dir "<audio_dir>" \
  --output "<output_path>" \
  --mapping '<JSON>' \
  --resolution 1080x1920
```

**参数说明：**
- `--resolution`：默认 `1080x1920`（9:16 竖屏），横屏用 `1920x1080`
- `--output`：文件名使用文章标题（去除 `/` 等特殊字符）

或直接编写等效 Python 逻辑（pydub + ffmpeg concat demuxer）。

### 步骤 3：输出时长分布表

```
| 幻灯片 | 时长 | 内容 |
|--------|------|------|
| 1      | 14s  | 封面 |
| 2      | 38s  | ... |
```

### 输出

```
═══════════ video-assemble 完成 ═══════════
视频：<output_path>
时长：X 分 Y 秒
分辨率：1080x1920（竖屏）
大小：N MB
```
