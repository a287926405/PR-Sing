#!/bin/sh
# PR-Sing 卸载脚本
set -e

INSTALL_DIR="${INSTALL_DIR:-/opt/pr-sing}"
DATA_DIR="${DATA_DIR:-/opt/pr-sing/data}"

echo "=== PR-Sing 卸载 ==="

# 0. 先问是否保留数据（此前是先删代码最后才问，而数据目录默认在代码目录内，
#    问的时候数据已经被一起删掉，询问毫无意义）
ans=""
if [ -d "$DATA_DIR" ]; then
  echo "数据目录 $DATA_DIR 包含你的节点、链和设置。"
  read -r -p "同时删除数据目录？[y/N] " ans || ans=""
fi
DELETE_DATA=0
if [ "$ans" = "y" ] || [ "$ans" = "Y" ]; then
  DELETE_DATA=1
fi

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

# 4. 保留数据时，若数据目录在安装目录内，先把它挪到安装目录之外再删代码
#    （挪到 $DATA_DIR.kept 仍在安装目录内，会被下一步 rm -rf 一起删掉）
KEEP_DIR=""
if [ "$DELETE_DATA" -eq 0 ] && [ -d "$DATA_DIR" ]; then
  case "$DATA_DIR" in
    "$INSTALL_DIR"/*)
      KEEP_DIR="${INSTALL_DIR}-data.kept"
      rm -rf "$KEEP_DIR"
      mv "$DATA_DIR" "$KEEP_DIR"
      ;;
    *)
      KEEP_DIR="$DATA_DIR"
      ;;
  esac
fi

# 5. 删除代码（删除数据时，数据目录随安装目录一并删除）
rm -rf "$INSTALL_DIR"
echo "已删除代码: $INSTALL_DIR"

if [ "$DELETE_DATA" -eq 1 ]; then
  rm -rf "$DATA_DIR" 2>/dev/null || true
  echo "已删除数据。卸载完成。"
elif [ -n "$KEEP_DIR" ]; then
  echo "数据已保留在 $KEEP_DIR（可手动删除）。卸载完成。"
else
  echo "卸载完成。"
fi
