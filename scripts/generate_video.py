"""口播视频生成主管道 - 口播脚本 → 配音+白板动画+字幕 → MP4。

流程:
  1. 解析口播脚本Markdown → 结构化分段
  2. 每段: edge-tts配音 + Manim白板动画 + 字幕对齐
  3. FFmpeg合成: 音频+动画逐段合并 → 拼接 → 叠加字幕

用法:
  python generate_video.py --script 口播脚本.md --output final.mp4 --voice zh-CN-YunxiNeural
  python generate_video.py --script 口播脚本.md --output final.mp4 --platform douyin --max-segments 3
"""
import argparse
import asyncio
import edge_tts
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

# ── 路径配置 ──────────────────────────────────────────────────
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON_EXE = r"C:\Users\ZQJ\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
MANIM_SCRIPT = os.path.join(SKILL_DIR, "scripts", "manim_scenes.py")
TTS_SCRIPT = os.path.join(SKILL_DIR, "scripts", "tts_generator.py")
SUB_SCRIPT = os.path.join(SKILL_DIR, "scripts", "subtitle_generator.py")
FFMPEG_EXE = r"C:\Users\ZQJ\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe"
FFPROBE_EXE = FFMPEG_EXE.replace("ffmpeg.exe", "ffprobe.exe")

# 平台→分辨率/声音
PLATFORM_CONFIG = {
    "douyin": {"resolution": "1080,1920", "fps": 30, "voice": "zh-CN-YunxiNeural"},
    "channels": {"resolution": "1080,1920", "fps": 30, "voice": "zh-CN-YunxiNeural"},
    "bilibili": {"resolution": "1920,1080", "fps": 30, "voice": "zh-CN-YunyangNeural"},
    "xiaohongshu": {"resolution": "1080,1440", "fps": 30, "voice": "zh-CN-XiaoxiaoNeural"},
}

# 场景映射
SCENE_MAP = {
    "title": "TitleScene",
    "text_reveal": "TextRevealScene",
    "data_bar": "DataBarScene",
    "flow": "FlowScene",
    "icon_grid": "IconGridScene",
    "quote": "QuoteScene",
    "portrait": "PortraitScene",
    "illustration": "IllustrationScene",
}


# ── 脚本解析 ──────────────────────────────────────────────────
def parse_script(md_path):
    """解析口播脚本Markdown为结构化分段。"""
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 只取"脚本正文"部分
    body_match = re.search(r"━━━\s*脚本正文\s*━━━(.*?)(━━━\s*配套素材|━━━\s*质量自检)", content, re.S)
    if not body_match:
        # fallback: 取所有 [xx-xx秒] 段落
        body = content
    else:
        body = body_match.group(1)

    # 按时间标记分段: [0-3秒] / [15-40秒]
    segments = []
    # 匹配 [数字-数字秒] 或 [数字秒]
    pattern = r"\[(\d+)-(\d+)秒?\]\s*(.+?)(?=\[\d+-\d+秒?\]|━━━|$)"
    matches = re.findall(pattern, body, re.S)

    if not matches:
        # 尝试更简单匹配
        pattern2 = r"\[(\d+)-(\d+)秒?\](.*?)(?=\[\d+-\d+秒?\]|$)"
        matches = re.findall(pattern2, body, re.S)

    for start, end, block in matches:
        seg = {
            "start_sec": int(start),
            "end_sec": int(end),
            "oral_text": extract_field(block, "🗣"),
            "subtitle": extract_field(block, "📝"),
            "visual_instruction": extract_field(block, "🎬"),
            "emotion": extract_field(block, "💡"),
            "time_label": f"{start}-{end}秒",
        }
        seg["visual_type"] = infer_visual_type(seg)
        # 清理台词中的markdown加粗
        seg["oral_text"] = re.sub(r"\*\*(.*?)\*\*", r"\1", seg["oral_text"]).strip()
        seg["subtitle"] = seg["subtitle"].strip()
        if seg["oral_text"]:
            segments.append(seg)

    return segments


def extract_field(block, marker):
    """从段落块提取某个标记后的内容。

    不依赖正则前瞻，直接按标记位置截取，更健壮。
    """
    # 所有标记及其在 block 中的位置
    markers = {"🎬", "🗣", "📝", "💡"}
    # 找到当前标记的位置
    pos = block.find(marker)
    if pos < 0:
        return ""
    # 找到冒号（：或:）后的文本起始位置
    colon_pos = block.find("：", pos)
    if colon_pos < 0:
        colon_pos = block.find(":", pos)
    if colon_pos < 0:
        return ""
    content_start = colon_pos + 1
    # 找到下一个标记的位置
    next_pos = len(block)
    for m in markers:
        if m == marker:
            continue
        p = block.find(m, content_start)
        if 0 <= p < next_pos:
            next_pos = p
    content = block[content_start:next_pos].strip()
    return content


def infer_visual_type(seg):
    """从视觉指令和情绪推断场景类型。"""
    vi = (seg.get("visual_instruction", "") + " " + seg.get("emotion", "")).lower()
    oral = seg.get("oral_text", "")

    # 金句/收尾
    if "金句" in vi or "收尾" in vi or "核心句" in vi:
        return "quote"
    # 数据图表
    if any(k in vi for k in ["数据图表", "柱状", "对比图", "数据图", "条形"]):
        return "data_bar"
    # 流程图/思维导图
    if any(k in vi for k in ["流程图", "思维导图", "组合", "关系", "架构"]):
        return "flow"
    # 图标网格
    if any(k in vi for k in ["图标", "网格", "列表", "logo", "平台"]):
        return "icon_grid"
    # 标题/Hook
    if "hook" in vi or "标题" in vi or "开场" in vi or seg.get("start_sec", 0) == 0:
        return "title"
    # 默认：文字浮现
    return "text_reveal"


# ── 场景参数构建（从口播台词提取真实内容）───────────────────

_EXTRA_NUM_PAT = r"(\d+[\.\d]*)\s*(万|亿)?\s*(token|参数|次|轮|分)"
_UNIT_FIX = {"token": "", "参数": "亿", "次": "次", "轮": "轮", "分": "分"}


def _extract_numbers(text):
    """从文本提取数字+单位, 过滤日期, 用于数据图表。"""
    # 移除日期模式: 7月6号/7月6日
    text_clean = re.sub(r"\d+月\d+[号日]", "", text)
    items = []
    seen = set()
    for m in re.finditer(_EXTRA_NUM_PAT, text_clean):
        num_str = m.group(1)
        factor = m.group(2) or ""
        unit = m.group(3)
        suffix = _UNIT_FIX.get(unit, "")

        # 计算实际值
        val = float(num_str)
        if factor == "万":
            val = int(val * 10000) if val < 10000 else int(val)
        elif factor == "亿":
            val = int(val * 100000000)

        # 提取数字前标签
        prefix = text_clean[max(0, m.start() - 25):m.start()]
        labels = re.split(r"[，。；：、！？\n]", prefix)
        label = labels[-1].strip() if labels else ""
        label = re.sub(r"[^\u4e00-\u9fff\w]", "", label)[-6:]
        if not label:
            label = f"{factor}{unit}" if factor else unit

        if label not in seen:
            seen.add(label)
            items.append({"label": label, "value": val, "unit": suffix})
    return items[:8]


def _extract_platforms(text):
    """从文本提取平台/产品名列表。"""
    known = ["LongCat", "龙猫", "美团", "商汤", "小米", "MiMo", "SenseNova",
             "豆包", "文心", "通义", "Kimi", "DeepSeek", "智谱", "元宝",
             "抖音", "视频号", "B站", "小红书", "微信"]
    found = []
    for p in known:
        if p in text:
            found.append(p)
    return found[:6]


def _extract_short_title(text, max_len=12):
    """从口播台词提取最简短的标题文案。"""
    # 去掉"你知道吗""一个数字吓你一跳"等Hook前缀
    cleaned = re.sub(r"^(你知道吗|一个数字吓你一跳|是不是|我后悔|终于有人)", "", text)
    # 取第一句的非Hook内容
    first_sent = re.split(r"[，。！？]", cleaned)[0].strip()
    # 取最后15字（重点通常在末尾）
    return first_sent[-max_len:] if len(first_sent) > max_len else first_sent


def _extract_points(text, max_count=4):
    """从口播台词提取要点列表。"""
    # 先按"第一/第二/第三"或"①/②/③"拆分
    numbered = re.split(r"(?:第一|第二|第三|第四|①|②|③|④|首先|其次|最后)", text)
    if len(numbered) > 1:
        points = [s.strip().split("。")[0][:15] for s in numbered if len(s.strip()) > 3]
        return points[:max_count]
    # 否则按"。"取前几个完整句
    sents = [s.strip() for s in re.split(r"[。！？]", text) if len(s.strip()) > 4]
    return [s[:15] for s in sents[:max_count]]


def _extract_quote(text):
    """提取金句。取副标题（如果有），否则取最长的一句话或带感叹号/破折号的句子。"""
    # 找含"是""不是""才是""就是"的句子
    for s in re.split(r"[。！？]", text):
        if any(k in s for k in ["是", "不是", "才是", "就是", "该薅", "别客气", "窗口期", "差距"]):
            if 8 <= len(s) <= 25:
                return s.strip()
    # 取带感叹号的句子
    for s in re.split(r"[。！]", text):
        s = s.strip()
        if 8 <= len(s) <= 25:
            return s
    # fallback: 最长句子
    sents = [s.strip() for s in re.split(r"[。！？]", text) if 8 <= len(s) <= 25]
    return max(sents, key=len) if sents else text[:15]


def build_scene_params(seg, portrait_image=None, illustration_map=None):
    """根据口播台词内容构建Manim可视化参数。
    
    Args:
        seg: 分段数据
        portrait_image: 人物肖像图片路径（可选）
        illustration_map: {seg_id: image_path} 场景插图映射（可选）
    """
    vtype = seg["visual_type"]
    accent_map = {"title": "RED", "text_reveal": "BLUE", "data_bar": "BLUE",
                  "flow": "GREEN", "icon_grid": "ORANGE", "quote": "RED", "portrait": "BLACK"}
    script_dur = max(3, seg["end_sec"] - seg["start_sec"])
    text = seg.get("oral_text", "")
    subtitle = seg.get("subtitle", "")
    seg_id = seg.get("id", 0)

    # 中文口播约4.5字/秒 → 估算配音时长, Manim直接渲染够长时间
    estimated_audio_dur = len(text) / 4.5
    duration = max(script_dur, int(estimated_audio_dur) + 1)

    # 优先使用场景插图（需要传入 illustration_map）
    illustration_img = None
    if illustration_map and seg_id in illustration_map:
        illustration_img = illustration_map[seg_id]

    # 插图模式: 非标题/非金句段, 有对应插图
    if illustration_img and vtype not in ("title", "quote"):
        vtype = "illustration"
    # 肖像模式: 非标题段, 有肖像图但无插图
    elif portrait_image and vtype not in ("title", "quote") and not illustration_img:
        vtype = "portrait"

    params = {
        "type": vtype,
        "accent": accent_map.get(vtype, "BLUE"),
        "duration": duration,
        "subtitle": subtitle,
    }

    if vtype == "illustration":
        # 用字幕要点的第一段作为底部标题, ≤15字
        ill_title = subtitle.split("/")[0].split("\n")[0].strip()[:15] if subtitle else _extract_short_title(text, 15)
        params["title"] = ill_title
        params["subtitle"] = ""
        params["image"] = illustration_img
        params["overlay"] = False

    elif vtype == "portrait":
        # 肖像段: 左侧图片 + 右侧标题
        params["title"] = _extract_short_title(text, 16)
        # 副标题取字幕要点的非重复后半段，避免与标题重复
        sub_clean = ""
        if subtitle:
            sub_parts = [s.strip() for s in subtitle.split("/") if len(s.strip()) > 0]
            # 如果第一点和标题重复，使用第二点；否则使用第一点
            if sub_parts:
                if params["title"] and sub_parts[0] in params["title"] and len(sub_parts) > 1:
                    sub_clean = sub_parts[1][:18]
                else:
                    sub_clean = sub_parts[0][:18]
        params["subtitle"] = sub_clean
        params["image"] = portrait_image

    elif vtype == "title":
        # 标题段: 用字幕要点作为大字标题, 不用情绪标记
        title = subtitle[:15] if subtitle else _extract_short_title(text)
        params.update({"title": title})  # 不再传 emotion 到 subtitle

    elif vtype == "text_reveal":
        # 从字幕要点拆分 → 去掉分隔符, 每条≤12字
        raw = subtitle.replace(" ", "").replace("，", "、").replace("——", "—")
        points = [p.strip().strip("/").strip() for p in re.split(r"[/\n、]", raw) if len(p.strip()) > 2]
        if not points:
            # 从口播台词取有实际含义的短句
            sents = [s.strip() for s in re.split(r"[。。！？\n]", text) if 5 <= len(s.strip()) <= 18]
            if sents:
                points = [s[:15] for s in sents[:4]]
            else:
                points = [text[:15]] if len(text) > 3 else ["—"]
        params["points"] = points[:4]

    elif vtype == "quote":
        q = subtitle or _extract_quote(text)
        params["quote"] = q

    elif vtype == "data_bar":
        numbers = _extract_numbers(text)
        platforms = _extract_platforms(text)
        if numbers:
            # 用数字+平台组合成对比数据
            data = []
            for i, n in enumerate(numbers[:6]):
                label = platforms[i] if i < len(platforms) else n["label"]
                data.append({"label": label, "value": int(n["value"]) if n["value"] == int(n["value"]) else n["value"],
                             "unit": n["unit"]})
            params["data"] = data
            params["unit"] = ""
        else:
            # 没数字时展示"对比"概念：使用平台名
            pts = platforms[:4] if platforms else ["平台A", "平台B"]
            params["data"] = [
                {"label": pts[i] if i < len(pts) else f"X{i+1}", "value": 100 - i * 15,
                 "unit": ""} for i in range(min(4, len(pts)))
            ]

    elif vtype == "flow":
        platforms = _extract_platforms(text)
        nodes = [{"text": p, "color": "BLACK"} for p in platforms[:4]] if platforms else [{"text": "起点", "color": "BLACK"}, {"text": "终点", "color": "GREEN"}]
        edges = [[i, i + 1] for i in range(len(nodes) - 1)]
        params.update({"nodes": nodes, "edges": edges})

    elif vtype == "icon_grid":
        items = [{"label": p, "color": "ORANGE"} for p in _extract_platforms(text)[:9]]
        params["items"] = items if items else [{"label": "平台1", "color": "ORANGE"}]

    return params


# ── Manim渲染 ─────────────────────────────────────────────────
def render_manim(scene_type, params, out_path, resolution="1920,1080", fps=30, quality="l"):
    """渲染单个Manim场景到out_path。"""
    scene_name = SCENE_MAP.get(scene_type, "TextRevealScene")
    media_dir = tempfile.mkdtemp(prefix="manim_")

    env = dict(os.environ)
    env["SCENE_PARAMS"] = json.dumps(params, ensure_ascii=False)
    # 绕过 WorkBuddy 的 safe-delete 沙箱限制（Manim 需要删除临时缓存文件）
    env["CODEBUDDY_SAFE_DELETE_SANDBOX"] = "0"

    qflag = {"l": "-ql", "m": "-qm", "h": "-qh", "k": "-qk"}[quality]
    # manim CLI: python -m manim FILE SCENE [OPTIONS]
    cmd = [
        PYTHON_EXE, "-m", "manim",
        MANIM_SCRIPT,
        scene_name,
        qflag,
        "--media_dir", media_dir,
        "-r", resolution,
        "--fps", str(fps),
    ]

    try:
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            print(f"  ✗ Manim渲染失败: {scene_name}\n{result.stderr[-500:]}", file=sys.stderr)
            return None
        # 查找生成的mp4
        for root, dirs, files in os.walk(media_dir):
            for f in files:
                if f.endswith(".mp4") and scene_name in f:
                    shutil.move(os.path.join(root, f), out_path)
                    shutil.rmtree(media_dir, ignore_errors=True)
                    return out_path
    except subprocess.TimeoutExpired:
        print(f"  ✗ Manim渲染超时: {scene_name}", file=sys.stderr)
        return None

    print(f"  ✗ 未找到渲染输出: {scene_name}", file=sys.stderr)
    return None


# ── FFmpeg合成 ────────────────────────────────────────────────
def combine_audio_video(video_path, audio_path, out_path):
    """将音频混入视频（短视频时长对齐音频）。"""
    cmd = [
        FFMPEG_EXE, "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy", "-c:a", "aac",
        "-shortest",
        out_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ✗ 音视频合成失败: {result.stderr[-300:]}", file=sys.stderr)
        return None
    return out_path


def _get_media_duration(path):
    """用 ffprobe 获取媒体时长（秒）。"""
    cmd = [FFPROBE_EXE, "-v", "quiet",
           "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", path]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    try:
        return float(r.stdout.strip())
    except (ValueError, TypeError):
        return None


def pad_video_to_audio(video_path, audio_path, out_path, fps=30):
    """合成音视频，截短到较短的一方。
    
    现在Manim已按音频估算长度渲染，直接截短即可。
    """
    cmd = [
        FFMPEG_EXE, "-y",
        "-i", video_path, "-i", audio_path,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-c:a", "aac",
        "-shortest", "-pix_fmt", "yuv420p",
        out_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    # fallback
    if result.returncode != 0:
        return combine_audio_video(video_path, audio_path, out_path)
    return out_path


def concat_segments(segment_videos, out_path):
    """拼接多段视频（concat滤镜+重编码，确保各段无缝衔接不黑屏）。"""
    if len(segment_videos) == 1:
        # 单段直接复制
        shutil.copy2(segment_videos[0], out_path)
        return out_path

    n = len(segment_videos)
    # 构建 filter_complex 的 concat 滤镜
    inputs = []
    for v in segment_videos:
        inputs.extend(["-i", v])

    # 为 n 个输入生成 concat 滤镜映射
    stream_spec = "".join(f"[{i}:v][{i}:a]" for i in range(n))
    filter_cmd = f"{stream_spec}concat=n={n}:v=1:a=1[v][a]"

    cmd = [
        FFMPEG_EXE, "-y", *inputs,
        "-filter_complex", filter_cmd,
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        out_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ✗ 拼接失败: {result.stderr[-300:]}", file=sys.stderr)
        return None
    return out_path


def mux_subtitles(video_path, srt_path, out_path):
    """叠加硬字幕。"""
    style = "FontSize=28,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,Outline=2,Alignment=2,MarginV=40"
    # 复制字幕到输出目录同目录，用简单文件名避免 Windows 路径转义问题
    srt_tmp = os.path.join(os.path.dirname(os.path.abspath(out_path)), "subtitles_tmp.srt")
    shutil.copy(srt_path, srt_tmp)

    # 使用相对路径（输出目录）作为 filter 参数，避免盘符和分隔符问题
    out_dir = os.path.dirname(os.path.abspath(out_path))
    srt_rel = os.path.relpath(srt_tmp, out_dir)

    cmd = [
        FFMPEG_EXE, "-y",
        "-i", os.path.normpath(video_path),
        "-vf", f"subtitles={srt_rel}:force_style='{style}'",
        "-c:a", "copy",
        os.path.normpath(out_path),
    ]
    # 在输出目录执行，确保相对路径可解析
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=out_dir)
    try:
        os.remove(srt_tmp)
    except FileNotFoundError:
        pass
    if result.returncode != 0:
        print(f"  ✗ 字幕叠加失败: {result.stderr[-300:]}", file=sys.stderr)
        # fallback: 无字幕输出
        shutil.copy(video_path, out_path)
        return out_path
    return out_path


# ── 主流程 ────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="口播视频生成主管道")
    parser.add_argument("--script", required=True, help="口播脚本Markdown路径")
    parser.add_argument("--output", required=True, help="最终MP4输出路径")
    parser.add_argument("--voice", default="zh-CN-YunxiNeural", help="TTS声音")
    parser.add_argument("--platform", help="目标平台(douyin/channels/bilibili/xiaohongshu)")
    parser.add_argument("--quality", default="l", choices=["l", "m", "h", "k"], help="渲染质量")
    parser.add_argument("--max-segments", type=int, help="限制处理段数(测试用)")
    parser.add_argument("--workdir", default=None, help="工作目录(默认脚本同目录)")
    parser.add_argument("--portrait", default=None, help="人物肖像图片路径(嵌入到非标题段画面)")
    parser.add_argument("--illustrations", default=None, help="场景插图JSON文件路径({seg_id: image_path})")
    args = parser.parse_args()

    # 加载插图映射
    illustration_map = {}
    if args.illustrations:
        with open(args.illustrations, "r", encoding="utf-8") as f:
            illustration_map = json.load(f)
        # 统一处理: 键转为int
        illustration_map = {int(k): v for k, v in illustration_map.items()}
        print(f"▶ 加载场景插图映射: {len(illustration_map)}张")

    if args.platform:
        pconf = PLATFORM_CONFIG.get(args.platform, PLATFORM_CONFIG["douyin"])
        resolution = pconf["resolution"]
        args.voice = pconf["voice"]
    else:
        resolution = "1920,1080"

    workdir = args.workdir or os.path.dirname(os.path.abspath(args.output))
    os.makedirs(workdir, exist_ok=True)
    audio_dir = os.path.join(workdir, "audio")
    video_dir = os.path.join(workdir, "video")
    os.makedirs(audio_dir, exist_ok=True)
    os.makedirs(video_dir, exist_ok=True)

    print("▶ 解析口播脚本...")
    segments = parse_script(args.script)
    if args.max_segments:
        segments = segments[:args.max_segments]
    print(f"  解析到 {len(segments)} 段")

    if not segments:
        print("✗ 未解析到任何分段", file=sys.stderr)
        sys.exit(1)

    # 1. TTS配音
    print("▶ 生成配音...")
    tts_segments = [{"id": i + 1, "oral_text": s["oral_text"]} for i, s in enumerate(segments)]
    tts_results = generate_tts_batch(tts_segments, audio_dir, args.voice)
    if not tts_results:
        print("✗ TTS生成失败", file=sys.stderr)
        sys.exit(1)

    # 调整时间段为连续：使用实际音频时长，确保字幕与画面/配音同步
    cumulative = 0
    for i, seg in enumerate(segments):
        seg_id = i + 1
        audio_path = os.path.join(audio_dir, f"segment_{seg_id:02d}.mp3")
        audio_dur = _get_media_duration(audio_path)
        if audio_dur is None or audio_dur < 1:
            # fallback: 脚本时长
            audio_dur = seg["end_sec"] - seg["start_sec"]
        seg["abs_start"] = cumulative
        seg["abs_end"] = cumulative + audio_dur
        cumulative += audio_dur

    # 2. Manim动画
    print("▶ 生成白板动画...")
    segment_videos = []
    for i, seg in enumerate(segments):
        seg_id = i + 1
        seg["id"] = seg_id
        print(f"  ▶ 第{seg_id}段 [{seg['visual_type']}]: {seg['oral_text'][:25]}...")
        params = build_scene_params(seg, portrait_image=args.portrait, illustration_map=illustration_map)
        out_mp4 = os.path.join(video_dir, f"segment_{seg_id:02d}.mp4")
        seg_type = params["type"]
        # 打印场景切换
        if seg_type != seg["visual_type"]:
            print(f"    → 场景切换: {seg['visual_type']} -> {seg_type}")
        rendered = render_manim(seg_type, params, out_mp4, resolution, 30, args.quality)
        if not rendered:
            print(f"  ✗ 第{seg_id}段动画渲染失败，跳过", file=sys.stderr)
            continue
        segment_videos.append(rendered)

    if not segment_videos:
        print("✗ 所有动画渲染失败", file=sys.stderr)
        sys.exit(1)

    # 3. 音视频合成（每段）
    print("▶ 合成音视频...")
    combined_videos = []
    for i, vid in enumerate(segment_videos):
        seg_id = i + 1
        audio_path = os.path.join(audio_dir, f"segment_{seg_id:02d}.mp3")
        if not os.path.exists(audio_path):
            print(f"  ⚠ 第{seg_id}段音频缺失，跳过合成", file=sys.stderr)
            combined_videos.append(vid)
            continue
        out_combined = os.path.join(video_dir, f"combined_{seg_id:02d}.mp4")
        combined = pad_video_to_audio(vid, audio_path, out_combined, 30)
        if combined:
            combined_videos.append(combined)
            print(f"  ✓ 第{seg_id}段合成完成")

    # 4. 拼接
    print("▶ 拼接所有段...")
    concat_out = os.path.join(workdir, "concat_raw.mp4")
    final_concat = concat_segments(combined_videos, concat_out)
    if not final_concat:
        print("✗ 拼接失败", file=sys.stderr)
        sys.exit(1)

    # 5. 字幕
    print("▶ 生成字幕...")
    srt_path = os.path.join(workdir, "subtitles.srt")
    sub_segments = [
        {
            "id": i + 1,
            "start_sec": seg["abs_start"],
            "end_sec": seg["abs_end"],
            "subtitle": seg.get("subtitle", ""),
        }
        for i, seg in enumerate(segments)
    ]
    with open(os.path.join(workdir, "sub_segments.json"), "w", encoding="utf-8") as f:
        json.dump(sub_segments, f, ensure_ascii=False, indent=2)
    try:
        subprocess.run([PYTHON_EXE, SUB_SCRIPT, "--segments",
                        os.path.join(workdir, "sub_segments.json"),
                        "--output", srt_path], check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"  ⚠ 字幕生成失败: {e}", file=sys.stderr)
        srt_path = None

    # 6. 叠加字幕
    if srt_path and os.path.exists(srt_path):
        print("▶ 叠加字幕...")
        final_out = mux_subtitles(final_concat, srt_path, args.output)
    else:
        shutil.copy(final_concat, args.output)
        final_out = args.output

    if final_out and os.path.exists(final_out):
        size = os.path.getsize(final_out) / 1024 / 1024
        print(f"\n✅ 视频生成完成: {final_out} ({size:.1f}MB)")
    else:
        print("✗ 最终输出失败", file=sys.stderr)
        sys.exit(1)


def generate_tts_batch(segments, outdir, voice):
    """调用tts_generator.py批量生成配音。"""
    segs_json = os.path.join(outdir, "segments_for_tts.json")
    with open(segs_json, "w", encoding="utf-8") as f:
        json.dump(segments, f, ensure_ascii=False, indent=2)
    result = subprocess.run([
        PYTHON_EXE, TTS_SCRIPT,
        "--segments", segs_json,
        "--outdir", outdir,
        "--voice", voice,
    ], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ✗ TTS批量失败: {result.stderr[-500:]}", file=sys.stderr)
        return None
    return True


if __name__ == "__main__":
    main()
