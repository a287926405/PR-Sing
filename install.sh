#!/bin/sh
# PR-Sing 安装脚本：安装面板代码 + 下载 sing-box 内核 + 注册服务。
# 用法: ./install.sh
# 可选环境变量: INSTALL_DIR(默认 /opt/pr-sing) DATA_DIR(默认 /opt/pr-sing/data) PANEL_PORT(默认 3001)
set -e

VERSION="1.14.3"
INSTALL_DIR="${INSTALL_DIR:-/opt/pr-sing}"
DATA_DIR="${DATA_DIR:-/opt/pr-sing/data}"
PANEL_PORT="${PANEL_PORT:-3001}"
PANEL_LISTEN="${PANEL_LISTEN:-0.0.0.0}"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== PR-Sing 安装 ==="
echo "代码目录: $INSTALL_DIR"
echo "数据目录: $DATA_DIR"
echo "面板:     $PANEL_LISTEN:$PANEL_PORT"

command -v python3 >/dev/null 2>&1 || { echo "错误: 需要 python3"; exit 1; }

# ---------- 1. 安装代码 ----------
mkdir -p "$INSTALL_DIR" "$DATA_DIR/config" "$DATA_DIR/logs" "$DATA_DIR/bin"
if [ -f "$INSTALL_DIR/prsing/paths.py" ] && [ "$SRC_DIR" != "$INSTALL_DIR" ]; then
  echo "检测到 $INSTALL_DIR 已有代码，覆盖更新…"
fi
cp -r "$SRC_DIR/prsing" "$INSTALL_DIR/"
cp "$SRC_DIR/run.py" "$INSTALL_DIR/"
cp "$SRC_DIR/README.md" "$INSTALL_DIR/" 2>/dev/null || true
echo "代码安装完成"

# ---------- 2. sing-box 内核 ----------
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64)          AS="linux-amd64" ;;
  aarch64|arm64)   AS="linux-arm64-v8a" ;;
  armv7l)          AS="linux-armv7-32" ;;
  i386|i686)       AS="linux-386" ;;
  *)               AS="" ;;
esac
SB="$DATA_DIR/bin/sing-box"
if [ -x "$SB" ]; then
  echo "内核已存在: $SB ($("$SB" version 2>/dev/null | head -1))"
else
  [ -n "$AS" ] || { echo "错误: 不支持的架构 $ARCH，请手动放置 sing-box 到 $SB"; exit 1; }
  echo "下载 sing-box v$VERSION ($AS)…"
  TMP="$(mktemp -d)"
  for CAND in "sing-box-${AS}.tar.gz" "sing-box-${AS}-glibc.tar.gz"; do
    URL="https://github.com/SagerNet/sing-box/releases/download/v${VERSION}/${CAND}"
    if wget -q -O "$TMP/sb.tar.gz" "$URL" 2>/dev/null || curl -fsSL -o "$TMP/sb.tar.gz" "$URL" 2>/dev/null; then
      tar -xzf "$TMP/sb.tar.gz" -C "$TMP"
      BIN="$(find "$TMP" -type f -name "sing-box" | head -1)"
      [ -n "$BIN" ] || BIN="$(find "$TMP" -type f -name "sing-box*" ! -name "*.txt" | head -1)"
      if [ -n "$BIN" ]; then
        cp "$BIN" "$SB"
        chmod +x "$SB"
        echo "内核安装完成: $SB"
        break
      fi
    fi
  done
  rm -rf "$TMP"
  [ -x "$SB" ] || { echo "错误: sing-box 下载失败，请手动下载 v$VERSION 放到 $SB 后重跑本脚本"; exit 1; }
fi
"$SB" version | head -1

# ---------- 3. 服务 ----------
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
  PY="$(command -v python3)"
  cat > /etc/systemd/system/pr-sing.service <<EOF
[Unit]
Description=PR-Sing sing-box transparent proxy panel
After=network.target

[Service]
Environment=PRSING_HOME=$DATA_DIR
ExecStart=$PY $INSTALL_DIR/run.py --listen $PANEL_LISTEN --port $PANEL_PORT
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable pr-sing >/dev/null 2>&1
  systemctl restart pr-sing
  echo "systemd 服务已启用: pr-sing"
else
  cat > /usr/local/bin/pr-sing-start <<EOF
#!/bin/sh
export PRSING_HOME=$DATA_DIR
nohup python3 $INSTALL_DIR/run.py --listen $PANEL_LISTEN --port $PANEL_PORT >> $DATA_DIR/logs/panel.out 2>&1 &
EOF
  chmod +x /usr/local/bin/pr-sing-start
  cat > /usr/local/bin/pr-sing-stop <<'EOF'
#!/bin/sh
for f in "$PRSING_HOME/config/panel.pid" "$PRSING_HOME/config/core.pid"; do
  [ -f "$f" ] && kill "$(cat "$f")" 2>/dev/null
done
EOF
  chmod +x /usr/local/bin/pr-sing-stop
  echo "未检测到 systemd，使用脚本方式启动"
  /usr/local/bin/pr-sing-start
fi

sleep 2
echo ""
echo "=== 安装完成 ==="
echo "面板地址:   http://<本机IP>:$PANEL_PORT"
echo "默认密码:   pr-sing  （登录后请到 设置 页修改）"
echo "数据目录:   $DATA_DIR"
if [ -d /run/systemd/system ] && command -v systemctl >/dev/null 2>&1; then
  echo "服务状态:   systemctl status pr-sing"
else
  echo "启动/停止:  /usr/local/bin/pr-sing-start | pr-sing-stop"
fi
