---
name: tts-gen
description: |
  使用火山引擎（豆包）TTS API 将解说词文本生成为分段 MP3 音频。用于：
  (1) 将 narration.txt（=== 分隔）转为 seg_01.mp3, seg_02.mp3 ...
  (2) 支持自定义音色、语速
  (3) 自动跳过已有音频，支持断点续传

  **触发场景：**
  - 已有解说词文件，需要生成语音
  - article-to-video 编排器调用
  - 用户要求文本转语音

  **前置条件：**
  - 环境变量 VOLCANO_APPID 和 VOLCANO_TOKEN 已设置
  - pip install requests
---

# tts-gen

## Instructions

1. 全程输出中文。
2. 接收参数：`narration_path`（解说词文件，通常为项目的 `narration.txt`）、`output_dir`（音频输出目录，通常为项目的 `audio/`）。

### 前置检查

```bash
echo "APPID=${VOLCANO_APPID:-(未设置)}" && echo "TOKEN=${VOLCANO_TOKEN:+(已设置)}"
```

如果未设置，提示用户设置后再执行。

### 执行 TTS

运行 `scripts/tts_generate.py`：

```bash
VOLCANO_APPID="$VOLCANO_APPID" VOLCANO_TOKEN="$VOLCANO_TOKEN" \
python3 ~/.claude/skills/tts-gen/scripts/tts_generate.py \
  --narration "<narration_path>" \
  --output-dir "<output_dir>" \
  --voice "zh_male_silang_mars_bigtts" \
  --speed 1.5
```

**可调参数：**
- `--voice`：默认 `zh_male_silang_mars_bigtts`
- `--speed`：默认 1.5x
- `--separator`：默认 `===`
- `--skip-existing`：默认开启，已存在的音频文件会跳过

**重新生成音频：** 如需重新生成某段音频，删除对应的 `seg_XX.mp3` 文件后重新运行即可。清除整个项目的音频：`rm -f <output_dir>/seg_*.mp3`

### 验证

生成后检查音频数量和总时长（用 pydub）。

### 输出

```
═══════════ tts-gen 完成 ═══════════
音频段数：N
总时长：X 分 Y 秒
目录：<output_dir>/
```
