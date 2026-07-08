# 口播视频生成（Manim白板动画版）

> 本模块在 `qianjin-oral-video` 技能输出的**口播脚本**基础上，自动生成带配音的简笔风白板动画视频。

## 一、管道总览

```
口播脚本.md
    │  (脚本解析器提取分段)
    ▼
结构化分段: [{time, oral_text, subtitle, visual_type, emotion}]
    │
    ├─→ [1] TTS生成器 (edge-tts)
    │       每段口播台词 → segment_N.mp3 + word_timestamps_N.json
    │
    ├─→ [2] Manim白板场景
    │       每段视觉指令 → segment_N.mp4 (简笔风动画)
    │
    ├─→ [3] 字幕生成器
    │       词级时间戳 + 字幕要点 → 内嵌字幕轨道
    │
    └─→ [4] FFmpeg合成
            音频 + 动画 + 字幕 → final.mp4 (配音+白板+字幕)
```

## 二、环境依赖

| 依赖 | 版本 | 用途 | 安装命令 |
|------|------|------|---------|
| Python venv | 3.13.12 | 隔离环境 | 已配置 |
| edge-tts | 7.2.8+ | 中文配音+TTS时间戳 | `pip install edge-tts` |
| manim | 0.20.1+ | 白板动画渲染 | `pip install manim` |
| ffmpeg | 8.1.1+ | 视频合成 | 系统已装（winget） |
| Pillow | 12.2.0+ | 字幕帧生成 | `pip install pillow` |

**关键路径：**
- ffmpeg: `C:\Users\ZQJ\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe`
- Python venv: `C:\Users\ZQJ\.workbuddy\binaries\python\envs\default\Scripts\python.exe`

## 三、白板视觉风格规范

### 配色（马克笔调色板）

```python
WHITEBOARD_BG = "#FAFAFA"      # 米白背景（非纯白，减少刺眼）
PEN_BLACK = "#1A1A1A"          # 黑笔（主线条/正文）
PEN_BLUE = "#1F6FEB"           # 蓝笔（强调/数据）
PEN_RED = "#E03131"            # 红笔（警示/对比）
PEN_GREEN = "#2F9E44"          # 绿笔（正向/完成）
PEN_ORANGE = "#F08C00"         # 橙笔（高亮/过渡）
```

### 字体

```python
FONT_CN = "Noto Sans SC"       # 白板主字体（干净无衬线）
FONT_CN_BOLD = "simhei"        # 粗体（标题/金句）
```

### 动画语言

| 动画 | 效果 | 适用 |
|------|------|------|
| `Write` | 手写浮现（笔画顺序） | 标题、金句、关键词 |
| `Create` | 绘制出现（线条生长） | 图形、箭头、框 |
| `FadeIn` | 淡入 | 背景元素、图标 |
| `Transform` | 变形过渡 | 数据变化、状态切换 |
| `GrowFromCenter` | 中心放大 | 圆形、图标出现 |

### 简笔风关键参数

```python
# 手写感线条
stroke_width=3,            # 马克笔粗细
cap_style=Round,           # 圆头笔触
line_join=Round,           # 圆角连接

# 白板留白
buff=0.5,                  # 元素间距
```

## 四、场景类型映射

从口播脚本的 `🎬 视觉指令` 解析出 `visual_type`，映射到对应 Manim 场景：

| visual_type | 触发关键词 | 场景类 | 说明 |
|-------------|-----------|--------|------|
| `title` | 开场/Hook/标题 | `TitleScene` | 大字标题+强调下划线+背景色块 |
| `text_reveal` | 字幕弹出/要点/核心观点 | `TextRevealScene` | 关键词手写浮现，逐条出现 |
| `data_bar` | 数据图表/对比/柱状 | `DataBarScene` | 动态柱状图，数值增长动画 |
| `flow` | 流程图/思维导图/组合 | `FlowScene` | 框+箭头连接，逐步展开 |
| `icon_grid` | 平台/多元素/列表 | `IconGridScene` | 图标网格，逐个点亮 |
| `quote` | 金句/收尾/核心句 | `QuoteScene` | 引号+高亮框+放大强调 |

## 五、脚本解析规则

从口播脚本Markdown提取结构化数据：

```python
# 分段标识: [0-3秒] / [15-40秒] 等
# 台词标识: 🗣 口播台词：
# 字幕标识: 📝 字幕要点：
# 视觉标识: 🎬 视觉指令：镜头：xxx / 字幕弹出：xxx

segment = {
    "id": 1,
    "time_range": "0-3秒",
    "visual_type": "title",        # 从🎬指令推断
    "oral_text": "一个数字吓你一跳...",  # 从🗣提取
    "subtitle": "1.6万亿参数完全免费",   # 从📝提取
    "emotion": "震惊开场",          # 从💡提取
    "tts_voice": "zh-CN-YunxiNeural"
}
```

## 六、TTS配音生成

### edge-tts关键参数

```python
communicate = edge_tts.Communicate(
    text=oral_text,
    voice="zh-CN-YunxiNeural",   # 男声，偏新闻播报感
    boundary="WordBoundary",      # 必须！获取词级时间戳
    rate="+0%",                   # 语速，可微调
)
```

### 输出

- `segment_N.mp3` — 配音音频
- `word_timestamps_N.json` — 词级时间戳（offset_ms/duration_ms）

### 速率限制处理

edge-tts连续调用会触发403限流，必须指数退避重试：

```python
async def generate_with_retry(text, voice, path, max_retries=5):
    for attempt in range(max_retries):
        try:
            # stream一次性收集audio + word boundaries
            ...
            return words
        except Exception:
            await asyncio.sleep(2 ** attempt)  # 1s, 2s, 4s, 8s, 16s
```

### 推荐声音

| Voice | 性别 | 风格 | 适用平台 |
|-------|------|------|---------|
| zh-CN-YunxiNeural | 男 | 沉稳有磁性 | 抖音/视频号通用 |
| zh-CN-YunyangNeural | 男 | 活力年轻 | 抖音/B站 |
| zh-CN-XiaoxiaoNeural | 女 | 亲切自然 | 小红书/视频号 |
| zh-CN-YunjianNeural | 男 | 专业播报 | B站知识区 |

## 七、字幕生成

### 方案：内嵌硬字幕

用Pillow生成字幕帧，叠加在动画视频上（ffmpeg overlay），确保跨平台兼容。

### 字幕规范

- 底部横条：白字 + 半透明黑底
- 字体大小：视频高度的1/18
- 字幕内容：来自📝字幕要点（提炼版，≤15字）
- 出现时机：对齐word_timestamps的对应词

## 八、FFmpeg合成

```bash
# 1. 音频+动画合成（每段）
ffmpeg -i segment_N.mp4 -i segment_N.mp3 -c:v copy -c:a aac -shortest seg_with_audio_N.mp4

# 2. 拼接所有段
ffmpeg -f concat -safe 0 -i segments.txt -c copy final_raw.mp4

# 3. 叠加字幕（硬字幕）
ffmpeg -i final_raw.mp4 -vf "subtitles=subtitles.srt" final.mp4
```

## 九、质量检查

| 检查项 | 标准 |
|--------|------|
| 音画同步 | 字幕出现误差<200ms |
| 配音完整 | 每段MP3时长≈脚本段落时长 |
| 动画时长 | Manim场景时长=对应音频时长 |
| 风格统一 | 全片白板配色一致 |
| 字幕可读 | 底部留白充足，对比度达标 |

## 十、已知限制

| 限制 | 影响 | 缓解方案 |
|------|------|---------|
| edge-tts限流 | 长视频需分段+重试 | 指数退避，单段≤50字 |
| Manim渲染慢 | 每段30-60秒渲染 | 低质量预览→高质量成品 |
| 中文手写字体 | 默认非手写体 | 用Write动画模拟手写感 |
| 表情/口型 | 无真人出镜 | 白板动画本身不需口型 |
| 背景音乐 | 需手动添加 | ffmpeg混音BGM轨道 |

## 十一、使用示例

```bash
# 1. 先用技能生成口播脚本
# （见SKILL.md工作流）

# 2. 运行视频生成管道
python scripts/generate_video.py \
  --script outputs/口播视频脚本_免费AI平台综.md \
  --output outputs/口播视频_免费AI平台综.mp4 \
  --voice zh-CN-YunxiNeural
```
