"""字幕生成器 - 从口播脚本生成 SRT 字幕轨道。

v2 策略（默认）: 段落带 timestamps（edge-tts 词级时间戳）时，交给 srt_aligner
    做逐句对齐——每条字幕的起止精确到词，文本用旁白原文。
v1 策略（兜底）: 无时间戳时每段一条字幕，持续整个段落时长。

定位: 底部居中，白字+黑描边，字号与安全区由合成环节按分辨率自适应。

用法:
    # v2：带词级时间戳
    python subtitle_generator.py --segments manifest.json --output subs.srt
    # v1：只有段落与时间
    python subtitle_generator.py --segments segments.json --output subs.srt
"""
import argparse
import json
import os
import sys


def seconds_to_srt_time(seconds):
    """将秒转为SRT时间格式 HH:MM:SS,mmm。"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def generate_srt(segments, output_path):
    """生成 SRT 字幕。有词级时间戳则逐句对齐，否则退回单段策略。

    Args:
        segments: [{"id":1, "start_sec":0, "end_sec":3,
                    "subtitle":"要点", "oral_text":"原文",
                    "abs_start":0.0, "audio_dur":3.0,
                    "timestamps":[{text,offset_ms,duration_ms}, ...]}]
        output_path: SRT输出路径
    """
    # ── v2: 词级时间戳逐句对齐 ──
    if any(seg.get("timestamps") for seg in segments):
        try:
            from srt_aligner import build_srt_from_manifest
            manifest = []
            for i, seg in enumerate(segments):
                manifest.append({
                    "oral_text": seg.get("oral_text") or seg.get("subtitle", ""),
                    "abs_start": seg.get("abs_start", seg.get("start_sec", 0)),
                    "audio_dur": seg.get("audio_dur",
                                         seg.get("end_sec", 3) - seg.get("start_sec", 0)),
                    "timestamps": seg.get("timestamps", []),
                })
            srt_text, lines = build_srt_from_manifest(manifest)
            if lines and srt_text.strip():
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(srt_text)
                print(f"✓ 字幕已生成(逐句对齐): {output_path} ({len(lines)}条)")
                return
        except Exception as e:
            print(f"  ⚠ 逐句对齐失败，退回单段策略: {e}", file=sys.stderr)

    # ── v1: 单段一条（仅在无时间戳时使用） ──
    srt_entries = []
    idx = 1
    for seg in segments:
        subtitle = seg.get("oral_text") or seg.get("subtitle", "")
        if not subtitle:
            continue
        start = seg.get("start_sec", 0)
        end = seg.get("end_sec", start + 3)
        start = max(0, start + 0.1)
        end = end - 0.1
        if end <= start:
            end = start + 2
        srt_entries.append(
            f"{idx}\n"
            f"{seconds_to_srt_time(start)} --> {seconds_to_srt_time(end)}\n"
            f"{subtitle}\n\n"
        )
        idx += 1

    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(srt_entries)
    print(f"✓ 字幕已生成(单段策略): {output_path} ({len(srt_entries)}条)")


def main():
    parser = argparse.ArgumentParser(description="字幕生成器")
    parser.add_argument("--segments", required=True, help="分段JSON路径")
    parser.add_argument("--output", default="subtitles.srt", help="SRT输出路径")
    args = parser.parse_args()

    with open(args.segments, "r", encoding="utf-8") as f:
        segs = json.load(f)
    generate_srt(segs, args.output)


if __name__ == "__main__":
    main()
