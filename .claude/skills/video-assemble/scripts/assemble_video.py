#!/usr/bin/env python3
"""
通用视频合成脚本：幻灯片 PNG + 分段音频 → MP4 视频

用法:
  python3 assemble_video.py \
    --slides-dir /path/to/slides \
    --audio-dir /path/to/audio \
    --output /path/to/output.mp4 \
    --mapping '{"1":[1],"2":[2,3,4],...}'

mapping 格式: JSON 对象，key 为幻灯片编号（字符串），value 为音频段编号数组
"""

import argparse
import json
import os
import subprocess
from pydub import AudioSegment


def main():
    parser = argparse.ArgumentParser(description="幻灯片+音频合成视频")
    parser.add_argument("--slides-dir", required=True, help="幻灯片 PNG 目录")
    parser.add_argument("--audio-dir", required=True, help="音频段目录 (seg_01.mp3 ...)")
    parser.add_argument("--output", required=True, help="输出视频路径 (.mp4)")
    parser.add_argument("--mapping", required=True, help="JSON: 幻灯片→音频段映射")
    parser.add_argument("--resolution", default="1920:1080", help="视频分辨率")
    parser.add_argument("--cover-silence", type=float, default=0, help="封面前静默秒数")
    args = parser.parse_args()

    mapping = json.loads(args.mapping)
    # Normalize keys to int
    slide_audio_map = {int(k): v for k, v in mapping.items()}
    total_slides = max(slide_audio_map.keys())

    # 1. Get audio durations
    print("=" * 60)
    print("1/3  分析音频时长...")
    print("=" * 60)

    all_seg_ids = set()
    for segs in slide_audio_map.values():
        all_seg_ids.update(segs)

    audio_durations = {}
    for seg_id in sorted(all_seg_ids):
        path = os.path.join(args.audio_dir, f"seg_{seg_id:02d}.mp3")
        audio = AudioSegment.from_mp3(path)
        audio_durations[seg_id] = len(audio) / 1000.0

    slide_durations = {}
    for slide_idx in range(1, total_slides + 1):
        segs = slide_audio_map.get(slide_idx, [])
        if not segs and args.cover_silence > 0:
            dur = args.cover_silence
        else:
            dur = sum(audio_durations.get(s, 0) for s in segs)
        slide_durations[slide_idx] = dur
        seg_str = " + ".join(f"seg_{s:02d}({audio_durations[s]:.1f}s)" for s in segs) if segs else f"(静默 {dur:.1f}s)"
        print(f"  Slide {slide_idx:2d}: {dur:6.2f}s  <- {seg_str}")

    total = sum(slide_durations.values())
    print(f"\n  总时长: {total:.1f}s ({total/60:.1f}min)")

    # 2. Combine audio
    print(f"\n{'=' * 60}")
    print("2/3  合并音频...")
    print("=" * 60)

    combined = AudioSegment.empty()
    if args.cover_silence > 0 and not slide_audio_map.get(1, []):
        combined += AudioSegment.silent(duration=int(args.cover_silence * 1000))

    ordered_segs = []
    for slide_idx in range(1, total_slides + 1):
        ordered_segs.extend(slide_audio_map.get(slide_idx, []))

    for seg_id in ordered_segs:
        path = os.path.join(args.audio_dir, f"seg_{seg_id:02d}.mp3")
        combined += AudioSegment.from_mp3(path)

    output_dir = os.path.dirname(args.output) or "."
    combined_path = os.path.join(output_dir, "combined_audio_tmp.mp3")
    combined.export(combined_path, format="mp3", bitrate="192k")
    print(f"  -> {combined_path} ({len(combined)/1000:.1f}s)")

    # 3. ffmpeg
    print(f"\n{'=' * 60}")
    print("3/3  ffmpeg 合成视频...")
    print("=" * 60)

    concat_file = os.path.join(output_dir, "slides_concat_tmp.txt")
    with open(concat_file, "w") as fp:
        for slide_idx in range(1, total_slides + 1):
            img_path = os.path.join(args.slides_dir, f"slide_{slide_idx:02d}.png")
            dur = slide_durations[slide_idx]
            fp.write(f"file '{img_path}'\n")
            fp.write(f"duration {dur:.3f}\n")
        last = os.path.join(args.slides_dir, f"slide_{total_slides:02d}.png")
        fp.write(f"file '{last}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", concat_file,
        "-i", combined_path,
        "-vf", f"scale={args.resolution}:flags=lanczos,format=yuv420p",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart",
        args.output,
    ]

    print(f"  执行 ffmpeg...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    # Cleanup temp files
    os.remove(combined_path)
    os.remove(concat_file)

    if result.returncode == 0:
        size = os.path.getsize(args.output) / (1024 * 1024)
        print(f"\n  视频已生成: {args.output}")
        print(f"  文件大小: {size:.1f} MB")
    else:
        print(f"\n  ffmpeg 出错:")
        print(result.stderr[-2000:])
        return False

    print(f"\n{'=' * 60}")
    print("完成!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    main()
