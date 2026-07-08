"""字幕生成器 - 从口播脚本字幕要点生成SRT字幕轨道。

字幕策略(v1): 每段显示该段的📝字幕要点，持续整个段落时长。
定位: 底部居中，白字+半透明黑底，确保跨平台可读。

用法:
    python subtitle_generator.py --segments segments.json --output subs.srt
"""
import argparse
import json
import os


def seconds_to_srt_time(seconds):
    """将秒转为SRT时间格式 HH:MM:SS,mmm。"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def generate_srt(segments, output_path):
    """从分段生成合并的SRT字幕。

    Args:
        segments: [{"id":1, "start_sec":0, "end_sec":3, "subtitle":"..."}, ...]
        output_path: SRT输出路径
    """
    srt_entries = []
    idx = 1
    for seg in segments:
        subtitle = seg.get("subtitle", "")
        if not subtitle:
            continue
        start = seg.get("start_sec", 0)
        end = seg.get("end_sec", start + 3)
        # 留0.2秒缓冲
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
    print(f"✓ 字幕已生成: {output_path} ({len(srt_entries)}条)")


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
