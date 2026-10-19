"""国风手绘白板渲染：笔尖走哪儿，线稿就长到哪儿，手一直在画。

和上一版（切条带淡入）的根本区别：
    上一版  线稿自己一段段淡入，画面上没有手 —— 只是"出现"，不是"画"
    这一版  一只手握着笔在前沿移动，线稿只在笔走过的位置显现

关于节奏（第二版返工）：
    上一版用 24 行蛇形扫描，3.2 秒扫完 = 每秒换向 7 次，人眼读成高频抖动。
    这一版把"扫多少行"和"看起来像不像画"解耦 —— 揭示用**连续路径参数**
    （s∈[0,1]，沿左→右→右→左 递增），所以行数可以降到 5 也不露横带；
    软边按参数空间做，接缝处天然连续。换向降到约 1.4 次/秒，手是"划一笔"
    而不是"来回蹭"。
"""
import json
import math
import os
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEMO = os.path.join(ROOT, "assets", "handwhite")
FIG = os.path.join(DEMO, "lineart")
HAND = os.path.join(DEMO, "hand.png")
OUT = os.path.join(ROOT, "output", "hw")

# 字体跨平台兜底：优先楷体（国风），退到宋体/黑体，最后 Noto
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\simkai.ttf",
    r"C:\Windows\Fonts\STKAITI.TTF",
    r"C:\Windows\Fonts\simsun.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/Library/Fonts/Songti.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]


def pick_font():
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("找不到中文字体，请用 --font 指定楷体/宋体 ttc 路径")


FONT = next((p for p in FONT_CANDIDATES if os.path.exists(p)), None)

W, H = 720, 1280
INK = (0x24, 0x1F, 0x1A)
INK_LIGHT = (0x5A, 0x51, 0x48)
PAPER = (0xF1, 0xE6, 0xD0)
PAPER_DEEP = (0xE3, 0xD4, 0xB8)
SEAL = (0xA6, 0x3A, 0x2B)
SEAL_DARK = (0x8B, 0x2E, 0x22)
GOLD = (0x8C, 0x6B, 0x2F)

ROWS = 4               # 落笔趟数（不是扫描行）；越少手越稳
SKEW = 0.28            # 笔锋在带内的倾斜，让前沿是一条斜线而不是竖直刀口
FEATHER = 0.022        # 软边宽度（路径参数单位），换算成像素约 55
GHOST = 0.075           # 未落笔处先留一层淡稿：否则粗笔带会把线稿切成互不相连的碎片
PASS_TIME = 0.72       # 每趟基准耗时（秒）；长镜头上限为其 2 倍，手更慢

# 版面三分：图区 62~760 / 场景文字 780~980 / 烧录字幕 1030~1150（不能再压）
FIG_TOP, FIG_H = 55, 740
FIG_MAXW = 610
FIG_CX = 300

HAND_SCALE = 0.27
TIP_X, TIP_Y = 48, 103  # hand.png 里笔尖的像素坐标


# ────────────────────── 静态底 ──────────────────────
def make_paper():
    """宣纸底 + 三团淡墨晕 + 天头双线，整片只算一次。"""
    canvas = Image.new("RGB", (W, H), PAPER)
    arr = np.array(canvas).astype(np.float32)
    yy, xx = np.mgrid[0:H, 0:W]
    for (cx, cy, r, op) in [(W * 0.2, H * 0.22, H * 0.30, 0.30),
                            (W * 0.85, H * 0.40, H * 0.26, 0.24),
                            (W * 0.55, H * 0.92, H * 0.34, 0.20)]:
        d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / r
        m = np.clip(1 - d, 0, 1) ** 2 * op
        for i in range(3):
            arr[..., i] = arr[..., i] * (1 - m) + PAPER_DEEP[i] * m
    canvas = Image.fromarray(arr.astype("uint8"))
    d = ImageDraw.Draw(canvas)
    d.line([(int(W * 0.12), 70), (int(W * 0.88), 70)], fill=INK_LIGHT, width=1)
    d.line([(int(W * 0.12), 76), (int(W * 0.88), 76)], fill=(0x9A, 0x91, 0x85), width=1)
    return canvas


def load_figure(name):
    """线稿按"高度优先、宽度封顶"缩放，返回 (RGBA数组, alpha, 左上x, 左上y)。"""
    im = Image.open(os.path.join(FIG, name + ".png")).convert("RGBA")
    s = FIG_H / im.height
    if im.width * s > FIG_MAXW:
        s = FIG_MAXW / im.width
    im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))),
                   Image.LANCZOS)
    rgba = np.array(im)
    # 提一点线稿的中调，不然"墨"比"淡底稿"亮不了多少，画到哪儿看不出来
    a = (rgba[..., 3].astype(np.float32) / 255.0) ** 0.72 * 255.0
    rgba[..., 3] = a.astype(np.uint8)
    return rgba, a, \
        int(FIG_CX - im.width / 2), int(FIG_TOP + (FIG_H - im.height) / 2)


# ────────────────────── 落笔路径 ──────────────────────
def build_smap(h, w, rows=ROWS, skew=SKEW):
    """路径参数图：每个像素对应它在"左→右 / 右→左"序列里的位置 s∈[0,1]。

    因为 s 沿蛇形连续（行末右边缘 s=k/rows，下一行起点同样是 k/rows），
    前沿可以做很宽的软边而不露出横带接缝 —— 这正是能把手速降下来的原因。
    """
    yy = np.arange(h)[:, None].astype(np.float32)
    xx = np.arange(w)[None, :].astype(np.float32) / max(w - 1, 1)
    rh = h / rows
    k = np.clip((yy // rh).astype(np.int32), 0, rows - 1)
    u = (yy - k * rh) / max(rh, 1e-6)
    frac = xx + skew * (u - 0.5)
    frac = np.where(k % 2 == 0, frac, 1.0 - frac)
    return (k + np.clip(frac, 0.0, 1.0)) / rows


DWELL = 0.80   # 每趟里画的时间占比，剩下 20% 是抬笔换带（手会先停住再滑下去）


def stroke_state(t):
    """(揭示进度 p, 笔尖局部坐标)。

    一趟之内：前沿按 smoothstep 推进，手随笔尖；
    趟末 20%：前沿停在带尾，手先停半拍，再平滑滑到下一带中线 ——
    否则 y 会在带边界瞬跳一整带高度，屏幕上看就是手在抽。
    """
    span = 1.0 / ROWS
    if t <= 0:
        return 0.0, (0.0, 0.5 / ROWS)
    if t >= 1:
        last = (ROWS - 0.5) / ROWS
        return 1.0, (1.0 if (ROWS - 1) % 2 == 0 else 0.0, last)
    k = min(int(t / span), ROWS - 1)
    u = (t - k * span) / span
    if u <= DWELL:
        a = u / DWELL
        p = (k + a * a * (3 - 2 * a)) / ROWS
        xx = p * ROWS - k
        return p, (xx if k % 2 == 0 else 1 - xx, (k + 0.5) / ROWS)
    if k == ROWS - 1:
        return 1.0, (1.0 if k % 2 == 0 else 0.0, (k + 0.5) / ROWS)
    f = (u - DWELL) / (1 - DWELL)
    f = f * f * (3 - 2 * f)
    return (k + 1) / ROWS, (1.0 if k % 2 == 0 else 0.0, (k + 0.5 + f) / ROWS)


def reveal(canvas, fig_rgba, alpha, fx, fy, smap, p, pen):
    """只把 s <= p 的部分贴上去，软边收在前沿，返回笔尖画布坐标。"""
    if p <= 0:
        return None
    m = np.clip((p - smap) / FEATHER, 0.0, 1.0)
    out = fig_rgba.copy()
    # 淡底稿打底，笔过之处才上满墨 —— 全图始终连着，不会被笔带切碎
    out[..., 3] = (alpha * (GHOST + (1.0 - GHOST) * m)).astype(np.uint8)
    im = Image.fromarray(out, "RGBA")
    canvas.paste(im, (fx, fy), im)
    return fx + pen[0] * fig_rgba.shape[1], fy + pen[1] * fig_rgba.shape[0]


def draw_hand(canvas, pen_x, pen_y, t, alpha=255):
    """笔尖对齐到 (pen_x, pen_y)；只留极缓的呼吸浮动，不要高频抖。"""
    if alpha <= 0:
        return
    hand = _HAND
    s = HAND_SCALE
    hw, hh = int(hand.width * s), int(hand.height * s)
    im = hand.resize((hw, hh), Image.LANCZOS)
    if alpha < 255:
        a = im.getchannel("A").point(lambda v: int(v * alpha / 255))
        im.putalpha(a)
    wob = math.sin(t * 1.6) * 2.0
    canvas.paste(im, (int(pen_x - TIP_X * s), int(pen_y - TIP_Y * s + wob)), im)


_HAND = None


def load_hand():
    """手素材：裁切边（手臂末端/右侧）做 alpha 渐隐，否则屏幕上是一个直角方块。"""
    im = Image.open(HAND).convert("RGBA")
    a = np.array(im.getchannel("A")).astype(np.float32)
    h, w = a.shape
    fy, fx = int(h * 0.20), int(w * 0.12)
    ry = np.clip((h - np.arange(h)) / fy, 0.0, 1.0)[:, None]
    rx = np.clip((w - np.arange(w)) / fx, 0.0, 1.0)[None, :]
    a *= np.minimum(ry, rx)
    im.putalpha(Image.fromarray(a.astype(np.uint8)))
    return im


# ────────────────────── 文字 ──────────────────────
def _font(size):
    return ImageFont.truetype(FONT, size)


def text_chars(canvas, text, cx, cy, size, color, t, at, dur,
               vertical=False, line_h=None, spacing=None, halo=False):
    """逐字浮现（像跟着笔一笔笔写出来），t 为该元素的本地时间。"""
    if t < at:
        return
    p = min(1.0, (t - at) / max(dur, 0.01))
    n = len(text)
    f = _font(size)
    d = ImageDraw.Draw(canvas, "RGBA")
    if vertical:
        line_h = line_h or int(size * 1.12)
        x0, y0 = cx - size / 2, cy - n * line_h / 2
        for i, ch in enumerate(text):
            q = min(1.0, max(0.0, p * n - i))
            if q <= 0:
                continue
            d.text((x0, y0 + i * line_h - (1 - q) * 10), ch, font=f,
                   fill=color + (int(255 * q),),
                   **({"stroke_width": 4, "stroke_fill": PAPER + (int(230 * q),)}
                      if halo else {}))
    else:
        spacing = spacing or int(size * 0.12)
        widths = [_char_w(f, ch) for ch in text]
        total = sum(widths) + spacing * (n - 1)
        x = cx - total / 2
        for i, ch in enumerate(text):
            q = min(1.0, max(0.0, p * n - i))
            if q > 0:
                d.text((x, cy - size * 0.62 - (1 - q) * 12), ch,
                       font=f, fill=color + (int(255 * q),))
            x += widths[i] + spacing


def _char_w(f, ch):
    b = f.getbbox(ch)
    return b[2] - b[0]


def _quote_bar(canvas, text, cy, size, t, at):
    """名句左侧的金色笔锋竖线。"""
    if t < at:
        return
    f = _font(size)
    tw = sum(_char_w(f, c) for c in text) + int(size * 0.12) * (len(text) - 1)
    x = int(W / 2 - tw / 2 - size * 0.55)
    d = ImageDraw.Draw(canvas, "RGBA")
    d.line([(x, cy - size * 0.62), (x, cy + size * 0.42)],
           fill=GOLD + (190,), width=6)


def draw_seal(canvas, text, cx, cy, t, at, dur, side=104):
    if t < at:
        return
    p = min(1.0, (t - at) / max(dur, 0.01))
    sc = 1.45 - 0.45 * min(1.0, p * 1.8)
    s = int(side * sc)
    box = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(box)
    d.rectangle([0, 0, s - 1, s - 1], fill=SEAL + (int(225 * p),),
                outline=SEAL_DARK + (int(235 * p),), width=3)
    f = _font(int(s * 0.60))
    bb = f.getbbox(text)
    d.text(((s - (bb[2] - bb[0])) / 2 - bb[0], (s - (bb[3] - bb[1])) / 2 - bb[1]),
           text, font=f, fill=PAPER + (int(245 * p),))
    canvas.paste(box, (int(cx - s / 2), int(cy - s / 2)), box)


def draw_items(canvas, text, cx, cy, t, at, dur, size=52):
    """横排词组 + 毛笔锋线，逐项出现。"""
    if t < at:
        return
    items = text.split("|")
    p = min(1.0, (t - at) / max(dur, 0.01))
    f = _font(size)
    n = len(items)
    gap = int(size * 0.55)
    ws = [sum(_char_w(f, c) for c in it) for it in items]
    total = sum(ws) + gap * (n - 1)
    x = cx - total / 2
    d = ImageDraw.Draw(canvas, "RGBA")
    for i, it in enumerate(items):
        q = min(1.0, max(0.0, p * n - i))
        if q > 0:
            d.text((x, cy - size * 0.62 - (1 - q) * 12), it, font=f,
                   fill=INK + (int(255 * q),))
            lw = int(ws[i] * 0.92)
            ly = int(cy + size * 0.46)
            d.line([(x, ly), (x + lw, ly)], fill=INK + (int(150 * q),),
                   width=max(1, int(size * 0.10)))
        x += ws[i] + gap


# ────────────────────── 单幕渲染 ──────────────────────
def render_scene(idx, steps, dur, fps=30, pass_time=PASS_TIME):
    global _HAND
    paper = make_paper()
    _HAND = load_hand()

    fig_data, smaps = {}, {}
    for st in steps:
        if st["k"] == "figure" and st["src"] not in fig_data:
            fd = load_figure(st["src"])
            fig_data[st["src"]] = fd
            smaps[st["src"]] = build_smap(fd[0].shape[0], fd[0].shape[1])

    # 长镜头多给时间：手走得越慢越舒服，短镜头才用固定节奏
    draw_dur = min(max(dur * 0.72, 2.0), ROWS * pass_time * 2.0)
    path = os.path.join(OUT, "s%02d.mp4" % idx)
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", "%dx%d" % (W, H), "-r", str(fps), "-i", "-",
         "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p", path],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)

    frames = int(round(dur * fps))
    pen, fig_end = (W / 2, FIG_TOP), 0.0
    for fi in range(frames):
        t = fi / fps
        canvas = paper.copy()

        # 1) 线稿：只画到笔走过的位置
        for st in steps:
            if st["k"] != "figure":
                continue
            rgba, alpha, fx, fy = fig_data[st["src"]]
            at = st.get("at", 0)
            lp = min(1.0, max(0.0, (t - at) / draw_dur))
            p, pen_local = stroke_state(lp)
            pt = reveal(canvas, rgba, alpha, fx, fy, smaps[st["src"]],
                        p, pen_local)
            if pt:
                pen = pt
            fig_end = at + draw_dur

        # 2) 手盖在线稿上；画完 0.3s 淡出
        if t <= fig_end + 0.28:
            fa = 255 if t <= fig_end else int(255 * (1 - (t - fig_end) / 0.28))
            fa = min(fa, int(255 * min(1.0, t / 0.15)))   # 入场淡入，别硬切出手
            draw_hand(canvas, pen[0], pen[1], t, fa)

        # 3) 文字最后画：手和线稿都在它下面，字永远不会被挡住
        for st in steps:
            k = st["k"]
            if k == "figure":
                continue
            if k == "chap":
                # 章名列在手/线稿之上，加纸色描边，压到手背上也读得清
                text_chars(canvas, st["text"], st.get("cx", 660),
                           st.get("cy", 300), st.get("size", 62), INK, t,
                           st["at"], st.get("dur", 1.0), vertical=True,
                           halo=True)
            elif k in ("title", "quote"):
                text_chars(canvas, st["text"], W / 2, st.get("cy", 1010),
                           st.get("size", 100), INK, t, st["at"],
                           st.get("dur", 1.2))
                if k == "quote":
                    _quote_bar(canvas, st["text"], st.get("cy", 1010),
                               st.get("size", 100), t, st["at"])
            elif k == "note":
                text_chars(canvas, st["text"], W / 2, st.get("cy", 960),
                           st.get("size", 40), INK_LIGHT, t, st["at"],
                           st.get("dur", 0.8))
            elif k == "items":
                draw_items(canvas, st["text"], W / 2, st.get("cy", 1040), t,
                           st["at"], st.get("dur", 1.4), st.get("size", 52))
            elif k == "seal":
                draw_seal(canvas, st["text"], st.get("cx", 600),
                          st.get("cy", 826), t, st["at"], st.get("dur", 0.4))


        ff.stdin.write(canvas.tobytes())
    ff.stdin.close()
    ff.wait()
    return path


def main():
    import argparse

    ap = argparse.ArgumentParser(
        description="真·白板手绘渲染：手入镜、笔尖驱动线稿生长")
    ap.add_argument("--scenes", default=os.path.join(DEMO, "scenes_hw.json"),
                    help="场景 JSON（每幕 figure + 文字 steps）")
    ap.add_argument("--figs", default=None, help="线稿目录，默认 <skill>/lineart/ready")
    ap.add_argument("--hand", default=None, help="手的 PNG，默认 <skill>/hand/hand.png")
    ap.add_argument("--out", default=None, help="输出目录，默认 <skill>/hw")
    ap.add_argument("--font", default=None, help="中文字体 ttc/ttf 路径")
    ap.add_argument("--rows", type=int, default=None, help="落笔趟数，默认 4（≤5）")
    ap.add_argument("--pass-time", type=float, default=None, help="每趟基准耗时（秒）")
    ap.add_argument("--scale", type=float, default=None, help="手的缩放，默认 0.27")
    a = ap.parse_args()

    global FIG, HAND, OUT, FONT, ROWS, PASS_TIME, HAND_SCALE, _HAND
    if a.figs:
        FIG = a.figs
    if a.hand:
        HAND = a.hand
    if a.out:
        OUT = a.out
    if a.font:
        FONT = a.font
    elif not FONT:
        FONT = pick_font()
    if a.rows:
        ROWS = max(1, min(5, a.rows))
    if a.pass_time:
        PASS_TIME = a.pass_time
    if a.scale:
        HAND_SCALE = a.scale
    _HAND = None

    os.makedirs(OUT, exist_ok=True)
    with open(a.scenes, encoding="utf-8") as f:
        plan = json.load(f)
    for i, sc in enumerate(plan, 1):
        p = render_scene(i, sc["steps"], sc["dur"])
        print("✓", os.path.basename(p), flush=True)


if __name__ == "__main__":
    main()
