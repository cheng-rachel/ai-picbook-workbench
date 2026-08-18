#!/bin/bash
# Power Up 绘编（Power Up Picture Book Forge）本地一键启动入口。
# 双击运行：启动 Web App 并自动打开浏览器；在本窗口按 Ctrl+C 停止服务。
# 本文件不保存任何 API Key；模型配置只从当前环境变量读取。

set -u
cd "$(dirname "$0")" || exit 1

PORT=8765
URL="http://127.0.0.1:${PORT}/"

if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 python3。请先安装 Xcode Command Line Tools 或 Python 3 后重试。"
  read -r -p "按回车键关闭…" _
  exit 1
fi

# Runtime Database 定位：环境变量 PICBOOK_DB 优先，
# 其次已有的教研运行库，最后使用默认参考库（首次使用时的空运行库）。
if [ -n "${PICBOOK_DB:-}" ]; then
  DB="$PICBOOK_DB"
elif [ -f "work/picbook_selection.sqlite" ]; then
  DB="work/picbook_selection.sqlite"
else
  DB="02data/structured/picbook_forge.sqlite"
fi

if [ ! -f "$DB" ]; then
  echo "找不到数据库文件：$DB"
  echo "请确认项目文件完整，或用 PICBOOK_DB 环境变量指定数据库路径。"
  read -r -p "按回车键关闭…" _
  exit 1
fi

if lsof -ti tcp:"$PORT" >/dev/null 2>&1; then
  echo "端口 ${PORT} 已被占用：Power Up 绘编可能已经在运行。"
  echo "即将直接打开浏览器：${URL}"
  echo "如果打开后页面无法使用，请先退出占用该端口的程序，再重新双击本文件。"
  open "$URL"
  read -r -p "按回车键关闭本窗口…" _
  exit 0
fi

if [ ! -f ".env.local" ] && { [ -z "${MODEL_API_KEY:-}" ] || [ -z "${MODEL_API_URL:-}" ]; }; then
  echo "提示：还没有模型服务配置。"
  echo "浏览、词表、编辑、校验、定稿等功能不受影响；"
  echo "启动后请在网页右上角「模型配置」页面填写你自己的 API 信息，"
  echo "保存后立即生效，下次启动自动读取，无需在终端设置环境变量。"
  echo
fi

echo "正在启动 Power Up 绘编…"
echo "数据库：$DB"
echo "启动后浏览器将自动打开 ${URL}（如未打开请手动访问）。"
echo "停止服务：在本窗口按 Ctrl+C。"
echo
( sleep 2 && open "$URL" ) &
exec python3 04scripts/run_webapp.py --db "$DB" --port "$PORT"
