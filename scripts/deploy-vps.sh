#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${ROOT_DIR}"

echo "=========================================="
echo "    CardCue VPS 后端一键部署与启动脚本    "
echo "=========================================="

# 1. 检查环境变量文件
if [ ! -f "backend/.env" ]; then
    if [ -f "backend/.env.production.example" ]; then
        echo "[1/4] 未检测到 backend/.env，自动从 .env.production.example 创建..."
        cp backend/.env.production.example backend/.env
        echo "--> 请检查并确认 backend/.env 中的数据库密码与密钥是否正确！"
    else
        echo "错误：未找到 backend/.env 或 .env.production.example"
        exit 1
    fi
else
    echo "[1/4] 检测到已存在 backend/.env 配置文件。"
fi

# 2. 判断部署模式：优先推荐 Docker Compose
if command -v docker &>/dev/null && (docker compose version &>/dev/null || docker-compose version &>/dev/null); then
    echo "[2/4] 检测到系统已安装 Docker 与 Compose，使用容器化模式部署..."
    
    COMPOSE_CMD="docker compose"
    if ! docker compose version &>/dev/null; then
        COMPOSE_CMD="docker-compose"
    fi
    
    echo "--> 正在构建并启动服务..."
    ${COMPOSE_CMD} build
    ${COMPOSE_CMD} up -d
    
    echo "[3/4] 容器服务已启动，正在等待健康检查就绪..."
    for i in {1..30}; do
        if curl -s -f http://127.0.0.1:8000/health >/dev/null 2>&1; then
            echo "--> 后台服务健康检查通过！"
            break
        fi
        sleep 1
    done
else
    echo "[2/4] 未检测到 Docker，回退到原生 Python 3.11 虚拟环境部署模式..."
    
    if ! command -v python3 &>/dev/null; then
        echo "错误：系统未安装 python3，请先安装 Python 3.11+ 或 Docker！"
        exit 1
    fi
    
    cd backend
    if [ ! -d ".venv" ]; then
        echo "--> 创建 Python 虚拟环境..."
        python3 -m venv .venv
    fi
    
    echo "--> 安装依赖与当前模块..."
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -e .
    
    echo "--> 执行数据库迁移 (alembic upgrade head)..."
    .venv/bin/alembic upgrade head
    
    cd ..
    
    echo "[3/4] 启动原生进程..."
    echo "提示：推荐使用 systemd 服务托管，配置文件在 backend/deploy/ 目录。"
    echo "当前可在后台手动拉起服务："
    echo "nohup backend/.venv/bin/uvicorn cardcue_api.main:app --host 0.0.0.0 --port 8000 > api.log 2>&1 &"
    echo "nohup backend/.venv/bin/python -m cardcue_api.jobs.scheduler > scheduler.log 2>&1 &"
fi

# 4. 验证服务状态
echo "[4/4] 验证服务响应状态..."
HEALTH_RESP=$(curl -s http://127.0.0.1:8000/health || true)
CAP_RESP=$(curl -s http://127.0.0.1:8000/v1/capabilities || true)

echo "Health: ${HEALTH_RESP}"
echo "Capabilities: ${CAP_RESP}"
echo "=========================================="
echo "部署完成！请确保 VPS 防火墙已放行 8000 端口："
echo "  sudo ufw allow 8000/tcp"
echo "Android 手机已配置默认访问: http://152.70.238.24:8000"
echo "=========================================="
