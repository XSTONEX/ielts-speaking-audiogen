# Audio Generator

本项目是一个基于 Flask 的 Web 应用，集成了 DeerAPI 的 TTS（文本转语音）能力，支持通过网页界面输入文本并自动生成分门别类的音频文件，适合英语口语练习、听力材料制作等场景。

## 功能概述

- 支持输入文本并生成高质量语音（mp3），自动保存到指定分类文件夹。
- 支持音频及文本的分类管理、浏览和下载。
- 前端页面美观，操作简单直观。
- 支持自定义 Part2 问题文本的额外保存。
- 提供批量管理（删除音频/文件夹）等功能。
- 附带命令行脚本 `curl_openai_ttx.py`，可直接调用 API 生成音频。
<img width="880" height="924" alt="image" src="https://github.com/user-attachments/assets/c0438d37-eedb-4eb2-9e6c-e5d3d072af4e" />


## 快速开始

### 1. 安装依赖

建议使用 Python 3.8+，并在虚拟环境下运行：

```bash
pip install -r requirements.txt
```

### 2. 配置 API 密钥

在项目根目录下新建 `.env` 文件，内容如下（需自行申请 DeerAPI Key）：

```
DEER_API_KEY=你的_deerapi_key
```

### 3. 启动服务

```bash
python app.py
```

默认监听 `http://127.0.0.1:5000/`，用浏览器打开即可访问 Web 界面。

### 4. 使用命令行脚本（可选）

直接运行 `curl_openai_ttx.py` 可快速生成音频文件，适合批量或自动化场景。

```bash
python curl_openai_ttx.py
```

## 文件结构说明

- `app.py`：主后端服务，提供 API 和网页。
- `index.html`：前端页面，支持文本输入、音频管理等。
- `audio_files/`：所有生成的音频及文本文件按分类存储于此。
- `curl_openai_ttx.py`：命令行批量生成音频脚本。
- `requirements.txt`：依赖包列表。

## 其他说明

- 需科学上网以访问 DeerAPI。
- 支持多种分类（如 P1、P2、P3），可自定义文件夹名。
- 适合英语学习、口语考试备考等多种场景。

---

如需详细定制或遇到问题，欢迎提 Issue 或联系开发者。 
