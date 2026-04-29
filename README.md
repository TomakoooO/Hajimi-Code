<div align="center">
  <h1>🐾 哈吉米代码编辑器 (Hajimi Code) ✨</h1>
  <p>一个基于 <strong>多智能体协作</strong> 的本地大模型驱动代码编辑器。</p>
</div>

## 📖 项目简介

Hajimi Code 是一个类似 Trae/Cursor 的智能代码编辑器前端与后端分离项目。它由本地运行的 AI 智能体驱动，能够自主探索工作区、阅读并修改代码、管理任务，并支持动态加载技能卡片（SKILLs）。

---

## 🚀 项目功能

- **💬 多智能体协作 (Multi-Agent System)**: 主 Agent 可以派生探索型子智能体（Subagents）独立完成代码搜索、文件读写等具体任务。
- **📋 全局任务看板 (Task Board)**: 内置 `pending`、`in_progress`、`completed` 的任务状态流，自动解析依赖关系（`blockedBy` / `blocks`），并在 UI 端动态渲染 Kanban 面板。
- **🛠️ 动态技能加载 (Dynamic SKILLs)**: 提供可视化页面，支持直接上传自定义 Markdown 格式的技能卡片（例如：处理 PDF、画时序图等），AI 能够实时感知并使用这些新能力。
- **⚙️ 上下文管理与压缩 (Context Compression)**: 支持前端 Token 消耗量估算（饼图进度），允许手动触发后端的智能对话压缩，剔除冗长的终端输出，保留核心关键信息。
- **🎨 现代级玻璃态 UI**: 还原主流 IDE 的左右侧边栏与编辑器布局，提供流畅的顶部悬浮导航（Sticky Nav）、组件切换、Markdown 代码高亮与 Diff 差异对比视图。

---

## 🛠️ 使用技术栈

- **前端 (Frontend)**: Vue 3 (Composition API), Vite, Pinia, Monaco Editor, Tailwind CSS
- **后端 (Backend)**: FastAPI, Uvicorn, Python 3.10+
- **AI 接入**: Anthropic SDK (完全兼容 OpenAI / DeepSeek API 协议)
- **依赖与并发控制**: Conda / Virtualenv, 异步 asyncio 与守护线程 (Daemon Threads 防止 Uvicorn 重启死锁)

---

## � 项目框架

本项目采用标准的前后端分离架构，核心目录结构如下：

```text
Hajimi-Code/
├── backend/                 # 后端目录
│   └── app/                 # FastAPI 主程序目录
│       ├── agent/           # 智能体核心逻辑 (Agent 循环, TaskManager 任务调度)
│       ├── api/             # 路由接口 (REST API 与 WebSocket 双向通信)
│       ├── skills/          # 动态技能卡片 (SKILL.md) 的持久化存储目录
│       └── .env.example     # 环境变量配置示例 (如大模型 API 密钥)
├── fronted/                 # 前端目录
│   ├── src/                 # Vue 源码 (Components 视图组件, Stores 状态管理)
│   ├── package.json         # 前端 Node 依赖配置
│   └── vite.config.ts       # Vite 构建与端口锁定配置
├── .tasks/                  # 全局任务看板数据存储目录 (JSON 格式持久化)
├── requirements.txt         # 后端 Python 依赖清单 (pip freeze 导出)
└── README.md                # 项目说明文档
```

---

## 📦 如何安装依赖与启动前后端

### 1. 准备工作
将项目克隆到本地，并进入项目根目录：
```bash
git clone https://github.com/yourusername/Hajimi-Code.git
cd Hajimi-Code
```

### 2. 后端部署 (FastAPI)
建议使用 Conda 创建干净的虚拟环境以避免依赖冲突。

```bash
# 创建并激活虚拟环境 (推荐 Python 3.10+)
conda create -n your-env-name-here python=3.10
conda activate your-env-name-here

# 安装后端依赖
pip install -r requirements.txt

# 配置大模型 API 密钥
# 将 backend/app 目录下的 .env.example 复制一份并重命名为 .env，填入你的 API Key
cp backend/app/.env.example backend/app/.env

# 启动后端服务 (在项目根目录下执行)
conda run --no-capture-output -n your-env-name-here uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload
```
成功启动后，后端将运行在 `http://127.0.0.1:8000`。

### 3. 前端部署 (Vue 3)
打开一个新的终端窗口，启动前端：

```bash
# 进入前端工作目录
cd fronted

# 安装前端依赖 (推荐 Node.js 18+)
npm install

# 启动 Vite 开发服务器
npm run dev
```
成功启动后，前端开发服务器将默认运行在 `http://localhost:5173/`，在浏览器中打开此地址即可体验完整的 AI 编辑器。

---


## 📄 License
MIT License
