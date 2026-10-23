#!/bin/sh
# PR-Sing 卸载脚本
set -e

INSTALL_DIR="${INSTALL_DIR:-/opt/pr-sing}"
DATA_DIR="${DATA_DIR:-/opt/pr-sing/data}"

echo "=== PR-Sing 卸载 ==="

# 1. 停止服务
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
  systemctl stop pr-sing 2>/dev/null || true
  systemctl disable pr-sing 2>/dev/null || true
  rm -f /etc/systemd/system/pr-sing.service
  systemctl daemon-reload 2>/dev/null || true
  echo "已停止并移除 systemd 服务"
fi

# 2. 停止进程
for f in "$DATA_DIR/config/panel.pid" "$DATA_DIR/config/core.pid"; do
  if [ -f "$f" ]; then
    kill "$(cat "$f")" 2>/dev/null || true
    rm -f "$f"
  fi
done
sleep 1

# 3. 移除启动脚本
rm -f /usr/local/bin/pr-sing-start /usr/local/bin/pr-sing-stop

# 4. 删除代码
rm -rf "$INSTALL_DIR"
echo "已删除代码: $INSTALL_DIR"

# 5. 数据（含节点/链/配置）
echo "数据目录 $DATA_DIR 包含你的节点、链和设置。"
read -r -p "同时删除数据目录？[y/N] " ans
if [ "$ans" = "y" ] || [ "$ans" = "Y" ]; then
  rm -rf "$DATA_DIR"
  echo "已删除数据。卸载完成。"
else
  echo "数据已保留在 $DATA_DIR（可手动删除）。卸载完成。"
fi
