#!/usr/bin/env python3
"""
通用 TTS 语音生成脚本（火山引擎/豆包）

用法:
  VOLCANO_APPID="xxx" VOLCANO_TOKEN="yyy" python3 tts_generate.py \
    --narration /path/to/narration.txt \
    --output-dir /path/to/output/audio \
    [--voice zh_male_silang_mars_bigtts] \
    [--speed 1.5] \
    [--separator "==="]
"""

import argparse
import base64
import os
import sys
import time
import uuid
import requests
from pathlib import Path


def load_segments(narration_path, separator):
    with open(narration_path, "r", encoding="utf-8") as f:
        text = f.read()
    segments = []
    for s in text.split(separator):
        # 去掉以 # 开头的注释行
        lines = [l for l in s.strip().splitlines() if not l.strip().startswith("#")]
        clean = "\n".join(lines).strip()
        if clean:
            segments.append(clean)
    return segments


def main():
    parser = argparse.ArgumentParser(description="火山引擎 TTS 语音生成")
    parser.add_argument("--narration", required=True, help="解说词文件路径")
    parser.add_argument("--output-dir", required=True, help="音频输出目录")
    parser.add_argument("--voice", default="zh_male_silang_mars_bigtts", help="音色 ID")
    parser.add_argument("--speed", type=float, default=1.5, help="语速倍率")
    parser.add_argument("--separator", default="===", help="段落分隔符")
    parser.add_argument("--skip-existing", action="store_true", default=True, help="跳过已存在的文件")
    args = parser.parse_args()

    appid = os.environ.get("VOLCANO_APPID", "")
    token = os.environ.get("VOLCANO_TOKEN", "")
    voice = os.environ.get("VOLCANO_VOICE_TYPE", args.voice)

    if not appid or not token:
        print("错误: 请设置 VOLCANO_APPID 和 VOLCANO_TOKEN")
        print("  export VOLCANO_APPID='你的AppID'")
        print("  export VOLCANO_TOKEN='你的Token'")
        sys.exit(1)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    segments = load_segments(args.narration, args.separator)

    tts_url = "https://openspeech.bytedance.com/api/v1/tts"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer;{token}",
    }

    total = len(segments)
    print(f"共 {total} 段，音色: {voice}，语速: {args.speed}x\n")

    for i, text in enumerate(segments, 1):
        out_path = output_dir / f"seg_{i:02d}.mp3"

        if args.skip_existing and out_path.exists():
            print(f"  [跳过] seg_{i:02d}.mp3 已存在")
            continue

        print(f"  [{i:02d}/{total}] ({len(text)} 字) {text[:40]}...")

        payload = {
            "app": {"appid": appid, "token": "access_token", "cluster": "volcano_tts"},
            "user": {"uid": "video_gen_user"},
            "audio": {"voice_type": voice, "encoding": "mp3", "speed_ratio": args.speed},
            "request": {
                "reqid": str(uuid.uuid4()),
                "text": text,
                "text_type": "plain",
                "operation": "query",
            },
        }

        for attempt in range(3):
            try:
                resp = requests.post(tts_url, headers=headers, json=payload, timeout=30)
                resp.raise_for_status()
                result = resp.json()
                if result.get("code") != 3000:
                    raise RuntimeError(f"code={result.get('code')}, msg={result.get('message')}")
                audio_data = base64.b64decode(result["data"])
                with open(out_path, "wb") as f:
                    f.write(audio_data)
                print(f"         -> {len(audio_data)} bytes")
                break
            except Exception as e:
                print(f"         [重试 {attempt+1}/3] {e}")
                if attempt < 2:
                    time.sleep(3)
                else:
                    print(f"         [失败] seg_{i:02d} 生成失败")
                    sys.exit(1)

    print(f"\n✅ 语音生成完成! 文件在: {output_dir}")
    print(f"共 {total} 个音频文件")


if __name__ == "__main__":
    main()
