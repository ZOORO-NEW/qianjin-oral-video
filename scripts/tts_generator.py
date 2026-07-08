"""TTS配音生成器 - 用edge-tts将口播台词转为MP3并输出词级时间戳。

用法:
    python tts_generator.py --text "口播台词" --output out.mp3 --timestamps ts.json
    python tts_generator.py --segments segments.json --outdir ./audio/
"""
import argparse
import asyncio
import edge_tts
import json
import os
import sys


# 推荐声音列表
RECOMMENDED_VOICES = {
    "douyin": "zh-CN-YunxiNeural",      # 抖音：沉稳有磁性
    "channels": "zh-CN-YunxiNeural",    # 视频号：同上
    "bilibili": "zh-CN-YunyangNeural",  # B站：专业播报
    "xiaohongshu": "zh-CN-XiaoxiaoNeural",  # 小红书：亲切女声
    "default": "zh-CN-YunxiNeural",
}


async def generate_one(text, voice, mp3_path, max_retries=5):
    """生成单段TTS音频+词级时间戳，带指数退避重试。

    Returns:
        list: 词级时间戳 [{text, offset_ms, duration_ms}, ...]
    """
    for attempt in range(max_retries):
        try:
            communicate = edge_tts.Communicate(
                text, voice, boundary="WordBoundary"
            )
            audio_chunks = []
            words = []
            async for event in communicate.stream():
                if event["type"] == "audio":
                    audio_chunks.append(event["data"])
                elif event["type"] == "WordBoundary":
                    words.append({
                        "text": event["text"],
                        "offset_ms": event["offset"] // 10000,  # 100ns→ms
                        "duration_ms": event["duration"] // 10000,
                    })
            # 写音频
            os.makedirs(os.path.dirname(mp3_path) or ".", exist_ok=True)
            with open(mp3_path, "wb") as f:
                f.write(b"".join(audio_chunks))
            return words
        except Exception as e:
            print(f"  [重试 {attempt+1}/{max_retries}] {e}", file=sys.stderr)
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # 1,2,4,8,16秒
            else:
                raise
    return None


def generate_batch(segments, outdir, voice="zh-CN-YunxiNeural"):
    """批量生成多段TTS。

    Args:
        segments: [{"id": 1, "oral_text": "..."}, ...]
        outdir: 输出目录
        voice: TTS声音
    Returns:
        list: [{"id":1, "mp3":"path", "timestamps":[...]}, ...]
    """
    os.makedirs(outdir, exist_ok=True)
    results = []

    async def run_all():
        for seg in segments:
            seg_id = seg.get("id", len(results) + 1)
            mp3_path = os.path.join(outdir, f"segment_{seg_id:02d}.mp3")
            ts_path = os.path.join(outdir, f"segment_{seg_id:02d}_ts.json")
            text = seg["oral_text"]
            print(f"  ▶ 生成第{seg_id}段配音: {text[:30]}...")
            words = await generate_one(text, voice, mp3_path)
            if words is None:
                print(f"  ✗ 第{seg_id}段生成失败", file=sys.stderr)
                continue
            with open(ts_path, "w", encoding="utf-8") as f:
                json.dump(words, f, ensure_ascii=False, indent=2)
            results.append({
                "id": seg_id,
                "mp3": mp3_path,
                "timestamps": words,
            })
            # 段间间隔，避免触发限流
            await asyncio.sleep(0.5)

    asyncio.run(run_all())
    return results


def main():
    parser = argparse.ArgumentParser(description="edge-tts配音生成器")
    parser.add_argument("--text", help="单段文本")
    parser.add_argument("--output", help="输出MP3路径")
    parser.add_argument("--timestamps", help="词级时间戳JSON输出路径")
    parser.add_argument("--segments", help="批量模式：segments.json路径")
    parser.add_argument("--outdir", default="./audio", help="批量模式：输出目录")
    parser.add_argument("--voice", default="zh-CN-YunxiNeural", help="TTS声音")
    parser.add_argument("--platform", help="根据平台自动选声音")
    args = parser.parse_args()

    if args.platform:
        args.voice = RECOMMENDED_VOICES.get(args.platform, RECOMMENDED_VOICES["default"])

    if args.segments:
        with open(args.segments, "r", encoding="utf-8") as f:
            segs = json.load(f)
        results = generate_batch(segs, args.outdir, args.voice)
        print(f"✓ 批量生成完成: {len(results)}段")
        # 输出汇总JSON
        summary_path = os.path.join(args.outdir, "tts_summary.json")
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
    elif args.text and args.output:
        async def run():
            words = await generate_one(args.text, args.voice, args.output)
            if args.timestamps and words:
                with open(args.timestamps, "w", encoding="utf-8") as f:
                    json.dump(words, f, ensure_ascii=False, indent=2)
            return words
        words = asyncio.run(run())
        if words:
            print(f"✓ 生成完成: {args.output} ({len(words)}词)")
        else:
            print("✗ 生成失败", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
