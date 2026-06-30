#!/bin/bash
# 系统代理设置工具 - 启动脚本
# 检查依赖并启动程序

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/proxy_setting_tool.py"

# 检查 Python3
if ! command -v python3 &>/dev/null; then
    echo "[错误] 未找到 python3，请先安装："
    echo "  sudo apt install python3"
    exit 1
fi

# 检查 tkinter
if ! python3 -c "import tkinter" 2>/dev/null; then
    echo "[提示] 正在安装 tkinter 依赖..."
    sudo apt install -y python3-tk || {
        echo "[错误] 无法安装 python3-tk，请手动运行：sudo apt install python3-tk"
        exit 1
    }
fi

# 启动程序
echo "[启动] 正在启动系统代理设置工具..."
python3 "$PYTHON_SCRIPT"
