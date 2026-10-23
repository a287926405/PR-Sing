#!/bin/sh
# PR-Sing 安装脚本
set -e

REPO="a287926405/PR-Sing"
GH="https://github.com/${REPO}"
GH_PROXY="${GH_PROXY:-https://gh-proxy.com/}"

log() { echo "=== $* ==="; }

INSTALL_DIR="${INSTALL_DIR:-/opt/pr-sing}"
DATA_DIR="${DATA_DIR:-/opt/pr-sing/data}"
PANEL_PORT="${PANEL_PORT:-3001}"
PANEL_LISTEN="${PANEL_LISTEN:-0.0.0.0}"
SB_VER="${SB_VER:-1.14.3}"

# ---- 定位源码目录（默认：安装脚本所在目录；可由 bootstrap 预置） ----
SRC_DIR="${SRC_DIR:-}"
if [ -z "$SRC_DIR" ]; then
  SRC_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"
fi
if [ ! -d "$SRC_DIR/prsing" ]; then
  echo "错误：未找到 PR-Sing 源码（缺少 prsing/ 目录）。"
  echo "请使用 bootstrap.sh 一键安装，或先下载仓库源码后再运行 install.sh。"
  exit 1
fi

# ---- 下载 sing-box 内核 ----
KERNEL_ARCH="$(uname -m)"
case "$KERNEL_ARCH" in
  aarch64|arm64) KERNEL_ARCH_NAME="arm64" ;;
  x86_64|amd64)  KERNEL_ARCH_NAME="amd64" ;;
  *) echo "不支持的架构：$KERNEL_ARCH"; exit 1 ;;
esac

SB_FILE="sing-box-${SB_VER}-linux-${KERNEL_ARCH_NAME}.tar.gz"
SB_URL="${GH}/releases/download/v${SB_VER}/${SB_FILE}"

log "下载 sing-box 内核 v${SB_VER} ($KERNEL_ARCH)"
mkdir -p "$INSTALL_DIR/bin"
TMP_KERNEL="$(mktemp -d)"
cd "$TMP_KERNEL"
if command -v wget >/dev/null 2>&1; then
  wget -q -O kernel.tar.gz "${GH_PROXY}${SB_URL}"
elif command -v curl >/dev/null 2>&1; then
  curl -fsSL -o kernel.tar.gz "${GH_PROXY}${SB_URL}"
fi
tar -xzf kernel.tar.gz --strip-components=1 "sing-box-${SB_VER}-linux-${KERNEL_ARCH_NAME}/sing-box"
cp sing-box "$INSTALL_DIR/bin/sing-box"
chmod +x "$INSTALL_DIR/bin/sing-box"
rm -rf "$TMP_KERNEL"
"$INSTALL_DIR/bin/sing-box" version

# ---- 复制面板源码到 $INSTALL_DIR ----
log "复制面板源码到 $INSTALL_DIR"
cp -r "$SRC_DIR/prsing" "$INSTALL_DIR/"
cp "$SRC_DIR/run.py" "$INSTALL_DIR/"
cp "$SRC_DIR/README.md" "$INSTALL_DIR/"
cp "$SRC_DIR/LICENSE" "$INSTALL_DIR/"
cp "$SRC_DIR/.gitignore" "$INSTALL_DIR/" 2>/dev/null || true
cp "$SRC_DIR/uninstall.sh" "$INSTALL_DIR/" 2>/dev/null || true
rm -rf "$SRC_DIR"

# ---- 生成 bootstrap 启动脚本 ----
log "生成启动脚本"
cat > "$INSTALL_DIR/bootstrap.sh" <<EOF
#!/bin/sh
set -e
cd "$INSTALL_DIR"
PRSING_HOME="${DATA_DIR}" python3 run.py --listen "${PANEL_LISTEN}" --port "${PANEL_PORT}" "\$@"
EOF
chmod +x "$INSTALL_DIR/bootstrap.sh"

# ---- 注册系统服务 ----
log "注册系统服务"
if command -v systemctl >/dev/null 2>&1 && [ -d /etc/systemd/system ]; then
  cat > /etc/systemd/system/pr-sing.service <<EOF
[Unit]
Description=PR-Sing Panel
After=network.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
Environment=PRSING_HOME=$DATA_DIR
ExecStart=$INSTALL_DIR/bootstrap.sh
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable pr-sing.service
  systemctl start pr-sing.service
  echo "服务已注册并启动：pr-sing.service"
elif [ -d /usr/local/bin ]; then
  cat > /usr/local/bin/pr-sing-start <<EOF
#!/bin/sh
PRSING_HOME="$DATA_DIR" python3 "$INSTALL_DIR/run.py" --listen "$PANEL_LISTEN" --port "$PANEL_PORT" &
EOF
  chmod +x /usr/local/bin/pr-sing-start
  echo "已写入 /usr/local/bin/pr-sing-start，请手动启动或加入开机自启。"
else
  echo "未检测到 systemd，请手动运行：$INSTALL_DIR/bootstrap.sh"
fi

echo "=== 安装完成 ==="
echo "面板地址：http://<本机IP>:${PANEL_PORT}"
echo "默认密码：pr-sing"
echo "控制脚本：$INSTALL_DIR/bootstrap.sh"