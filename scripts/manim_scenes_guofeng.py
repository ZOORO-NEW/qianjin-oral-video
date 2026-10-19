"""国风水墨手绘场景 - 借鉴 srt-whiteboard-animation 的元素时序编排

与原白板场景的区别:
    纸   纯白 #FAFAFA          → 宣纸 #F1E6D0 + 淡墨晕 + 天头线
    笔   等宽矢量线            → 分段笔锋（起细-中粗-收尖，模拟毛笔）
    色   马克笔高饱和          → 墨 #241F1A / 朱 #A63A2B / 赭 #8C6B2F 三色
    编排 按段落整段播          → steps 数组，每个元素绑定一个绝对时间点

编排机制借鉴:
    srt-whiteboard-animation 用 annotation.json 的 startMs / sequence
    让每个元素绑定字幕事件出场。这里用 steps[].at 实现同一件事——
    at 对应某条字幕的开始时间，画面元素与旁白严格同步，未到时间的元素完全不可见。

用法（由 generate_video.py 通过 SCENE_PARAMS 驱动）:
    SCENE_PARAMS='{"duration":5,"steps":[...]}' python -m manim manim_scenes_guofeng.py GuofengScene
"""
import glob
import json
import os

from manim import (
    DOWN, LEFT, RIGHT, UP, AnimationGroup, Circle, Create, FadeIn, FadeOut,
    Group, ImageMobject, LaggedStart, Line, Rectangle, Scene, Text, VGroup, VMobject,
    Write, config,
)
from manim.constants import CapStyleType

INK = "#241F1A"
INK_LIGHT = "#5A5148"
PAPER = "#F1E6D0"
PAPER_DEEP = "#E3D4B8"
SEAL = "#A63A2B"
SEAL_DARK = "#8B2E22"
GOLD = "#8C6B2F"


def load_params():
    return json.loads(os.environ.get("SCENE_PARAMS", "{}"))


def sync_frame_to_aspect():
    """让构图比例跟随像素分辨率。

    Manim 的 -r 只改 pixel_width/pixel_height，config.frame_width 仍是
    16:9 的 14.22——竖屏输出会被上下黑边 letterbox，portrait 判断也会失效。
    这里按像素比反推 frame_width（frame_height 固定 8.0）。
    """
    pw, ph = config.pixel_width, config.pixel_height
    if not pw or not ph:
        return
    config.frame_height = 8.0
    config.frame_width = 8.0 * pw / ph


sync_frame_to_aspect()


def _debug_frame(tag=""):
    """把实际 frame 参数落盘，便于排查 letterbox 问题。"""
    try:
        p = os.environ.get("GF_DEBUG")
        if not p:
            return
        with open(p, "a", encoding="utf-8") as f:
            f.write("%s frame=%.3fx%.3f pixel=%dx%d\n" % (
                tag, config.frame_width, config.frame_height,
                config.pixel_width, config.pixel_height))
    except Exception:
        pass


def brush_stroke(start, end, w_max=13, w_min=2.5, bow=0.16):
    """毛笔笔锋：起笔细 → 中段粗 → 收笔尖。

    Manim 的 stroke 是等宽的，单条线画不出笔锋。
    这里用三段不同线宽的 VMobject 首尾相接，视觉上近似提按。
    弧度量 bow 让线条略带行笔的弧，不呆板。
    """
    import numpy as np
    s = np.array([start[0], start[1], 0.0])
    e = np.array([end[0], end[1], 0.0])
    mid = (s + e) / 2 + np.array([0, bow, 0])
    q1 = (s + mid) / 2
    q2 = (mid + e) / 2
    widths = (w_min, w_max * 0.72, w_max, w_max * 0.62, w_min)
    pts = [s, q1, mid, q2, e]
    seg = VGroup()
    for i in range(4):
        ln = Line(pts[i], pts[i + 1], stroke_color=INK,
                  stroke_width=widths[i], stroke_opacity=0.92)
        ln.set_cap_style(CapStyleType.ROUND)
        seg.add(ln)
    return seg


class GuofengScene(Scene):
    """通用国风场景：按 steps 的绝对时间点逐个揭示元素。"""

    def setup(self):
        self.p = load_params()
        _debug_frame("setup")
        self.FH = config.frame_height
        self.FW = config.frame_width
        self.portrait = self.FH > self.FW

    # ── 时间对齐：等场景时钟走到指定秒再播 ──
    def _sync(self, at):
        try:
            gap = at - self.renderer.time
        except Exception:
            gap = 0
        if gap > 0.02:
            self.wait(gap)

    # ── 纸：宣纸底 + 淡墨晕 + 天头线 ──
    def make_paper(self):
        paper = Rectangle(width=self.FW, height=self.FH,
                          fill_color=PAPER, fill_opacity=1, stroke_width=0)
        # 淡墨晕：几团极低透明度的赭色圆，模仿纸面墨气
        pools = VGroup()
        for (dx, dy, r, op) in [
            (-self.FW * 0.30, self.FH * 0.34, self.FH * 0.30, 0.05),
            (self.FW * 0.34, self.FH * 0.10, self.FH * 0.26, 0.04),
            (-self.FW * 0.10, -self.FH * 0.42, self.FH * 0.34, 0.035),
        ]:
            pools.add(Circle(radius=r, fill_color=PAPER_DEEP, fill_opacity=op,
                             stroke_width=0).move_to([dx, dy, 0]))
        # 天头细线（书页界栏）
        head = Line(LEFT * self.FW * 0.40 + UP * self.FH * 0.445,
                    RIGHT * self.FW * 0.40 + UP * self.FH * 0.445,
                    stroke_color=INK_LIGHT, stroke_width=1.2, stroke_opacity=0.45)
        head2 = Line(LEFT * self.FW * 0.40 + UP * self.FH * 0.432,
                     RIGHT * self.FW * 0.40 + UP * self.FH * 0.432,
                     stroke_color=INK_LIGHT, stroke_width=0.6, stroke_opacity=0.22)
        return VGroup(paper, pools, head, head2)

    # ── 竖排章名 ──
    def make_chap(self, text, size=None):
        size = size or (46 if self.portrait else 44)
        chars = VGroup(*[Text(c, font="KaiTi", font_size=size, color=INK)
                         for c in text])
        chars.arrange(DOWN, buff=size * 0.0022)
        return chars

    # ── 朱印 ──
    def make_seal(self, text, side=None):
        side = side or self.FH * 0.085
        box = Rectangle(width=side, height=side, fill_color=SEAL,
                        fill_opacity=0.88, stroke_color=SEAL_DARK, stroke_width=2.5)
        char = Text(text, font="KaiTi", font_size=side * 58, color=PAPER)
        return VGroup(box, char)

    # ── steps 各元素处理器 ──
    def step_figure(self, st):
        """白描线稿逐笔生长（本场景的主体，不是文字）。

        Manim 的 ImageMobject 不能局部遮罩，没法做真正的"描线"。
        折中：预处理把整幅线稿切成 N 条横带（lineart_prep.py），
        这里按序 FadeIn，前沿自上而下推进 —— 视觉上就是一笔从
        纸顶扫到纸底，把人物一点点勾出来。
        """
        name = st["src"]
        d = self.p.get("fig_dir") or ""
        files = sorted(glob.glob(os.path.join(d, "strips", name + "_*.png")))
        if not files:
            return
        strips = [ImageMobject(f) for f in files]
        # 缩放：先按像素比例整体缩放到目标高度，保证条带之间严丝合缝
        total = sum(s.height for s in strips)
        if total <= 0:
            return
        k = float(st.get("h", 5.0)) / total
        for s in strips:
            s.scale(k)
        max_w = self.FW * float(st.get("maxw") or 0.86)
        if strips[0].width > max_w > 0:
            f = max_w / strips[0].width
            for s in strips:
                s.scale(f)
        # 自上而下堆叠
        y = strips[0].height * len(strips) / 2.0
        for s in strips:
            s.move_to([0, y - s.height / 2.0, 0])
            y -= s.height
        Group(*strips).move_to([
            self.FW * float(st.get("x", -0.05)),
            self.FH * float(st.get("y", 0.1125)), 0])
        self.play(
            LaggedStart(*[FadeIn(s) for s in strips], lag_ratio=0.55),
            run_time=float(st.get("dur", 1.5)))

    def step_chap(self, st):
        """右上角竖排章名，逐字落下。位置要让开中上部的线稿。"""
        g = self.make_chap(st["text"])
        g.align_to(UP * self.FH * 0.4125, UP)
        g.shift(RIGHT * self.FW * (0.365 if self.portrait else 0.40))
        self.play(LaggedStart(*[FadeIn(c, shift=DOWN * 0.10) for c in g],
                              lag_ratio=0.30, run_time=st.get("dur", 1.3)))

    def _fit(self, mob, ratio=0.86):
        """按可用宽度自动缩字号，防止长句超出画幅（竖屏尤其容易）。"""
        max_w = self.FW * ratio
        if mob.width > max_w > 0:
            mob.scale(max_w / mob.width)
        return mob

    def step_title(self, st):
        """主标题：逐字手写。

        竖屏画幅只有 4.5 unit 宽，标题压在画面中下部，
        避免与右上角竖排章名叠字；超宽时自动缩到安全宽度。
        """
        size = st.get("size") or (64 if self.portrait else 92)
        t = Text(st["text"], font="KaiTi", font_size=size, color=INK)
        t.move_to(UP * (-self.FH * 0.29 if self.portrait else self.FH * 0.05))
        self._fit(t)
        self.play(Write(t, run_time=st.get("dur", 1.8)))

    def step_items(self, st):
        """条目：笔锋线与文字同步出现（线不再单独抢占时间）。"""
        items = [x for x in st["text"].split("|") if x]
        size = st.get("size") or (42 if self.portrait else 40)
        rows = VGroup()
        for it in items:
            label = Text(it, font="KaiTi", font_size=size, color=INK)
            w = label.width + 0.26
            ln = brush_stroke((-w / 2, -0.30), (w / 2, -0.30), w_max=7, w_min=1.4)
            ln.move_to(label.get_center() + DOWN * (label.height * 0.62))
            rows.add(VGroup(label, ln))
        if self.portrait and st.get("dir", "v") == "h":
            rows.arrange(RIGHT, buff=self.FW * 0.045)
        elif self.portrait:
            rows.arrange(DOWN, buff=self.FH * 0.030)
        else:
            rows.arrange(RIGHT, buff=self.FW * 0.035)
        y = float(st.get("y", -0.275 if self.portrait else -0.13))
        rows.move_to(UP * (self.FH * y))

        anims = [AnimationGroup(Create(g[1], run_time=0.45),
                                FadeIn(g[0], shift=UP * 0.06, run_time=0.45))
                 for g in rows]
        self.play(LaggedStart(*anims, lag_ratio=0.42,
                              run_time=st.get("dur", 2.0)))

    def step_quote(self, st):
        """名句：大字 + 左侧笔锋竖线。"""
        size = st.get("size") or (64 if self.portrait else 76)
        t = Text(st["text"], font="KaiTi", font_size=size, color=INK)
        t.move_to(DOWN * self.FH * 0.29)
        self._fit(t)
        bar = Line(LEFT * (t.width / 2 + 0.30) + UP * (t.height / 2),
                   LEFT * (t.width / 2 + 0.30) + DOWN * (t.height / 2),
                   stroke_color=GOLD, stroke_width=5, stroke_opacity=0.75)
        bar.set_cap_style(CapStyleType.ROUND)
        self.play(Create(bar, run_time=0.5),
                  Write(t, run_time=st.get("dur", 1.8)))

    def step_seal(self, st):
        """朱印落下：略大 → 回弹 → 定住。"""
        g = self.make_seal(st["text"])
        pos = st.get("pos")
        if pos == "br":
            g.to_corner(DOWN + RIGHT, buff=self.FH * 0.055)
            g.shift(LEFT * self.FW * 0.08 + UP * self.FH * 0.16)
        elif self.portrait:
            g.move_to([self.FW * 0.335, -self.FH * 0.145, 0])
        else:
            g.move_to(DOWN * self.FH * 0.245 + LEFT * self.FW * 0.30)
        self.play(FadeIn(g, scale=1.55, run_time=st.get("dur", 0.42)))

    def step_note(self, st):
        """小字注释。y 为正数表示向上偏移（占画幅高度比例）。"""
        size = st.get("size") or (30 if self.portrait else 26)
        t = Text(st["text"], font="KaiTi", font_size=size, color=INK_LIGHT)
        t.move_to(UP * (self.FH * float(st.get("y", -0.215))))
        self._fit(t, 0.92)
        self.play(FadeIn(t, shift=UP * 0.06, run_time=st.get("dur", 0.8)))

    def construct(self):
        self.add(self.make_paper())
        cur = 0.0
        for st in self.p.get("steps", []):
            at = float(st.get("at", cur))
            self._sync(at)
            handler = getattr(self, "step_" + st["k"], None)
            if handler:
                handler(st)
            try:
                cur = self.renderer.time
            except Exception:
                cur = at
        total = float(self.p.get("duration", 5.0))
        try:
            gap = total - self.renderer.time
        except Exception:
            gap = 0
        if gap > 0.02:
            self.wait(gap)


if __name__ == "__main__":
    print("scene: GuofengScene (params via SCENE_PARAMS)")
