# PlotPilot (墨枢) - macOS 本地开发与启动指南 (README Local)

> [!NOTE]
> 本文档专门用于记录和指导在 **macOS** 系统下，如何快速部署、本地开发、单元测试和一键启动 PlotPilot 项目。
> 本文件已被加入 `.gitignore`，不会被提交到公共仓库，仅供本地环境及本次协作参考使用。

---

## 🛠️ 1. 环境准备

在开始部署前，请确保您的 Mac 已经安装了以下底层环境：

1. **Python 3.9+**：推荐使用官方的 [uv](https://github.com/astral-sh/uv) 工具进行包管理器加速，或者标准的 `python3` 虚拟环境。
2. **Node.js 18+ & npm**：用于前端 Vite 开发服务的运行与静态资源编译。

---

## 🐍 2. 后端（Backend）部署与启动

后端项目为基于 **FastAPI + Uvicorn + SQLite** 构建的 Python 服务。

### 2.1 依赖安装与虚拟环境构建
在仓库根目录（即 `/Users/maphi-macminim4/DEV/01_Project/01_PlotPilot/PlotPilot`）下执行：

```bash
# 1. 创建 Python 虚拟环境 (二选一)
# 推荐方式 (使用 uv)：
uv venv
# 传统方式：
python3 -m venv .venv

# 2. 激活虚拟环境
source .venv/bin/activate

# 3. 安装依赖包 (二选一)
# 推荐方式 (使用 uv)：
uv pip install -r requirements.txt
# 传统方式：
pip install -r requirements.txt
```

### 2.2 启动后端开发服务器
确保已激活虚拟环境后，在仓库根目录下运行：

```bash
# 启动 FastAPI 开发服务（默认端口 8005）
uvicorn interfaces.main:app --host 127.0.0.1 --port 8005 --reload
```
* 服务启动后，可以在浏览器访问：`http://127.0.0.1:8005/docs` 查看 Swagger API 交互式文档。

---

## ⚡ 3. 前端（Frontend）部署与启动

前端项目是基于 **Vue 3 + Vite + TypeScript + Naive UI** 编写的单页应用。

### 3.1 依赖安装
导航至 `frontend` 目录：

```bash
cd frontend
npm install
```

### 3.2 启动前端开发服务器
在 `frontend` 目录下运行：

```bash
# 启动 Vite 本地开发代理服务（默认端口 3000）
npm run dev -- --host 127.0.0.1 --port 3000
```
* 浏览器访问 `http://127.0.0.1:3000` 即可进入本地开发调试页面。所有发往 `/api` 的请求均已通过 Vite Proxy 自动转发至后端的 `8005` 端口。

---

## 🚀 4. 一键极速启动（推荐 ⭐️）

如果您不想每次都打开两个终端窗口分别启动前后端，我们在本地提供了一个 **一键并发启动脚本**。

### 4.1 赋权与运行
在仓库根目录下运行：

```bash
# 1. 赋予执行权限（如果之前未授权）
chmod +x scripts/dev-local.sh

# 2. 运行一键启动脚本
sh scripts/dev-local.sh
```

### 4.2 脚本工作机制
此脚本基于 Bash 运行，执行以下逻辑：
1. **自动激活** 根目录下的 `.venv` 并以后台进程形式运行 Uvicorn 服务（8005 端口）。
2. **并发启动** `frontend` 下的 Vite 编译服务（3000 端口）。
3. **集成退出监听**：按下 `Ctrl + C` 时，脚本会自动触发信号捕获（trap），同时且优雅地杀掉前后端进程，绝无端口残留冲突。

---

## 💾 5. macOS 平台数据与日志路径

了解本地数据存放的绝对路径有助于在调试、清空库或者手动迁移数据时保持绝对掌控。

### 5.1 数据库路径
* **本地独立开发运行（`uvicorn`）**：
  * 使用本地仓库内的 SQLite 库：`/Users/maphi-macminim4/DEV/01_Project/01_PlotPilot/PlotPilot/data/plotpilot.db`
* **桌面安装包壳中运行（Tauri App）**：
  * macOS 规范沙盒目录：`~/Library/Application Support/com.plotpilot.desktop/data/plotpilot.db`

### 5.2 日志路径
* 所有后端产生的运行时日志文件存放在：
  * `/Users/maphi-macminim4/DEV/01_Project/01_PlotPilot/PlotPilot/logs/`

---

## 🧪 6. 单元测试运行

本次我们针对世界观与人物改名级联更新的逻辑，编写了严密的标准 Pytest 单元测试：

```bash
# 激活虚拟环境
source .venv/bin/activate

# 运行改名级联同步更新测试
pytest tests/unit/application/world/test_bible_service_propagation.py -v
```
* 该测试套件采用隔离的内存数据库运行，测试结束自动销毁，不会对本地开发库引入脏数据。

---

## 🌐 7. 独立启动命令 (免激活虚拟环境 & 全局任意目录可运行的绝对路径命令)

如果您在全局终端（未激活虚拟环境 `.venv`）下直接运行 `uvicorn` 会提示 `zsh: command not found: uvicorn`。
以下是使用 **绝对路径** 的“一行流”启动命令，**无论您当前处于系统中的任何目录**，都可以直接复制并在终端中一键运行：

### 7.1 后端绝对路径启动命令 (免激活 .venv)
使用虚拟环境内部的 Python 解析器，并配合 `--app-dir` 指向项目根目录：
```bash
/Users/maphi-macminim4/DEV/01_Project/01_PlotPilot/PlotPilot/.venv/bin/python -m uvicorn interfaces.main:app --app-dir /Users/maphi-macminim4/DEV/01_Project/01_PlotPilot/PlotPilot --host 127.0.0.1 --port 8005 --reload
```

### 7.2 前端绝对路径启动命令 (免切换目录)
使用 npm 的 `--prefix` 选项，让 npm 自动寻址并在目标前端目录下启动 Vite：
```bash
npm run dev --prefix /Users/maphi-macminim4/DEV/01_Project/01_PlotPilot/PlotPilot/frontend -- --host 127.0.0.1 --port 3000
```

### 7.3 端口一键强行释放命令 (解决 Address already in use 报错)
如果您在启动后端或前端时遇到 `Address already in use` 或者是 Vite 端口被迫从 `3000` 漂移切换的情况，说明后台已有残留僵尸进程锁定了端口。复制并运行下面这一行命令，可强行杀掉并释放 8005 (后端) 和 3000 (前端) 端口：
```bash
kill -9 $(lsof -t -i:8005 -i:3000) 2>/dev/null || true
```

