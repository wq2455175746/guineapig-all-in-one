# GuineaPig Product Sense

## Product Vision
GuineaPig 是一个以语音交互为核心的 AI 桌面助手，通过 LLM + ASR + TTS 能力整合，让用户以最自然的语音方式控制 AI 完成各种任务。

## Core Principles
1. **语音优先 (Voice First)**: 主要交互方式是语音输入输出，文本为辅助记录手段
2. **AI 原生 (AI Native)**: 所有能力围绕 LLM 驱动循环构建，非传统功能堆砌
3. **模块化 (Modular)**: 功能以 Skill/Subagent/MCP 方式扩展，核心循环不变
4. **离线感知 (Offline Aware)**: 核心交互尽量不依赖实时网络（MVP 阶段为非实时）

## Core Features

### Phase 1: 语音对话基础能力
- 语音输入 -> ASR 解析 -> LLM 对话 -> TTS 输出
- 邮箱注册登录
- 对话历史记录
- 基础用户管理 (ops-web)

### Phase 2: 高级语音能力
- 对话实时翻译
- 听书（语音播报 + 位置记忆）
- 多轮对话上下文保持

### Phase 3: 智能助理能力
- 新闻订阅与定时播报
- 股票分析
- AI 接听/语音信箱
- 自定义 Skill 系统

## User Stories

### Voice Dialogue
- 用户按下录音键 -> 说话 -> 松开 -> 等待 AI 语音回复
- 每次语音输入限制 10s 内
- LLM 回复限制 20s 内，长内容分段生成

### Translation
- 用户说中文 -> AI 输出英文语音（或反向）
- 支持实时翻译模式

### Audio Book
- 用户上传/选择文本 -> AI TTS 朗读
- 记忆阅读位置，下次继续

## Non-Functional Requirements
- 语音交互延迟: < 3s (端到端)
- 对话上下文窗口: 最近 20 轮
- 并发用户: MVP 支持 10 并发
- 音频格式: MP3 (客户端) / OPUS (实时模式预留)
