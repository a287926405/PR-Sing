#!/bin/sh
# PR-Sing 一键安装引导脚本
# 用法: wget -qO- https://raw.githubusercontent.com/a287926405/PR-Sing/master/bootstrap.sh | sh
#   或: curl -fsSL https://raw.githubusercontent.com/a287926405/PR-Sing/master/bootstrap.sh | sh

set -e

REPO="https://github.com/a287926405/PR-Sing"
RAW="https://raw.githubusercontent.com/a287926405/PR-Sing/master"
TMPDIR="$(mktemp -d)"
cleanup() { rm -rf "$TMPDIR"; }
trap cleanup EXIT

echo "=== PR-Sing 一键安装 ==="
echo "临时目录: $TMPDIR"

# 1. 下载 install.sh
echo "下载安装脚本…"
if command -v wget >/dev/null 2>&1; then
    wget -q -O "$TMPDIR/install.sh" "$RAW/install.sh"
elif command -v curl >/dev/null 2>&1; then
    curl -fsSL -o "$TMPDIR/install.sh" "$RAW/install.sh"
else
    echo "错误: 需要 wget 或 curl"; exit 1
fi
chmod +x "$TMPDIR/install.sh"

# 2. 运行安装脚本（会自动 clone 仓库、下载 sing-box 内核、注册 systemd/脚本服务）
echo "启动安装程序…"
"$TMPDIR/install.sh" "$@"

echo ""
echo "=== 安装完成 ==="
echo "面板地址: http://<本机IP>:3001"
echo "默认密码: pr-sing  （登录后请立即修改）"
echo "数据目录: /opt/pr-sing/data"
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    echo "服务管理: systemctl status|start|stop|restart pr-sing"
else
    echo "服务管理: /usr/local/bin/pr-sing-start | pr-sing-stop"
fi