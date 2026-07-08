"""Manim白板动画场景模板 - 简笔风口播视频画面。

场景类型(由口播脚本视觉指令映射):
  - TitleScene: 标题卡 (大字+下划线+背景块)
  - TextRevealScene: 关键词手写浮现
  - DataBarScene: 动态柱状图对比
  - FlowScene: 流程图/思维导图
  - IconGridScene: 平台图标网格
  - QuoteScene: 金句卡

参数通过环境变量 SCENE_PARAMS (JSON) 传入:
  {
    "type": "title",
    "title": "免费AI平台盘点",
    "subtitle": "窗口期过了就没了",
    "duration": 5,
    "accent": "RED"
  }
"""
import os
import json
from manim import *

# ── 白板风格常量 ──────────────────────────────────────────────
WHITEBOARD_BG = "#FAFAFA"
PEN_BLACK = "#1A1A1A"
PEN_BLUE = "#1F6FEB"
PEN_RED = "#E03131"
PEN_GREEN = "#2F9E44"
PEN_ORANGE = "#F08C00"

FONT_CN = "Noto Sans SC"
FONT_CN_BOLD = "simhei"

ACCENT_MAP = {
    "BLACK": PEN_BLACK, "BLUE": PEN_BLUE, "RED": PEN_RED,
    "GREEN": PEN_GREEN, "ORANGE": PEN_ORANGE,
}


def load_params():
    """从环境变量加载场景参数。"""
    raw = os.environ.get("SCENE_PARAMS", "{}")
    return json.loads(raw)


class WhiteboardScene(Scene):
    """白板场景基类 - 统一背景和风格。"""

    def setup(self):
        # 米白背景
        bg = Rectangle(
            width=config.frame_width,
            height=config.frame_height,
            fill_color=WHITEBOARD_BG,
            fill_opacity=1,
            stroke_width=0,
        )
        self.add(bg)


class TitleScene(WhiteboardScene):
    """标题卡: 大字标题 + 强调下划线 + 背景色块。"""

    def construct(self):
        p = load_params()
        title = p.get("title", "标题")
        subtitle = p.get("subtitle", "")
        accent = ACCENT_MAP.get(p.get("accent", "RED"), PEN_RED)
        duration = p.get("duration", 5)

        # 背景色块
        block = Rectangle(
            width=config.frame_width * 0.85,
            height=1.4,
            fill_color=accent,
            fill_opacity=0.12,
            stroke_width=0,
        )
        self.play(FadeIn(block, run_time=0.5))

        # 主标题
        title_txt = Text(
            title, font=FONT_CN_BOLD, font_size=64, color=PEN_BLACK
        )
        self.play(Write(title_txt, run_time=min(1.5, duration * 0.4)))

        # 下划线
        underline = Line(
            start=title_txt.get_left(),
            end=title_txt.get_right(),
            color=accent,
            stroke_width=6,
            cap_style=CapStyleType.ROUND,
        )
        self.play(Create(underline, run_time=0.5))

        # 副标题
        if subtitle:
            sub_txt = Text(
                subtitle, font=FONT_CN, font_size=36, color=PEN_BLACK
            ).next_to(title_txt, DOWN, buff=0.5)
            self.play(FadeIn(sub_txt, run_time=0.5))

        self.wait(max(0.5, duration - 2.5))


class TextRevealScene(WhiteboardScene):
    """关键词手写浮现 - 逐条出现。"""

    def construct(self):
        p = load_params()
        points = p.get("points", [])
        duration = p.get("duration", 5)
        if not points:
            self.wait(float(duration))
            return
        accent = ACCENT_MAP.get(p.get("accent", "BLUE"), PEN_BLUE)
        duration = p.get("duration", 5)

        items = VGroup()
        for i, pt in enumerate(points):
            # 圆点标记
            dot = Dot(color=accent, radius=0.12)
            txt = Text(pt, font=FONT_CN, font_size=40, color=PEN_BLACK)
            row = VGroup(dot, txt).arrange(RIGHT, buff=0.3, aligned_edge=LEFT)
            items.add(row)

        items.arrange(DOWN, buff=0.5, aligned_edge=LEFT)
        items.move_to(ORIGIN)

        # 逐条手写浮现
        per_item = min(1.2, (duration - 0.5) / max(1, len(points)))
        for i, row in enumerate(items):
            self.play(
                Create(row[0], run_time=0.3),
                Write(row[1], run_time=per_item),
            )
            if i < len(items) - 1:
                self.wait(0.2)

        self.wait(max(0.3, duration - len(points) * per_item - 0.5))


class DataBarScene(WhiteboardScene):
    """动态柱状图对比。"""

    def construct(self):
        p = load_params()
        data = p.get("data", [{"label": "A", "value": 50}, {"label": "B", "value": 100}])
        unit = p.get("unit", "")
        accent = ACCENT_MAP.get(p.get("accent", "BLUE"), PEN_BLUE)
        duration = p.get("duration", 5)

        # 坐标轴
        axes = Axes(
            x_range=[0, len(data), 1],
            y_range=[0, max(d["value"] for d in data) * 1.2, max(d["value"] for d in data) / 5],
            x_length=10,
            y_length=5,
            axis_config={"color": PEN_BLACK, "stroke_width": 2},
        ).move_to(ORIGIN)
        self.play(Create(axes, run_time=0.5))

        # 柱子
        bars = VGroup()
        labels = VGroup()
        values = VGroup()
        for i, d in enumerate(data):
            x = i + 0.5
            bar = Rectangle(
                width=0.8,
                height=axes.c2p(0, d["value"])[1] - axes.c2p(0, 0)[1],
                fill_color=accent if i == 0 else PEN_BLACK,
                fill_opacity=0.85,
                stroke_width=0,
            ).move_to(axes.c2p(x, d["value"] / 2))
            bars.add(bar)

            label = Text(d["label"], font=FONT_CN, font_size=24, color=PEN_BLACK)
            label.next_to(bar, DOWN, buff=0.2)
            labels.add(label)

            val = Text(f"{d['value']}{unit}", font=FONT_CN_BOLD, font_size=24, color=accent)
            val.next_to(bar, UP, buff=0.1)
            values.add(val)

        self.play(*[GrowFromEdge(b, DOWN) for b in bars], run_time=min(1.5, duration * 0.4))
        self.play(*[Write(l, run_time=0.3) for l in labels])
        self.play(*[Write(v, run_time=0.3) for v in values])

        self.wait(max(0.5, duration - 2.5))


class FlowScene(WhiteboardScene):
    """流程图/思维导图 - 框+箭头连接。"""

    def construct(self):
        p = load_params()
        nodes = p.get("nodes", [{"text": "起点", "color": "BLACK"}])
        edges = p.get("edges", [])  # [[0,1], [1,2], ...]
        accent = ACCENT_MAP.get(p.get("accent", "GREEN"), PEN_GREEN)
        duration = p.get("duration", 5)

        # 创建节点框
        boxes = VGroup()
        for n in nodes:
            color = ACCENT_MAP.get(n.get("color", "BLACK"), PEN_BLACK)
            box = VGroup(
                Rectangle(
                    width=2.6, height=1.0,
                    fill_color=color, fill_opacity=0.1,
                    stroke_color=color, stroke_width=3, cap_style=CapStyleType.ROUND,
                ),
                Text(n["text"], font=FONT_CN, font_size=26, color=PEN_BLACK),
            )
            boxes.add(box)

        # 布局：环形或线性
        if len(boxes) <= 3:
            boxes.arrange(RIGHT, buff=1.5)
        else:
            boxes.arrange_in_grid(rows=2, buff=(1.2, 1.0))

        # 逐个出现
        for box in boxes:
            self.play(FadeIn(box, run_time=0.4))

        # 画箭头
        arrows = VGroup()
        for e in edges:
            if e[0] < len(boxes) and e[1] < len(boxes):
                arrow = Arrow(
                    start=boxes[e[0]].get_right(),
                    end=boxes[e[1]].get_left(),
                    color=accent, stroke_width=4, buff=0.15,
                )
                arrows.add(arrow)
        if arrows:
            self.play(*[Create(a, run_time=0.5) for a in arrows])

        self.wait(max(0.5, duration - 1.5 - len(boxes) * 0.4))


class IconGridScene(WhiteboardScene):
    """平台图标网格 - 逐个点亮。"""

    def construct(self):
        p = load_params()
        items = p.get("items", [{"label": "平台1"}])
        accent = ACCENT_MAP.get(p.get("accent", "ORANGE"), PEN_ORANGE)
        duration = p.get("duration", 5)

        cells = VGroup()
        for it in items:
            color = ACCENT_MAP.get(it.get("color", "ORANGE"), PEN_ORANGE)
            cell = VGroup(
                Circle(radius=0.6, fill_color=color, fill_opacity=0.12,
                       stroke_color=color, stroke_width=3, cap_style=CapStyleType.ROUND),
                Text(it["label"], font=FONT_CN, font_size=22, color=PEN_BLACK),
            )
            cells.add(cell)

        cols = min(3, len(cells))
        cells.arrange_in_grid(rows=int((len(cells) + cols - 1) / cols), cols=cols, buff=1.0)

        # 逐个点亮
        for cell in cells:
            circle = cell[0]
            self.play(
                GrowFromCenter(circle, run_time=0.3),
                Write(cell[1], run_time=0.3),
            )
            self.wait(0.1)

        self.wait(max(0.3, duration - len(cells) * 0.6 - 0.3))


class QuoteScene(WhiteboardScene):
    """金句卡: 引号 + 高亮框 + 放大强调。"""

    def construct(self):
        p = load_params()
        quote = p.get("quote", "金句内容")
        accent = ACCENT_MAP.get(p.get("accent", "RED"), PEN_RED)
        duration = p.get("duration", 4)

        # 引号
        quote_mark = Text("“", font=FONT_CN_BOLD, font_size=120, color=accent, opacity=0.3)
        quote_mark.to_corner(UL, buff=0.5)
        self.add(quote_mark)

        # 高亮框
        box = Rectangle(
            width=config.frame_width * 0.8,
            height=2.0,
            fill_color=accent, fill_opacity=0.08,
            stroke_color=accent, stroke_width=3, cap_style=CapStyleType.ROUND,
        )
        self.play(FadeIn(box, run_time=0.5))

        # 金句文字
        quote_txt = Text(
            quote, font=FONT_CN_BOLD, font_size=44, color=PEN_BLACK,
            line_spacing=1.2,
        ).move_to(box)
        # 如果太长则缩放
        if quote_txt.width > box.width * 0.9:
            quote_txt.scale_to_fit_width(box.width * 0.9)

        self.play(Write(quote_txt, run_time=min(2.0, duration * 0.6)))
        self.play(quote_txt.animate.scale(1.05).set_color(accent), run_time=0.4)
        self.play(quote_txt.animate.scale(1 / 1.05), run_time=0.3)

        self.wait(max(0.5, duration - 3.0))


class PortraitScene(WhiteboardScene):
    """人物肖像场景: 左侧显示角色简笔肖像 + 右侧显示名字/描述。"""

    def construct(self):
        p = load_params()
        image_path = p.get("image", "")
        title = p.get("title", "")
        subtitle = p.get("subtitle", "")
        accent = ACCENT_MAP.get(p.get("accent", "BLACK"), PEN_BLACK)
        duration = p.get("duration", 5)

        # 左侧: 人物肖像（圆形裁切 + 边框）
        img = None
        if image_path and os.path.exists(image_path):
            try:
                img = ImageMobject(image_path)
                # 限制图片高度，给右侧文字留空间
                img.scale_to_fit_height(4.8)
                img.to_edge(LEFT, buff=0.7)
                # 圆形边框
                frame = Circle(
                    radius=img.width / 2 + 0.12,
                    stroke_color=accent,
                    stroke_width=4,
                    fill_opacity=0,
                ).move_to(img.get_center())
                self.play(FadeIn(img, run_time=0.5), Create(frame, run_time=0.5))
            except Exception as e:
                print(f"  [Portrait] 图片加载失败: {e}", file=sys.stderr)
                img = None

        if img is None:
            # 无图片时显示占位圈
            placeholder = Circle(
                radius=2.2, stroke_color=accent, stroke_width=4,
                fill_opacity=0.08, fill_color=accent,
            ).to_edge(LEFT, buff=0.7)
            circle_label = Text("待上传", font=FONT_CN, font_size=24,
                                color=accent).move_to(placeholder)
            self.play(Create(placeholder, run_time=0.5), FadeIn(circle_label, run_time=0.3))
            img = placeholder

        # 右侧: 标题 + 副标题（紧靠图片右侧，避免重叠）
        right_group = VGroup()
        if title:
            title_txt = Text(
                title, font=FONT_CN_BOLD, font_size=48, color=PEN_BLACK,
                line_spacing=1.2,
            )
            # 最大宽度：剩余空间（画面右侧到右边缘）
            max_width = config.frame_width - img.get_right()[0] - 1.2
            if max_width > 1.5 and title_txt.width > max_width:
                title_txt.scale_to_fit_width(max_width)
            right_group.add(title_txt)

        if subtitle:
            sub_txt = Text(
                subtitle, font=FONT_CN, font_size=30, color=accent,
                line_spacing=1.1,
            )
            if right_group:
                sub_txt.next_to(right_group[0], DOWN, buff=0.3, aligned_edge=LEFT)
            max_width = config.frame_width - img.get_right()[0] - 1.2
            if max_width > 1.5 and sub_txt.width > max_width:
                sub_txt.scale_to_fit_width(max_width)
            right_group.add(sub_txt)

        if right_group:
            # 将文字组放在图片右侧，顶端对齐
            right_group.next_to(img, RIGHT, buff=0.7, aligned_edge=UP)
            # 确保不超出右边界
            if right_group.get_right()[0] > config.frame_width / 2 - 0.3:
                right_group.shift(LEFT * (right_group.get_right()[0] - config.frame_width / 2 + 0.3))
            self.play(*[Write(m, run_time=0.6) for m in right_group])

        # 下划线装饰
        if right_group and title:
            underline = Line(
                start=right_group[0].get_left(),
                end=right_group[0].get_right(),
                color=accent, stroke_width=4,
            ).next_to(right_group[0], DOWN, buff=0.12)
            self.play(Create(underline, run_time=0.3))

        self.wait(max(0.5, duration - 2.5))


class IllustrationScene(WhiteboardScene):
    """场景插图: 全屏简笔场景图 + 底部文字浮层。

    参数:
      image: 插图路径
      title: 画面标题（底部左侧）
      subtitle: 副标题/说明（底部右侧）
      overlay: True=半透明遮罩+白字, False=无遮罩（默认）
    """

    def construct(self):
        p = load_params()
        image_path = p.get("image", "")
        title = p.get("title", "")
        subtitle = p.get("subtitle", "")
        overlay = p.get("overlay", False)
        accent = ACCENT_MAP.get(p.get("accent", "BLACK"), PEN_BLACK)
        duration = p.get("duration", 5)

        # 加载场景插图
        has_img = False
        if image_path and os.path.exists(image_path):
            try:
                img = ImageMobject(image_path)
                # 缩放填满画面
                img.scale_to_fit_width(config.frame_width * 0.92)
                if img.height > config.frame_height * 0.85:
                    img.scale_to_fit_height(config.frame_height * 0.85)
                self.add(img)
                has_img = True
            except Exception as e:
                print(f"  [Illustration] 图片加载失败: {e}", file=sys.stderr)

        if not has_img:
            # 无图片时显示占位矩形
            placeholder = Rectangle(
                width=config.frame_width * 0.85,
                height=config.frame_height * 0.65,
                stroke_color=accent, stroke_width=3,
                fill_opacity=0.05, fill_color=accent,
            )
            placeholder.shift(DOWN * 0.3)
            label = Text("插图待生成", font=FONT_CN, font_size=32,
                         color=accent).move_to(placeholder)
            self.play(Create(placeholder, run_time=0.5), FadeIn(label, run_time=0.3))
            self.wait(max(0.5, duration - 1.0))
            return

        # 底部文字浮层 - 白底半透明条
        has_text = bool(title) or bool(subtitle)
        if has_text:
            text_bg = Rectangle(
                width=config.frame_width,
                height=1.4,
                fill_color=WHITEBOARD_BG,
                fill_opacity=0.92,
                stroke_width=0,
            ).to_edge(DOWN, buff=0)

            text_group = VGroup()
            if title:
                title_txt = Text(
                    title, font=FONT_CN_BOLD, font_size=42, color=PEN_BLACK,
                    line_spacing=1.1,
                )
                if title_txt.width > config.frame_width * 0.85:
                    title_txt.scale_to_fit_width(config.frame_width * 0.85)
                text_group.add(title_txt)

            if subtitle:
                sub_txt = Text(
                    subtitle, font=FONT_CN, font_size=28, color=accent,
                    line_spacing=1.0,
                )
                if sub_txt.width > config.frame_width * 0.85:
                    sub_txt.scale_to_fit_width(config.frame_width * 0.85)
                text_group.add(sub_txt)

            if text_group:
                text_group.arrange(DOWN, buff=0.15, aligned_edge=LEFT)
                text_group.move_to(text_bg.get_center())

            self.play(
                FadeIn(text_bg, run_time=0.4),
                *[Write(m, run_time=0.5) for m in text_group],
            )

        self.wait(max(1.0, duration - 2.0))


# 场景类型→类映射
SCENE_MAP = {
    "title": TitleScene,
    "text_reveal": TextRevealScene,
    "data_bar": DataBarScene,
    "flow": FlowScene,
    "icon_grid": IconGridScene,
    "quote": QuoteScene,
    "portrait": PortraitScene,
    "illustration": IllustrationScene,
}
