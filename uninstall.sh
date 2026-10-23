#!/bin/sh
# PR-Sing 卸载脚本（新版单目录布局：代码与数据同在 $INSTALL_DIR 下，
# 数据为其下的 config/ data/ logs/ bin/ 子目录）
set -e

INSTALL_DIR="${INSTALL_DIR:-}"
# 未显式指定时，若 manage.sh 记录过自定义安装目录则采用记录值
if [ -z "$INSTALL_DIR" ] && [ -f /etc/pr-sing-manage.conf ]; then
  # shellcheck disable=SC1091
  . /etc/pr-sing-manage.conf 2>/dev/null || true
fi
INSTALL_DIR="${INSTALL_DIR:-/opt/pr-sing}"
SERVICE_NAME="pr-sing"

echo "=== PR-Sing 卸载 ==="
echo "安装目录: $INSTALL_DIR"

# 0. 先问是否保留数据（保留 = 只删代码与服务，数据子目录原地保留）
ans=""
read -r -p "同时删除全部数据（config/data/logs/bin）？[y/N] " ans || ans=""
DELETE_DATA=0
if [ "$ans" = "y" ] || [ "$ans" = "Y" ]; then
  DELETE_DATA=1
fi

# 1. 停止服务
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
  systemctl stop "$SERVICE_NAME" 2>/dev/null || true
  systemctl disable "$SERVICE_NAME" 2>/dev/null || true
  rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
  systemctl daemon-reload 2>/dev/null || true
  echo "已停止并移除 systemd 服务"
elif command -v rc-service >/dev/null 2>&1 && [ -f "/etc/init.d/${SERVICE_NAME}" ]; then
  rc-service "$SERVICE_NAME" stop 2>/dev/null || true
  rc-update del "$SERVICE_NAME" default 2>/dev/null || true
  rm -f "/etc/init.d/${SERVICE_NAME}"
  echo "已停止并移除 OpenRC 服务"
fi

# 2. 停止进程
for f in "$INSTALL_DIR/config/panel.pid" "$INSTALL_DIR/config/core.pid"; do
  if [ -f "$f" ]; then
    kill "$(cat "$f")" 2>/dev/null || true
    rm -f "$f"
  fi
done
sleep 1

# 3. 移除快捷命令
rm -f /usr/local/bin/pr-sing-start /usr/local/bin/pr-sing-stop /usr/local/bin/pr-sing-manage

# 4. 删除代码（及按选择删除数据）
if [ "$DELETE_DATA" -eq 1 ]; then
  rm -rf "$INSTALL_DIR"
  rm -f /etc/pr-sing-manage.conf
  echo "已删除代码与全部数据。卸载完成。"
else
  rm -rf "$INSTALL_DIR/prsing"
  rm -f "$INSTALL_DIR/run.py" "$INSTALL_DIR/manage.sh" "$INSTALL_DIR/pr-sing" \
        "$INSTALL_DIR/bootstrap.sh" "$INSTALL_DIR/install.sh" "$INSTALL_DIR/uninstall.sh"
  echo "已删除代码；数据保留在 $INSTALL_DIR 的 config/data/logs/bin 子目录中。卸载完成。"
fi
