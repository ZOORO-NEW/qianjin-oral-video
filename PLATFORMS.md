# PLATFORMS.md — 跨平台部署指南

本技能支持以下AI平台部署：

| 平台 | 部署方式 | System Prompt |
|------|---------|--------------|
| WorkBuddy | SKILL.md 自动加载 | 自动 |
| OpenClaw | 导入SKILL.md | prompts/system-prompt-zh.md |
| Hermes | 导入SKILL.md | prompts/system-prompt-zh.md |
| Codex | 导入SKILL.md | prompts/system-prompt-en.md |
| ChatGPT | 复制system-prompt-zh.md到Custom Instructions | prompts/system-prompt-zh.md |
| Claude | 复制system-prompt-zh.md到Project Knowledge | prompts/system-prompt-zh.md |

## 部署说明

1. **WorkBuddy**：将整个技能目录放到 `~/.workbuddy/skills/qianjin-oral-video/`，自动识别并加载
2. **OpenClaw/Hermes**：将SKILL.md和references/目录上传到技能库
3. **ChatGPT/Claude**：将 `prompts/system-prompt-zh.md` 内容复制到自定义指令或项目知识库
4. **其他平台**：将SKILL.md主体内容+system prompt合并为单一指令文件

## 语言版本

- 中文版：`prompts/system-prompt-zh.md`
- 英文版：`prompts/system-prompt-en.md`
- 中文版为默认版本，覆盖抖音/视频号/B站/小红书4个中国平台
- 英文版可扩展适配YouTube/TikTok等国际平台

## 与qianjin技能体系的联动

- **qianjin-writer**：先用写作引擎写好长文，再用本技能转口播脚本
- **qianjin-content-repurposer**：一鱼多吃6平台转化后，对视频平台版本进一步细化为口播脚本
- **qianjin-trending-hunter**：热点选题确定后，用本技能快速生成口播脚本出视频
