# 前进口播视频脚本引擎 (qianjin-oral-video)

将长文案一键转化为口播视频脚本，并自动生成完整口播视频（配音+白板动画+字幕）——让文字变成可看的视频。

## ✨ 核心功能

- 🎬 **长文→口播脚本**：输入一篇长文，输出完整口播视频脚本（开场Hook + 分镜脚本 + 视觉指令 + 字幕要点 + 情绪标记）
- 🤖 **脚本→自动出片**：将口播脚本直接渲染为 MP4 视频——含 AI 配音、Manim 白板动画、人物肖像/场景插图、硬字幕，一键出片
- 📱 **4平台适配**：抖音口播、视频号、B站知识区、小红书视频——不同平台不同节奏、语气、时长
- 🎯 **3秒Hook公式**：6大Hook类型（反常识/数据冲击/身份认同/悬念/对比/痛点直击）+组合技巧
- 🎥 **视觉指令系统**：镜头/B-roll/字幕/音效/道具/背景——脚本不只是文字，是视听蓝图
- 🖼️ **AI场景插图**：AI生成国风水墨人物肖像+场景插图，自动嵌入白板动画
- 🎤 **AI配音**：edge-tts 多音色配音（支持 Xiaoxiao/Yunxi/Yunyang 等），词级时间戳对齐
- 📊 **质量自检**：结构/内容/语言/视觉/平台5维度评分，确保脚本可直接拍摄
- 📝 **配套素材**：标题文案（3个备选）+ 封面文字 + 话题标签 + 评论区引导话

## 🚀 快速使用

### 一、生成口播脚本

**3步搞定：**

**第1步**：告诉AI你要做什么
```
把这篇长文案转成抖音口播脚本
```

**第2步**：粘贴你的长文案
```
[粘贴你的公众号文章/演讲稿/报告/笔记]
```

**第3步**：收到完整脚本
- 开场Hook + 口播台词 + 视觉指令 + 字幕要点 + 情绪标记 + 金句+CTA
- 配套标题、封面文案、话题标签、评论区引导

### 二、自动生成视频

拿到口播脚本后，执行以下命令行一键出片：

```bash
# 基础用法：口播脚本 → MP4
python scripts/generate_video.py \
  --script 口播脚本.md \
  --output final.mp4 \
  --voice zh-CN-XiaoxiaoNeural

# 带人物肖像 + 场景插图
python scripts/generate_video.py \
  --script 口播脚本.md \
  --output final.mp4 \
  --voice zh-CN-XiaoxiaoNeural \
  --portrait 人物肖像.png \
  --illustrations 插图映射.json

# 指定平台快捷方式
python scripts/generate_video.py \
  --script 口播脚本.md \
  --output final.mp4 \
  --platform douyin

# 限制段落数（测试用）
python scripts/generate_video.py \
  --script 口播脚本.md \
  --output final.mp4 \
  --max-segments 3
```

**参数说明：**
| 参数 | 说明 | 可选值 |
|------|------|--------|
| `--script` | 口播脚本 Markdown 路径（必填） | `*.md` |
| `--output` | 输出 MP4 路径（必填） | `*.mp4` |
| `--voice` | TTS 音色（见下方配音列表） | `zh-CN-XiaoxiaoNeural` / `zh-CN-YunxiNeural` 等 |
| `--platform` | 目标平台（自动设置分辨率和默认声音） | `douyin` / `channels` / `bilibili` / `xiaohongshu` |
| `--portrait` | 人物肖像图片路径 | `*.png` |
| `--illustrations` | 场景插图 JSON 映射文件 | `*.json` |
| `--quality` | 渲染质量 | `l`(低) / `m`(中) / `h`(高) / `k`(4K) |
| `--max-segments` | 限制处理段数（测试用） | 数字 |
| `--workdir` | 工作目录（临时文件存放） | 目录路径 |

### 三、视频生成能力详解

#### 🎤 配音支持

基于 edge-tts，提供多种中文音色：

| 音色标识 | 性别 | 风格 | 推荐场景 |
|---------|------|------|---------|
| `zh-CN-XiaoxiaoNeural` | 女声 | 清澈温柔 | **推荐**：人物科普、知识讲解、小红书 |
| `zh-CN-YunxiNeural` | 男声 | 沉稳有力 | 抖音口播、视频号（默认男性叙述） |
| `zh-CN-YunyangNeural` | 男声 | 专业播报 | B站知识区、新闻报道风格 |
| `zh-CN-XiaoyiNeural` | 女声 | 亲切活泼 | 轻松话题、生活分享 |
| `zh-CN-YunjianNeural` | 男声 | 年轻活力 | 年轻向内容、快节奏 |
| `zh-CN-XiaohanNeural` | 女声 | 温暖柔和 | 故事讲述、情感类 |
| `zh-CN-XiaomengNeural` | 女声 | 元气可爱 | 萌系内容、趣味科普 |

> ⚡ 快速试听：`--voice zh-CN-XiaoxiaoNeural` 是人物科普最优选（清澈、咬字清晰、语气自然）

#### 📐 画面比例

通过 `--platform` 一键切换，或手动指定分辨率：

| 平台 | 分辨率 | 比例 | 方向 | 默认配音 |
|------|--------|------|------|---------|
| `douyin` / `channels` | 1080×1920 | 9:16 竖屏 | 短视频 | YunxiNeural |
| `xiaohongshu` | 1080×1440 | 3:4 竖屏 | 图文笔记视频 | XiaoxiaoNeural |
| `bilibili` | 1920×1080 | 16:9 横屏 | 知识区横屏 | YunyangNeural |

不指定平台时默认 1920×1080 横屏。也可手动传入 `--resolution`（目前需修改参数）。

#### 🎨 白板动画场景（8种）

| 场景类型 | 视觉效果 | 自动触发条件 |
|---------|---------|-------------|
| **TitleScene** 🏷️ | 居中大字 + 红色下划线 + 背景色块 | 开场Hook / 标题段 |
| **TextRevealScene** ✏️ | 圆点标记 + 关键词逐条手写浮现 | 默认场景 |
| **DataBarScene** 📊 | 坐标轴 + 动态柱状图（数据对比） | 含数字+平台名对比的段落 |
| **FlowScene** 🔄 | 流程框 + 箭头连接 | 含"流程/组合/架构"等关键词 |
| **IconGridScene** 🔲 | 图标网格逐个点亮 | 含"图标/平台/网格"等关键词 |
| **QuoteScene** 💬 | 引号 + 高亮框 + 金句放大强调 | 含"金句/收尾/核心句"等关键词 |
| **PortraitScene** 👤 | 左侧圆形人物肖像 + 右侧标题/副标题 | 传入 `--portrait` 时自动嵌入 |
| **IllustrationScene** 🖼️ | 全屏场景插图 + 底部半透明文字浮层 | 传入 `--illustrations` 时自动嵌入 |

场景类型由脚本中的视觉指令自动推断，无需手动指定。同时传入肖像和插图时，插图优先于肖像。

#### 🖼️ 人物肖像与场景插图

```bash
# 1. 使用单张人物肖像（所有非标题段共享）
python scripts/generate_video.py \
  --script 脚本.md --output out.mp4 \
  --portrait 秦琼肖像.png

# 2. 使用多张场景插图（指定段替换）
# 先创建插图映射 JSON 文件（秦琼_插图映射.json）：
# {
#   "3": "段3的场景图.png",
#   "5": "段5的场景图.png"
# }
python scripts/generate_video.py \
  --script 脚本.md --output out.mp4 \
  --illustrations 插图映射.json

# 3. 肖像 + 插图同时使用
python scripts/generate_video.py \
  --script 脚本.md --output out.mp4 \
  --portrait 人物肖像.png \
  --illustrations 插图映射.json
```

插图映射 JSON 格式：键为段序号（从1开始），值为图片路径。路径可以使用相对路径或绝对路径。

#### 🎬 完整工作流示例

**Step 1 → 生成口播脚本**（由 AI 完成）
```
把秦琼那篇长文转成抖音口播脚本
```

**Step 2 → 生成配图**（可选，AI 生成肖像 + 场景插图）
使用 ImageGen 生成国风水墨风格的人物肖像和场景插图。

**Step 3 → 一键出片**
```bash
python scripts/generate_video.py \
  --script 秦琼_口播脚本.md \
  --output 秦琼_科普视频.mp4 \
  --voice zh-CN-XiaoxiaoNeural \
  --portrait 秦琼肖像.png \
  --illustrations 秦琼_插图映射.json
```

输出示例：
```
▶ 加载场景插图映射: 2张
▶ 解析口播脚本... → 5段
▶ 生成配音... → edge-tts 完成
▶ 生成白板动画...
  第1段 [TitleScene] ✅
  第2段 [PortraitScene] ✅  ← 自动嵌入人物肖像
  第3段 [IllustrationScene] ✅ ← 自动嵌入场景插图
  第4段 [QuoteScene] ✅
  第5段 [IllustrationScene] ✅
▶ 合成音视频... → 各段音画同步
▶ 拼接... → concat重编码（无黑屏）
▶ 字幕叠加... → SRT硬字幕
✅ 视频生成完成: 秦琼_科普视频.mp4 (2.5MB, 73秒)
```

#### 🖥️ 所需环境

- Python 3.10+（推荐 3.13）
- [Manim Community](https://docs.manim.community/) v0.20.1+（白板动画引擎）
- [FFmpeg](https://ffmpeg.org/)（视频合成 + 字幕叠加）
- [edge-tts](https://github.com/rany2/edge-tts)（AI配音）

```bash
pip install manim edge-tts
# FFmpeg 需单独安装（https://ffmpeg.org/download.html）
```

#### ⚙️ 视频管线工作原理

```
口播脚本.md
    │
    ▼
┌─ 解析分段 ────── 按 [0-5秒] 标签拆分，提取台词/字幕/视觉指令
│
├─ 1. edge-tts ─── 逐段配音 → MP3 + 词级时间戳
│
├─ 2. Manim ────── 逐段渲染白板动画 → 8种场景自动匹配
│      ├── TitleScene      标题卡
│      ├── TextRevealScene 关键词浮现
│      ├── PortraitScene   人物肖像（如果有肖像图）
│      ├── IllustrationScene 场景插图（如果有插图映射）
│      ├── DataBarScene    柱状图
│      ├── FlowScene       流程图
│      ├── IconGridScene   图标网格
│      └── QuoteScene      金句卡
│
├─ 3. FFmpeg ───── 每段音视频合成（截短到音频时长）
│
├─ 4. FFmpeg ───── 所有段拼接（concat滤镜重编码）
│
├─ 5. 字幕 ─────── 根据实际音频时长生成SRT时间轴
│
└─ 6. FFmpeg ───── 硬字幕叠加 → 最终 MP4
```

### 常见使用场景

| 场景 | 对话示例 |
|------|---------|
| 公众号文章→抖音口播 | "把这篇公众号文章转成抖音口播脚本" |
| 演讲稿→B站知识区视频 | "把这个演讲稿改写成B站5分钟口播脚本" |
| 行业报告→视频号短视频 | "把这个报告的核心数据做成视频号口播" |
| 笔记→小红书视频 | "把这段笔记转成小红书口播视频脚本" |
| 通用口播脚本 | "帮我写一个关于XX的口播视频脚本" |

### 触发词

| 触发词 | 说明 |
|-------|------|
| 口播脚本 / 口播视频脚本 | 最直接的触发词 |
| 转口播 / 文案变视频 | 从文案转化角度触发 |
| 视频脚本 / 拍摄脚本 | 从脚本需求角度触发 |
| oral video script / video script | 英文触发词 |

### 指定平台

如果不指定平台，默认生成**抖音口播版**（60-90秒）。
- "转成抖音口播脚本" → 60-90秒竖屏
- "转成视频号脚本" → 60-90秒竖屏沉稳版
- "转成B站脚本" → 5-10分钟横屏深度版
- "转成小红书视频脚本" → 30-60秒竖屏收藏版
- "转成4平台口播脚本" → 同时输出4个版本

### 进阶用法

- **指定时长**："转成一个3分钟的抖音口播脚本"
- **指定风格**："用前辈聊天的语气做一个视频号脚本"
- **批量转化**："把这5篇文章都转成抖音口播脚本"
- **联动写作引擎**："先用qianjin-writer写一篇文章，再转成口播脚本"

## 📁 技能结构

```
qianjin-oral-video/
├── SKILL.md                          # 技能主文件
├── PLATFORMS.md                      # 跨平台部署指南
├── README.md                         # 项目说明
├── assets/                           # 示例素材
├── prompts/
│   ├── system-prompt-zh.md           # 中文System Prompt
│   └── system-prompt-en.md           # 英文System Prompt
├── scripts/                          # 视频生成管线
│   ├── generate_video.py             # 主管道（解析→TTS→Manim→合成→字幕）
│   ├── manim_scenes.py               # 8种白板场景模板
│   ├── tts_generator.py              # edge-tts 配音生成
│   └── subtitle_generator.py         # SRT字幕生成
└── references/
    ├── platform-specs.md             # 4平台详细规格
    ├── script-structure.md           # 脚本结构模板+完整示例
    ├── hook-formulas.md              # 开场Hook公式库
    ├── visual-direction.md           # 视觉指令参考
    ├── transformation-rules.md       # 长文→口播转化规则
    ├── quality-checklist.md          # 质量自检表
    └── video-generation.md           # 视频生成指南
```

## 🤝 与qianjin技能体系联动

| 技能 | 联动方式 |
|------|---------|
| qianjin-writer | 先写好长文 → 再转口播脚本 → 生成视频 |
| qianjin-content-repurposer | 一鱼多吃6平台 → 视频平台版本细化为口播 |
| qianjin-trending-hunter | 热点选题 → 快速出口播脚本抢占时效 |

## ⚠️ 注意事项

- 口播脚本不是"读稿"，是"说话"——台词必须口语化
- 前3秒是生死线——必须有明确Hook，不铺垫不寒暄
- 不同平台语气完全不同——抖音说书人、视频号前辈聊天、B站知识UP主、小红书闺蜜分享
- 脚本不只是文字——每段必须有镜头/B-roll/字幕/音效标注
- 视频生成需要安装 FFmpeg 和 Manim Community v0.20.1+
- Windows 用户注意字幕路径使用相对路径（详见 video-generation.md）

## 📄 License

MIT License — 自由使用、修改、分发
