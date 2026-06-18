#!/usr/bin/env bash
# GPT2API_IIAP 启动脚本

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "======================================"
echo "  GPT2API_IIAP 启动脚本"
echo "======================================"

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到 python3，请先安装 Python 3.11+"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | sed -E 's/.* ([0-9]+\.[0-9]+).*/\1/')
echo "Python 版本: $PYTHON_VERSION"

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "创建虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate

# 安装/更新依赖
echo "检查依赖..."
pip install -q -r requirements.txt

# 检查 .env
if [ ! -f ".env" ]; then
    echo "警告: 未找到 .env 文件，将使用默认配置"
    echo "建议复制 .env.example 为 .env 并填写你的配置"
fi

# 清理旧数据库（可选）
read -p "是否清理旧数据库并重新初始化? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "清理旧数据库..."
    rm -f data/control.db data/control.db-shm data/control.db-wal
fi

# 日志目录
mkdir -p logs

# 检查端口占用
PORT=$(python3 -c "from app.config import settings; print(settings.port)")
if lsof -ti:$PORT &> /dev/null; then
    echo "端口 $PORT 已被占用，尝试关闭旧进程..."
    lsof -ti:$PORT | xargs kill -9 2>/dev/null || true
    sleep 1
fi

# 启动服务
echo ""
echo "启动 GPT2API_IIAP 服务..."
echo "访问地址: http://127.0.0.1:$PORT"
echo "前端页面: http://127.0.0.1:$PORT/ui"
echo "管理面板: http://127.0.0.1:$PORT/panel"
echo "日志文件: logs/server.log"
echo "======================================"

nohup python -m app.main > logs/server.log 2>&1 &
PID=$!
echo $PID > .pid
sleep 2

# 检查是否启动成功
if kill -0 $PID 2>/dev/null; then
    echo "服务启动成功 (PID: $PID)"
    echo ""
    echo "常用命令:"
    echo "  查看日志: tail -f logs/server.log"
    echo "  停止服务: kill \$(cat .pid)"
    echo "  测试状态: curl http://127.0.0.1:$PORT/healthz"
else
    echo "服务启动失败，请查看日志: logs/server.log"
    exit 1
fi
