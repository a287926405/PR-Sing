#!/bin/sh
# PR-Sing 一键引导脚本
# 用法: wget -qO- https://raw.githubusercontent.com/a287926405/PR-Sing/master/bootstrap.sh | sh
#       或通过代理: wget -qO- https://gh-proxy.com/https://raw.githubusercontent.com/... | sh
set -e

REPO="a287926405/PR-Sing"
RAW="https://raw.githubusercontent.com/${REPO}/master"
GH="https://github.com/${REPO}"
export GH_PROXY="${GH_PROXY:-https://gh-proxy.com/}"

log() { echo "=== $* ==="; }

# 检查网络工具
if command -v wget >/dev/null 2>&1; then
  DOWNLOAD="wget -q -O"
elif command -v curl >/dev/null 2>&1; then
  DOWNLOAD="curl -fsSL -o"
else
  echo "错误：需要 wget 或 curl"; exit 1
fi

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

# 1. 下载 install.sh
log "下载安装脚本"
$DOWNLOAD "$TMPDIR/install.sh" "${GH_PROXY}${RAW}/install.sh"

# 2. 下载仓库源码包
log "下载仓库源码"
$DOWNLOAD "$TMPDIR/repo.zip" "${GH_PROXY}${GH}/archive/master.zip"

# 3. 解压并定位源码目录
log "解压仓库源码"
python3 - "$TMPDIR/repo.zip" "$TMPDIR/unpacked" <<'PYEOF'
import zipfile, sys
zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])
PYEOF

REPO_DIR="$(find "$TMPDIR/unpacked" -maxdepth 1 -type d -name '*PR-Sing*' -print -quit)"
if [ -z "$REPO_DIR" ] || [ ! -f "$REPO_DIR/install.sh" ]; then
  echo "错误：解压后未找到 PR-Sing 源码目录"; exit 1
fi

# 4. 启动安装（install.sh 自身会以脚本所在目录为代码目录）
log "启动安装程序"
sh "$REPO_DIR/install.sh" "$@"
