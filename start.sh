#!/usr/bin/env bash
# ============================================================
#  PlotPilot（墨枢）- AI 小说创作平台 启动器（Linux / macOS）
#  ============================================================
#  用法:
#    ./start.sh          → 自动模式（推荐双击或终端运行）
#    ./start.sh force    → 强制重启（清理残留进程后重启）
#    ./start.sh pack     → 打包分享（仅 hub.py 打包模式）
#
#  依赖:
#    - Python 3.10+（含 tkinter）
#    - 首次运行会自动创建 .venv 并安装依赖
# ============================================================

set -euo pipefail

# 切换到项目根目录（脚本所在目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

MODE="${1:-auto}"

# ════════════════════════════════════
# 工具函数
# ════════════════════════════════════
log_info()  { echo "  [INFO]  $*"; }
log_ok()    { echo "  [ OK ]  $*"; }
log_warn()  { echo "  [WARN]  $*"; }
log_error() { echo "  [ERR ]  $*" >&2; }

# ════════════════════════════════════
# Step 0: 确保必要目录存在
# ════════════════════════════════════
mkdir -p logs data/chromadb data/logs

# ════════════════════════════════════
# Step 1: 查找 Python（优先级：venv > 系统）
# ════════════════════════════════════
PYTHON_EXE=""

# A) 虚拟环境
if [ -f ".venv/bin/python" ]; then
    PYTHON_EXE=".venv/bin/python"
    log_info "使用虚拟环境 Python: $PYTHON_EXE"
fi

# B) 系统 PATH
if [ -z "$PYTHON_EXE" ]; then
    for cmd in python3 python; do
        if command -v "$cmd" &>/dev/null; then
            _ver=$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
            _maj=$(echo "$_ver" | cut -d. -f1)
            _min=$(echo "$_ver" | cut -d. -f2)
            if [ "${_maj:-0}" -gt 3 ] || { [ "${_maj:-0}" -eq 3 ] && [ "${_min:-0}" -ge 10 ]; }; then
                PYTHON_EXE=$(command -v "$cmd")
                log_info "使用系统 Python: $PYTHON_EXE ($_ver)"
                break
            fi
        fi
    done
fi

if [ -z "$PYTHON_EXE" ]; then
    log_error "未找到 Python 3.10+，请先安装："
    echo ""
    echo "  macOS:  brew install python@3.11"
    echo "  Ubuntu: sudo apt install python3.11 python3.11-tk"
    echo "  Arch:   sudo pacman -S python tk"
    echo ""
    echo "  或访问: https://www.python.org/downloads/"
    exit 1
fi

# ════════════════════════════════════
# Step 2: 检查 tkinter 可用性
# ════════════════════════════════════
if ! "$PYTHON_EXE" -c "import tkinter" &>/dev/null; then
    log_warn "tkinter 不可用，GUI 模式将失败。"
    echo ""
    echo "  安装 tkinter："
    echo "  macOS:  brew install python-tk@3.11  (或使用 python.org 官方安装包)"
    echo "  Ubuntu: sudo apt install python3-tk"
    echo "  Arch:   sudo pacman -S tk"
    echo ""
    # 不退出，让 hub.py 自己报错（可能用户已有其他方案）
fi

# ════════════════════════════════════
# Step 3: force 模式 — 清理残留进程
# ════════════════════════════════════
if [ "$MODE" = "force" ]; then
    log_info "Force 模式：清理占用 8005/8006 端口的进程..."
    for port in 8005 8006; do
        pid=$(lsof -ti ":$port" 2>/dev/null || true)
        if [ -n "$pid" ]; then
            kill -9 $pid 2>/dev/null || true
            log_ok "已终止占用端口 $port 的进程 (PID=$pid)"
        fi
    done
fi

# ════════════════════════════════════
# Step 4: 启动 GUI hub
# ════════════════════════════════════
echo ""
echo "  ┌────────────────────────────────────┐"
echo "  │  正在启动 PlotPilot（墨枢）...      │"
echo "  └────────────────────────────────────┘"
echo ""

# 在后台启动，与终端完全分离
# nohup 防止终端关闭时 SIGHUP 杀死进程
nohup "$PYTHON_EXE" -u scripts/install/hub.py "$MODE" \
    >"logs/hub_stdout.log" 2>"logs/hub_error.log" &

HUB_PID=$!
log_ok "PlotPilot 已在后台启动 (PID=$HUB_PID)"
log_info "日志: logs/hub_error.log"

# 稍等片刻，确认进程没有立即崩溃
sleep 1
if ! kill -0 "$HUB_PID" 2>/dev/null; then
    log_error "启动失败！请查看错误日志:"
    echo ""
    cat logs/hub_error.log 2>/dev/null | tail -20 || true
    exit 1
fi

log_ok "GUI 窗口应已弹出，此终端可以关闭。"
exit 0
