#!/bin/sh
# PR-Sing 一键引导脚本：下载 manage.sh 并转交其部署（结构与 SMBox 一致）。
# 用法: wget -qO- https://raw.githubusercontent.com/a287926405/PR-Sing/master/bootstrap.sh | sh
#       或通过代理: GH_PROXY=https://gh-proxy.com/ wget -qO- ... | sh
set -e

REPO="a287926405/PR-Sing"
RAW="https://raw.githubusercontent.com/${REPO}/master"
export GH_PROXY="${GH_PROXY:-https://gh-proxy.com/}"

log() { echo "=== $* ==="; }

if command -v wget >/dev/null 2>&1; then
  DOWNLOAD="wget -q -O"
elif command -v curl >/dev/null 2>&1; then
  DOWNLOAD="curl -fsSL -o"
else
  echo "错误：需要 wget 或 curl"; exit 1
fi

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

log "下载管理脚本 manage.sh"
$DOWNLOAD "$TMPDIR/manage.sh" "${GH_PROXY}${RAW}/manage.sh"

log "启动管理脚本（默认执行 deploy，可通过参数改命令）"
if [ $# -eq 0 ]; then
  set -- deploy
fi
exec bash "$TMPDIR/manage.sh" "$@"
