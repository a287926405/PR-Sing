#!/bin/sh
# PR-Sing 安装脚本（兼容入口）：实际安装逻辑已统一到 manage.sh，
# 本脚本仅做转发，等价于 manage.sh deploy --dir "$INSTALL_DIR"。
set -e

GH_PROXY="${GH_PROXY:-}"
INSTALL_DIR="${INSTALL_DIR:-/opt/pr-sing}"
SCRIPT_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"

if [ -n "${PANEL_PORT:-}" ]; then
  export PRSING_PANEL_PORT="$PANEL_PORT"
fi

if [ -f "$SCRIPT_DIR/manage.sh" ]; then
  exec bash "$SCRIPT_DIR/manage.sh" deploy --dir "$INSTALL_DIR"
fi

# 源码不在本地（被单独下载执行时）：拉取 manage.sh 再部署
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT
PREFIX="${GH_PROXY:-https://gh-proxy.com/}"
URL="${PREFIX}https://raw.githubusercontent.com/a287926405/PR-Sing/master/manage.sh"
echo "=== 下载管理脚本 ==="
if command -v wget >/dev/null 2>&1; then
  wget -q -O "$TMPDIR/manage.sh" "$URL"
elif command -v curl >/dev/null 2>&1; then
  curl -fsSL -o "$TMPDIR/manage.sh" "$URL"
else
  echo "错误：需要 wget 或 curl"; exit 1
fi
exec bash "$TMPDIR/manage.sh" deploy --dir "$INSTALL_DIR"
