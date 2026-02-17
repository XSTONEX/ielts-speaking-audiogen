# 雅思学习 🚀

一个综合性、AI 驱动的英语与雅思学习一站式 Web 平台。本项目将口语练习、文章精读、AI 音频转文本 (ASR) 以及自动化的写作逻辑链训练深度整合，构建了一个完整的语言学习生态系统。

## 🌟 核心功能模块

系统经过架构升级，目前由 9 个核心业务模块组成：

1. **🎤 口语练习 (speaking)**: 提供口语练习界面，集成 TTS 音频生成与文件管理功能。
2. **🎧 口语合集播放 (speaking_playlist)**: 自动化生成各个话题的音频与字幕合集，提供沉浸式听力环境。
3. **📖 阅读真题 (reading)**: 包含剑桥雅思真题目录检索、HTML 内嵌全屏预览及 PDF 下载功能。
4. **🔍 文章精读 (intensive_reading)**: 支持提交长文，提供词汇高亮、悬停释义添加，以及段落级别的音频合成。
5. **💬 学习交流小天地 (community)**: 留言板系统，供用户分享学习心得、交流音频与精读文章，内置词汇挑战与排行系统。
6. **📚 单词本 (vocabulary)**: 按听、说、读、写分类管理词汇，支持发音播放、CSV 批量导入以及后台音频队列自动处理。
7. **💡 学习技巧 (study_tips)**: 专项记录词汇替换（同义词/上下义词）以及各科做题技巧。
8. **🎙️ 音频转文本 (asr_transcription)**: 支持上传音频文件，调用底层 AI 模型生成高精度的文本内容。
9. **✍️ 写作逻辑链训练 (writing_logic)**: 解析 Markdown 格式的逻辑链语料，提供单句翻译实战交互，并接入大语言模型 (LLM) 进行多维度智能批改。

## 🏗️ 架构与技术栈

* **后端**: Python 3, Flask (基于 Blueprint 进行模块化重构)
* **前端**: HTML5, CSS3, Vanilla JS (Jinja2 模板渲染)
* **包管理**: uv (使用 pyproject.toml / uv.lock 进行极速依赖管理)
* **数据存储**: 基于 JSON 和本地扁平化文件系统，实现轻量级、高便携的数据持久化。
* **AI 集成**: 大语言模型 (LLM) 文本纠错与生成、TTS (文字转语音) 以及 ASR (自动语音识别) 接口联动。

### 📂 目录结构

项目近期从单体架构全面升级为高可维护的 Blueprint 模块化架构：

    .
    ├── app.py                  # 轻量级应用主入口
    ├── core.py                 # 全局公共依赖、认证逻辑与核心工具函数
    ├── routers/                # 按业务领域严格划分的 Flask Blueprints
    │   ├── auth.py
    │   ├── speaking.py
    │   ├── ... (其他业务模块)
    │   └── writing_logic.py
    ├── templates/              # Jinja2 HTML 模板目录
    ├── static/                 # CSS, JS 及静态资源库
    ├── pyproject.toml          # 现代 Python 包管理配置
    ├── uv.lock                 # 依赖锁定文件
    └── [各类数据目录]          # 如 user_data, vocab_audio, writing_correction 等

## 🚀 快速开始

### 环境准备

本项目采用极速的 `uv` 作为包管理工具。请确保已在系统中安装 `uv`：

    pip install uv

### 安装步骤

1. 克隆项目并进入根目录：

    cd ielts-speaking-audiogen

2. 使用 `uv` 自动同步依赖并创建虚拟环境：

    uv sync

### 配置说明

请确保正确配置了相关的 API 密钥（例如 OpenAI 或其他 ASR 服务的 Token）。检查并配置根目录下的 `tokens.json` 和 `users.json` 以完成本地认证和鉴权环境的搭建。

### 运行应用

启动 Flask 开发服务器：

    uv run app.py

应用启动后，可通过浏览器访问 `http://0.0.0.0:5001`。

*注：在启动 `app.py` 的同时，负责处理词汇音频生成的后台任务线程将会自动开启。*

## 🛠️ 近期重构纪要 (v2.0)

本项目近期完成了一次重大的架构解耦。原本高达 5400 多行的单体巨石文件 `app.py` 被安全、平滑地拆分为 10 个独立的 Flask Blueprints (`routers/`)。

* **前端零侵入**: 重构过程中未修改任何 HTML 模板或前端逻辑，所有 API 路由路径保持 100% 向后兼容。
* **状态解耦**: 所有的共享配置、鉴权装饰器和全局工具类被成功抽离至 `core.py`，彻底消除了模块间的循环导入风险。

---
*Built with ❤️ for better IELTS preparation.*