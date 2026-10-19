"""词级时间戳字幕对齐器 - v2 核心引擎

问题背景:
    v1 的 subtitle_generator.py 策略是「每段挂一条字幕要点，持续整个段落时长」。
    一段 20 秒的旁白屏幕上只有一句摘要，而声音在讲十几句话 —— 字幕与语音完全对不上。
    而 tts_generator.py 明明已经产出了 edge-tts 的 WordBoundary 词级时间戳，只是没人用。

本模块解决三件事:
    1. 时间对齐: 每条字幕的起止 = 首词的 offset 到 末词的 offset+duration，误差在单字级
    2. 文本正确: 字幕用旁白原文（oral_text）的片段，不是摘要要点
    3. 断句合理: 优先在标点处断，其次在词边界断，不切断词、不留孤字

核心算法:
    edge-tts 返回的 WordBoundary 不含标点，所以先做「词流 ↔ 原文」对齐，
    回填每个词在原文里的字符位置，再据此切分，这样切出来的字幕自带原标点。

用法:
    # 单独测试
    python srt_aligner.py --manifest segs.json --output out.srt
    # 作为库调用（generate_video.py 用）
    from srt_aligner import build_srt_from_manifest
    srt = build_srt_from_manifest(segments)
"""
import argparse
import json
import os
import re

# ---- 断句参数（竖屏 1080x1920 实测）----
MAX_CHARS = 16      # 单条字幕显示宽度上限（中文按 1，英文数字按 0.55）
PREF_CHARS = 13     # 达到此宽度后，遇到标点就断
MIN_CHARS = 4       # 小于此宽度不单独成条（避免一闪而过）
MAX_DUR = 4.2       # 单条最长停留秒数，超时必须切
MIN_DUR = 0.85      # 单条最短停留秒数，不足则向后延展
GAP_MS = 40         # 相邻两条之间的空隙，避免叠字

STRONG_PUNCT = "。！？；…!?;"
WEAK_PUNCT = "，、：—～,:" + "“”‘’「」（）()《》"
PAUSE_TAIL = "的了着地得吗呢吧啊呀哦嘛"   # 不宜作为下一条开头（会读成孤字）


def seconds_to_srt_time(seconds):
    """秒 → SRT 时间格式 HH:MM:SS,mmm。负数按 0 处理。"""
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms >= 1000:
        ms = 999
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def vlen(text):
    """视觉宽度：中日韩字符记 1，其他记 0.55。"""
    w = 0.0
    for ch in text:
        w += 1.0 if ord(ch) > 0x2E80 else 0.55
    return w


def _is_word_char(ch):
    """是否为正文用字（非标点、非空白）。"""
    if ch.isspace():
        return False
    if ch in STRONG_PUNCT or ch in WEAK_PUNCT:
        return False
    if ch in "，。！？；：、（）【】《》…—～·\"'":
        return False
    return True


def align_words_to_text(oral_text, words):
    """把 TTS 词流对齐回原文，得到每个词在原文里的字符区间。

    edge-tts 的 WordBoundary 不返回标点，且偶尔与原文有读法差异
    （数字读成中文、多音字、"一"的变调）。这里用贪心匹配逐个定位，
    匹配失败时跳过该字符而不是整体失败。

    Returns:
        spans: [(start_char, end_char), ...] 与 words 等长
        match_ratio: 匹配到的正文字符占原文正文字符的比例
    """
    spans = []
    pos = 0
    n = len(oral_text)
    matched = 0
    total = sum(1 for ch in oral_text if _is_word_char(ch))

    for w in words:
        target = (w.get("text") or "").strip()
        if not target:
            spans.append((pos, pos))
            continue
        start = None
        k = 0
        scan = pos
        while scan < n and k < len(target):
            ch = oral_text[scan]
            if not _is_word_char(ch):
                scan += 1
                continue
            if start is None:
                start = scan
            if ch == target[k]:
                k += 1
                matched += 1
                scan += 1
            else:
                # 读法差异：原文这字没被念到，跳过
                scan += 1
        if start is None:
            start = pos
        spans.append((start, scan))
        pos = scan

    ratio = (matched / total) if total else 1.0
    return spans, ratio


def find_break_points(oral_text, spans, words):
    """标记每个词之后是否有标点断点。

    Returns:
        {word_index: "strong"|"weak"}
    """
    breaks = {}
    for idx, (s, e) in enumerate(spans):
        if e <= s:
            continue
        # 看该词结束位置之后紧跟的标点
        tail = ""
        probe = e
        while probe < len(oral_text) and not _is_word_char(oral_text[probe]):
            if oral_text[probe] in STRONG_PUNCT:
                breaks[idx] = "strong"
                break
            if oral_text[probe] in WEAK_PUNCT and oral_text[probe].strip():
                tail = oral_text[probe]
            probe += 1
        else:
            if tail and idx not in breaks:
                breaks[idx] = "weak"
    return breaks


def _clean_slice(text):
    """去掉字幕片段首尾的空白与连接性标点，保留句中逗号顿号。"""
    text = text.strip()
    text = re.sub(r"^[，、。；：—～,.;:]+", "", text)
    text = re.sub(r"[，、；：—～,;:]+$", "", text)
    text = text.strip()
    return text


def split_one_segment(words, spans, oral_text, breaks):
    """把一个段落的词流切成若干条字幕。

    Returns:
        [{"text":..., "start_ms":..., "end_ms":...}, ...]  段内相对时间
    """
    n = len(words)
    if n == 0:
        return []

    def w_at(k):
        return words[k]

    def line_from(i, j):
        """取词区间 [i, j] 对应的原文片段与时间。"""
        start_char = spans[i][0]
        end_char = spans[j][1]
        raw = oral_text[start_char:end_char]
        text = _clean_slice(raw)
        if not text:
            text = "".join(w_at(k).get("text", "") for k in range(i, j + 1))
        start_ms = w_at(i)["offset_ms"]
        last = w_at(j)
        end_ms = last["offset_ms"] + last.get("duration_ms", 250)
        return {"text": text, "start_ms": start_ms, "end_ms": end_ms,
                "_i": i, "_j": j}

    lines = []
    i = 0
    while i < n:
        base = w_at(i)["offset_ms"]
        j = i
        chars = 0.0
        chosen = None
        while j < n:
            chars += vlen(w_at(j).get("text", ""))
            dur = (w_at(j)["offset_ms"] + w_at(j).get("duration_ms", 250) - base) / 1000.0
            kind = breaks.get(j)

            if chars >= MAX_CHARS or dur >= MAX_DUR:
                # 硬上限：回退到区间内最后一个合适的断点
                back = None
                for k in range(j, i, -1):
                    if breaks.get(k) and vlen("".join(
                            w_at(m).get("text", "") for m in range(i, k + 1))) >= MIN_CHARS:
                        back = k
                        break
                chosen = back if back is not None else j
                break

            if kind == "strong" and chars >= MIN_CHARS:
                chosen = j
                break
            if kind == "weak" and chars >= PREF_CHARS:
                chosen = j
                break
            j += 1

        if chosen is None:
            chosen = n - 1
        # 避免下一条以虚词开头（读起来像孤字）
        if chosen + 1 < n and chosen > i:
            nxt = w_at(chosen + 1).get("text", "")
            if nxt and nxt[0] in PAUSE_TAIL and vlen("".join(
                    w_at(m).get("text", "") for m in range(i, chosen + 2))) <= MAX_CHARS:
                chosen += 1
        lines.append(line_from(i, chosen))
        i = chosen + 1

    # 收尾处理：时间延展 + 相邻不重叠
    for idx, ln in enumerate(lines):
        ln["start_ms"] = max(0, ln["start_ms"] - 30)   # 略提前，观感更跟得上
        if ln["end_ms"] - ln["start_ms"] < MIN_DUR * 1000:
            hard_end = (lines[idx + 1]["start_ms"] - GAP_MS) if idx + 1 < len(lines) else ln["end_ms"] + 800
            ln["end_ms"] = max(ln["end_ms"], min(hard_end, ln["start_ms"] + MIN_DUR * 1000))
        if idx + 1 < len(lines):
            limit = lines[idx + 1]["start_ms"] - GAP_MS
            if ln["end_ms"] > limit:
                ln["end_ms"] = max(ln["start_ms"] + 300, limit)
    return lines


def align_one_segment(seg):
    """处理单个段落，返回绝对时间的字幕条列表。"""
    words = seg.get("timestamps") or []
    oral = (seg.get("oral_text") or "").strip()
    abs_start = float(seg.get("abs_start", 0.0))

    if not words:
        return [_fallback_line(seg, abs_start)]

    spans, ratio = align_words_to_text(oral, words)
    if ratio < 0.55:
        # 词流与原文差异过大（数字/英文被改写），退回纯词流切分
        spans = [(_i, _i) for _i in range(len(oral))]
        oral_use = "".join(w.get("text", "") for w in words)
        spans = [(k, k + len(w.get("text", ""))) for k, w in enumerate(words)]
        oral_use = "".join(w.get("text", "") for w in words)
        oral, spans = oral_use, _rebuild_spans(words)
        breaks = {}
    else:
        breaks = find_break_points(oral, spans, words)

    lines = split_one_segment(words, spans, oral, breaks)
    for ln in lines:
        ln["start"] = abs_start + ln.pop("start_ms") / 1000.0
        ln["end"] = abs_start + ln.pop("end_ms") / 1000.0
        ln.pop("_i", None)
        ln.pop("_j", None)
    return lines


def _rebuild_spans(words):
    """无原文可用时，用词自身长度构造伪字符区间。"""
    spans = []
    cur = 0
    for w in words:
        ln = len(w.get("text", ""))
        spans.append((cur, cur + max(1, ln)))
        cur += max(1, ln)
    return spans


def _fallback_line(seg, abs_start):
    """没有词级时间戳时的兜底：单段一条，用原文而非摘要。"""
    text = (seg.get("oral_text") or seg.get("subtitle") or "").strip()
    dur = float(seg.get("audio_dur") or 3.0)
    return {"text": text, "start": abs_start + 0.05, "end": abs_start + max(1.0, dur - 0.15)}


def build_srt_from_manifest(segments, max_chars=MAX_CHARS):
    """主入口：段落清单 → SRT 文本。

    Args:
        segments: [{
            "oral_text": 旁白原文,
            "abs_start": 该段在成片中的绝对起点(秒),
            "audio_dur": 该段实测音频时长(秒),
            "timestamps": [{text, offset_ms, duration_ms}, ...]  # edge-tts 词级
        }, ...]
    """
    global MAX_CHARS
    if max_chars:
        MAX_CHARS = max_chars

    all_lines = []
    for seg in segments:
        all_lines.extend(align_one_segment(seg))

    all_lines.sort(key=lambda x: x["start"])
    # 全局去重叠
    for i in range(len(all_lines) - 1):
        if all_lines[i]["end"] > all_lines[i + 1]["start"] - GAP_MS / 1000.0:
            all_lines[i]["end"] = max(all_lines[i]["start"] + 0.3,
                                      all_lines[i + 1]["start"] - GAP_MS / 1000.0)

    out = []
    for idx, ln in enumerate(all_lines, 1):
        if not ln["text"] or ln["end"] <= ln["start"]:
            continue
        out.append("%d\n%s --> %s\n%s\n" % (
            len(out) + 1,
            seconds_to_srt_time(ln["start"]),
            seconds_to_srt_time(ln["end"]),
            ln["text"]))
    return "\n".join(out), all_lines


def _ass_time(t):
    """秒 → ASS 时间 H:MM:SS.cc（厘秒）。"""
    if t < 0:
        t = 0
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    cs = int(round((t - int(t)) * 100))
    if cs >= 100:
        cs = 99
    return "%d:%02d:%02d.%02d" % (h, m, s, cs)


ASS_HEAD = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Guofeng,{font},{size},&H00FFFFFF,&H000000FF,&H00141414,&H64000000,0,0,0,0,100,100,1.2,0,1,{outline},1,2,{ml},{mr},{mv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _wrap_for_ass(text, per_line):
    """按字数手动折行，返回带 \\N 的 ASS 文本。

    必须自己做：libass 的中文换行按空格判断，中文没有空格，
    WrapStyle 形同虚设，长句会直接溢出画幅被裁掉（实测踩坑）。
    折行优先落在标点之后，否则居中均分，避免孤字成行。
    """
    if per_line < 4 or vlen(text) <= per_line:
        return text
    n = len(text)
    mid = (n + 1) // 2
    for d in range(0, min(5, mid)):
        for i in (mid - d, mid + d):
            if 0 < i < n and text[i - 1] in "，、。；：！？—":
                return text[:i] + "\\N" + text[i:]
    return text[:mid] + "\\N" + text[mid:]


def build_ass_from_manifest(segments, width, height, font_name="KaiTi",
                            font_ratio=0.0375, margin_v_ratio=0.105,
                            outline=3, max_chars=None):
    """生成 ASS 字幕（带明确 PlayRes，字号按真实像素计算）。

    必须走 ASS 而不能用 SRT + force_style：libass 在缺少 PlayRes 时
    按 384x288 解释 FontSize 与 MarginV，竖屏 720x1280 上字号会被
    放大约 4.4 倍、字幕被顶到画面顶部（实测踩坑）。

    Returns:
        (ass_text, lines)
    """
    _, lines = build_srt_from_manifest(segments, max_chars)
    size = max(22, int(height * font_ratio))
    mv = int(height * margin_v_ratio)
    mh = int(width * 0.083)
    head = ASS_HEAD.format(w=int(width), h=int(height), font=font_name,
                           size=size, outline=outline, ml=mh, mr=mh, mv=mv)
    body = []
    # 每行可容纳的字数：中文字宽约等于字号
    per_line = max(6, int((width - 2 * mh) / max(1, size)))
    for ln in lines:
        if not ln["text"] or ln["end"] <= ln["start"]:
            continue
        text = _wrap_for_ass(ln["text"].replace("\n", ""), per_line)
        body.append("Dialogue: 0,%s,%s,Guofeng,,0,0,0,,%s" % (
            _ass_time(ln["start"]), _ass_time(ln["end"]), text))
    return head + "\n".join(body) + "\n", lines


def load_timestamps(path):
    """读取 tts_generator.py 产出的 segment_XX_ts.json。"""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def main():
    parser = argparse.ArgumentParser(description="词级时间戳字幕对齐器 v2")
    parser.add_argument("--manifest", required=True, help="段落清单JSON")
    parser.add_argument("--output", default="aligned.srt", help="SRT输出路径")
    parser.add_argument("--max-chars", type=int, default=MAX_CHARS, help="单条宽度上限")
    parser.add_argument("--dump-lines", help="输出逐条明细JSON（调试用）")
    args = parser.parse_args()

    with open(args.manifest, "r", encoding="utf-8") as f:
        segs = json.load(f)

    srt, lines = build_srt_from_manifest(segs, args.max_chars)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(srt)

    print("✓ 字幕已生成: %s (%d条)" % (args.output, len(lines)))
    for ln in lines:
        print("  %6.2f → %6.2f  %s" % (ln["start"], ln["end"], ln["text"]))
    if args.dump_lines:
        with open(args.dump_lines, "w", encoding="utf-8") as f:
            json.dump(lines, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
