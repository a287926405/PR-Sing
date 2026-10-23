#!/bin/bash
# PR-Sing 安装管理脚本（结构与 SMBox manage.sh 对齐：单文件、彩色菜单、
# deploy 自动安装/升级、systemd/OpenRC 双服务、三下载源、--dir 指定目录；
# 实现为 PR-Sing 自有代码，代理功能由 prsing/ Python 引擎提供，
# 链式代理模块完整保留并可在「功能」菜单中操作。）
# shellcheck shell=bash

VERSION="1.1.1"

# ==================== 配置 ====================
REPO="a287926405/PR-Sing"
SB_VER="1.14.3"
# 下载源: 1=GitHub直连 2=gh-proxy.com 3=ghfast.top（GH_PROXY 环境变量优先）
DOWNLOAD_SOURCE=2
# 默认安装目录（SMBox 式单目录布局：代码与数据同在安装目录下）
INSTALL_DIR="/opt/pr-sing"
# 服务名称
SERVICE_NAME="pr-sing"
# 管理脚本状态文件（记住安装目录与下载源）
MANAGE_CONF="/etc/pr-sing-manage.conf"

# ==================== 工具函数 ====================
info() {
    echo -e "\033[32m[信息]\033[0m $1"
}

error() {
    echo -e "\033[31m[错误]\033[0m $1"
}

warn() {
    echo -e "\033[0;33m[警告]\033[0m $1"
}

red() {
    echo -e "\033[31m$1\033[0m"
}

yellow() {
    echo -e "\033[0;33m$1\033[0m"
}

blue() {
    echo -e "\033[34m$1\033[0m"
}

green() {
    echo -e "\033[32m$1\033[0m"
}

cyan() {
    echo -e "\033[36m$1\033[0m"
}

# ==================== 状态持久化 ====================
load_manage_conf() {
    if [ -f "$MANAGE_CONF" ]; then
        # shellcheck disable=SC1090
        . "$MANAGE_CONF" 2>/dev/null || true
    fi
}

save_manage_conf() {
    mkdir -p "$(dirname "$MANAGE_CONF")" 2>/dev/null || return 0
    cat > "$MANAGE_CONF" <<EOF
INSTALL_DIR="$INSTALL_DIR"
DOWNLOAD_SOURCE=$DOWNLOAD_SOURCE
EOF
}

# ==================== 系统检测 ====================
OS=""
ARCH=""
ARCH_NAME=""
INIT_SYSTEM=""

check_root() {
    if [ "$(id -u)" != "0" ]; then
        error "此脚本需要以 root 权限运行"
        exit 1
    fi
}

detect_os() {
    # 只取 ID 字段，不 source 整个 os-release（其 VERSION= 会覆盖脚本的 VERSION）
    local os_id=""
    if [ -f /etc/os-release ]; then
        os_id=$(grep '^ID=' /etc/os-release | head -n 1 | cut -d= -f2 | tr -d '"')
    fi
    case "$os_id" in
        debian|ubuntu|raspbian|armbian) OS="debian" ;;
        alpine) OS="alpine" ;;
        arch|manjaro) OS="arch" ;;
        openwrt) OS="openwrt" ;;
        "") OS="unknown" ;;
        *) OS="$os_id" ;;
    esac
}

detect_arch() {
    case "$(uname -m)" in
        x86_64|amd64) ARCH="amd64"; ARCH_NAME="x86_64" ;;
        aarch64|arm64) ARCH="arm64"; ARCH_NAME="aarch64" ;;
        *) ARCH=""; ARCH_NAME="$(uname -m)" ;;
    esac
}

detect_init() {
    if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
        INIT_SYSTEM="systemd"
    elif command -v rc-service >/dev/null 2>&1; then
        INIT_SYSTEM="openrc"
    else
        INIT_SYSTEM="none"
    fi
}

validate_install_dir() {
    case "$INSTALL_DIR" in
        /*) ;;
        *) error "安装目录必须是绝对路径: $INSTALL_DIR"; return 1 ;;
    esac
    case "$INSTALL_DIR" in
        /|/etc|/usr|/bin|/sbin|/lib|/var|/boot|/proc|/sys|/dev)
            error "安装目录不安全: $INSTALL_DIR"; return 1 ;;
    esac
    return 0
}

# ==================== 下载 ====================
src_prefix() {
    if [ -n "${GH_PROXY:-}" ]; then
        printf '%s' "$GH_PROXY"
        return
    fi
    case $DOWNLOAD_SOURCE in
        2) printf '%s' "https://gh-proxy.com/" ;;
        3) printf '%s' "https://ghfast.top/" ;;
        *) printf '%s' "" ;;
    esac
}

download() {
    # download <url> <dest>
    local url="$1" dest="$2"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL --connect-timeout 20 -o "$dest" "$url"
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O "$dest" "$url"
    else
        error "需要 curl 或 wget 下载文件"
        return 1
    fi
}

repo_archive_url() {
    printf '%shttps://github.com/%s/archive/refs/heads/master.zip' "$(src_prefix)" "$REPO"
}

kernel_url() {
    printf '%shttps://github.com/SagerNet/sing-box/releases/download/v%s/sing-box-%s-linux-%s.tar.gz' \
        "$(src_prefix)" "$SB_VER" "$SB_VER" "$ARCH"
}

# ==================== 依赖与系统环境 ====================
install_dependencies() {
    local missing=""
    command -v python3 >/dev/null 2>&1 || missing="$missing python3"
    command -v curl >/dev/null 2>&1 || command -v wget >/dev/null 2>&1 || missing="$missing curl"
    command -v tar >/dev/null 2>&1 || missing="$missing tar"
    if [ -z "$missing" ]; then
        return 0
    fi
    info "正在安装依赖:$missing"
    case "$OS" in
        debian)
            apt-get update -qq || true
            # shellcheck disable=SC2086
            apt-get install -y -qq python3 curl tar ca-certificates || true
            ;;
        alpine)
            # shellcheck disable=SC2086
            apk add --no-cache python3 curl tar ca-certificates || true
            ;;
        arch)
            # shellcheck disable=SC2086
            pacman -Sy --noconfirm python curl tar || true
            ;;
        *)
            warn "未知系统，请自行确保已安装:$missing"
            ;;
    esac
    command -v python3 >/dev/null 2>&1 || { error "python3 不可用，无法继续"; return 1; }
    return 0
}

configure_system() {
    # 轻量系统环境配置：管理脚本快捷命令 + TUN 设备提示（不改动系统网络配置）
    if [ -f "$INSTALL_DIR/manage.sh" ] && [ -d /usr/local/bin ]; then
        ln -sf "$INSTALL_DIR/manage.sh" /usr/local/bin/pr-sing-manage 2>/dev/null || true
    fi
    if [ ! -e /dev/net/tun ]; then
        warn "未检测到 /dev/net/tun：如需 TUN 透明代理请确认内核 TUN 已启用（面板默认仅开 Mixed 入站，不受影响）"
    fi
    info "系统环境配置完成"
}

# ==================== 服务 ====================
is_installed() {
    [ -f "$INSTALL_DIR/run.py" ] && [ -f "$INSTALL_DIR/pr-sing" ]
}

create_launcher() {
    cat > "$INSTALL_DIR/pr-sing" <<'LAUNCHEOF'
#!/bin/sh
# PR-Sing 启动器：服务与命令行共用。PRSING_HOME 固定为安装目录（单目录布局）。
cd "$(dirname "$0")" || exit 1
INSTALL_DIR="$(pwd)"
export PRSING_HOME="$INSTALL_DIR"
# 下载源前缀（与 manage.sh 选择一致，供面板规则库下载使用）
if [ -z "${PRSING_DL_PREFIX:-}" ]; then
    if [ -n "${GH_PROXY:-}" ]; then
        PRSING_DL_PREFIX="$GH_PROXY"
    elif [ -f /etc/pr-sing-manage.conf ]; then
        _src=$(grep '^DOWNLOAD_SOURCE=' /etc/pr-sing-manage.conf 2>/dev/null | cut -d= -f2)
        case "$_src" in
            2) PRSING_DL_PREFIX="https://gh-proxy.com/" ;;
            3) PRSING_DL_PREFIX="https://ghfast.top/" ;;
            *) PRSING_DL_PREFIX="" ;;
        esac
    fi
    export PRSING_DL_PREFIX
fi
if [ "$1" = "run" ]; then
    shift
    if [ -n "${PRSING_PANEL_PORT:-}" ]; then
        exec python3 run.py --port "$PRSING_PANEL_PORT" "$@"
    fi
    exec python3 run.py "$@"
elif [ "$1" = "cli" ]; then
    shift
    exec python3 -m prsing.cli "$@"
else
    exec python3 run.py "$@"
fi
LAUNCHEOF
    chmod +x "$INSTALL_DIR/pr-sing"
}

create_systemd_service() {
    info "正在创建 systemd 服务..."
    cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF || return 1
[Unit]
Description=PR-Sing - Sing-box Proxy Panel
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}
Environment="PRSING_HOME=${INSTALL_DIR}"
Environment="PRSING_DL_PREFIX=$(src_prefix)"
ExecStart="${INSTALL_DIR}/pr-sing" run
KillMode=mixed
TimeoutStopSec=30s
Restart=on-failure
RestartSec=5
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload || return 1
    systemctl enable "${SERVICE_NAME}" || return 1
    info "systemd 服务创建完成"
}

create_openrc_service() {
    info "正在创建 OpenRC 服务..."
    cat > "/etc/init.d/${SERVICE_NAME}" <<EOF || return 1
#!/sbin/openrc-run

name="pr-sing"
description="PR-Sing - Sing-box Proxy Panel"

command="${INSTALL_DIR}/pr-sing"
command_args="run"
command_background="yes"
pidfile="/run/\${RC_SVCNAME}.pid"
start_stop_daemon_args="--chdir ${INSTALL_DIR}"

depend() {
    need net
    after firewall
}
EOF
    chmod +x "/etc/init.d/${SERVICE_NAME}" || return 1
    rc-update add "${SERVICE_NAME}" default || return 1
    info "OpenRC 服务创建完成"
}

create_service() {
    case $INIT_SYSTEM in
        systemd) create_systemd_service ;;
        openrc) create_openrc_service ;;
        *) warn "未检测到 systemd/OpenRC，跳过服务注册；可手动运行: $INSTALL_DIR/pr-sing run" ;;
    esac
}

remove_service() {
    case $INIT_SYSTEM in
        systemd)
            systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
            systemctl disable "${SERVICE_NAME}" 2>/dev/null || true
            rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
            systemctl daemon-reload 2>/dev/null || true
            ;;
        openrc)
            rc-service "${SERVICE_NAME}" stop 2>/dev/null || true
            rc-update del "${SERVICE_NAME}" default 2>/dev/null || true
            rm -f "/etc/init.d/${SERVICE_NAME}"
            ;;
    esac
}

panel_pids() {
    local f
    for f in "$INSTALL_DIR/config/panel.pid" "$INSTALL_DIR/config/core.pid"; do
        [ -f "$f" ] && cat "$f"
    done
}

start_service() {
    if ! is_installed; then
        error "PR-Sing 未安装，请先部署"
        return 1
    fi
    case $INIT_SYSTEM in
        systemd) systemctl start "${SERVICE_NAME}" ;;
        openrc) rc-service "${SERVICE_NAME}" start ;;
        *)
            if [ -f "$INSTALL_DIR/config/panel.pid" ] && kill -0 "$(cat "$INSTALL_DIR/config/panel.pid")" 2>/dev/null; then
                info "面板已在运行"
                return 0
            fi
            mkdir -p "$INSTALL_DIR/logs"
            nohup "$INSTALL_DIR/pr-sing" run >>"$INSTALL_DIR/logs/panel.out" 2>&1 &
            info "面板已启动（无服务管理器，nohup 模式）"
            ;;
    esac
}

stop_service() {
    case $INIT_SYSTEM in
        systemd) systemctl stop "${SERVICE_NAME}" 2>/dev/null || true ;;
        openrc) rc-service "${SERVICE_NAME}" stop 2>/dev/null || true ;;
        *)
            local pid
            for pid in $(panel_pids); do
                kill "$pid" 2>/dev/null || true
            done
            ;;
    esac
    # 兜底：按 pid 文件停掉残留的面板/内核进程
    local pid
    for pid in $(panel_pids); do
        kill "$pid" 2>/dev/null || true
    done
    sleep 1
}

restart_service() {
    stop_service
    sleep 1
    start_service
}

check_service_status() {
    case $INIT_SYSTEM in
        systemd) systemctl status "${SERVICE_NAME}" --no-pager || true ;;
        openrc) rc-service "${SERVICE_NAME}" status || true ;;
        *)
            if [ -f "$INSTALL_DIR/config/panel.pid" ] && kill -0 "$(cat "$INSTALL_DIR/config/panel.pid")" 2>/dev/null; then
                green "面板: 运行中 (PID $(cat "$INSTALL_DIR/config/panel.pid"))"
            else
                yellow "面板: 未运行"
            fi
            ;;
    esac
    if is_installed; then
        echo ""
        run_cli status || true
    fi
}

# ==================== CLI 透传 ====================
run_cli() {
    if ! is_installed; then
        error "PR-Sing 未安装，请先部署"
        return 1
    fi
    (cd "$INSTALL_DIR" && PRSING_HOME="$INSTALL_DIR" python3 -m prsing.cli "$@")
}

# ==================== 部署 ====================
show_access_info() {
    local ip
    ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    [ -z "$ip" ] && ip="<本机IP>"
    echo ""
    green "=========================================="
    green "           PR-Sing 安装成功！"
    green "=========================================="
    echo ""
    yellow "访问地址: http://${ip}:3001"
    blue "默认密码: pr-sing（登录后请立即修改）"
    echo ""
    yellow "服务管理命令:"
    case $INIT_SYSTEM in
        systemd)
            echo "  启动: systemctl start ${SERVICE_NAME}"
            echo "  停止: systemctl stop ${SERVICE_NAME}"
            echo "  重启: systemctl restart ${SERVICE_NAME}"
            echo "  状态: systemctl status ${SERVICE_NAME}"
            ;;
        openrc)
            echo "  启动: rc-service ${SERVICE_NAME} start"
            echo "  停止: rc-service ${SERVICE_NAME} stop"
            echo "  重启: rc-service ${SERVICE_NAME} restart"
            echo "  状态: rc-service ${SERVICE_NAME} status"
            ;;
        *)
            echo "  启动: $INSTALL_DIR/pr-sing run"
            ;;
    esac
    echo "  管理: pr-sing-manage（或 bash $INSTALL_DIR/manage.sh）"
    echo "  链式代理: 面板「链式代理」页，或 manage.sh 菜单 13"
    echo ""
}

deploy_smbox() {
    local channel="${1:-release}"
    validate_install_dir || return 1
    if [ -z "$ARCH" ]; then
        error "不支持的架构: $(uname -m)"
        return 1
    fi
    install_dependencies || return 1

    local upgrade=0
    is_installed && upgrade=1
    if [ "$channel" = "beta" ]; then
        info "部署 PR-Sing (测试版通道，当前与稳定版同源 master)"
    else
        info "部署 PR-Sing (稳定版)"
    fi
    [ "$upgrade" = 1 ] && info "检测到已安装，将执行升级（保留配置与数据）"

    local tmp
    tmp=$(mktemp -d) || return 1
    info "下载源码包..."
    if ! download "$(repo_archive_url)" "$tmp/repo.zip"; then
        error "源码下载失败（下载源: $DOWNLOAD_SOURCE，可在菜单 9 切换）"
        rm -rf "$tmp"
        return 1
    fi
    python3 - "$tmp/repo.zip" "$tmp/unpacked" <<'PYEOF' || { error "解压失败"; rm -rf "$tmp"; return 1; }
import zipfile, sys
zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])
PYEOF
    local src
    src=$(find "$tmp/unpacked" -maxdepth 1 -type d -name 'PR-Sing*' -print -quit)
    if [ -z "$src" ] || [ ! -d "$src/prsing" ]; then
        error "源码包结构异常"
        rm -rf "$tmp"
        return 1
    fi

    # 升级时先停服务，避免覆盖正在运行的文件
    if [ "$upgrade" = 1 ]; then
        stop_service || true
    fi

    info "安装代码到 $INSTALL_DIR ..."
    mkdir -p "$INSTALL_DIR"
    rm -rf "$INSTALL_DIR/prsing"
    cp -r "$src/prsing" "$INSTALL_DIR/"
    cp "$src/run.py" "$src/manage.sh" "$src/README.md" "$src/LICENSE" "$INSTALL_DIR/"
    cp "$src/bootstrap.sh" "$src/install.sh" "$src/uninstall.sh" "$INSTALL_DIR/" 2>/dev/null || true
    cp "$src/.gitignore" "$INSTALL_DIR/" 2>/dev/null || true
    chmod +x "$INSTALL_DIR/manage.sh"

    info "下载 sing-box 内核 v$SB_VER ($ARCH_NAME)..."
    mkdir -p "$INSTALL_DIR/bin"
    if ! download "$(kernel_url)" "$tmp/kernel.tar.gz"; then
        error "内核下载失败"
        rm -rf "$tmp"
        return 1
    fi
    tar -xzf "$tmp/kernel.tar.gz" -C "$tmp" "sing-box-${SB_VER}-linux-${ARCH}/sing-box" || { error "内核解压失败"; rm -rf "$tmp"; return 1; }
    cp "$tmp/sing-box-${SB_VER}-linux-${ARCH}/sing-box" "$INSTALL_DIR/bin/sing-box"
    chmod +x "$INSTALL_DIR/bin/sing-box"
    rm -rf "$tmp"

    create_launcher
    create_service || { error "服务创建失败"; return 1; }
    save_manage_conf
    start_service || { error "服务启动失败"; return 1; }
    info "PR-Sing 部署完成！"
    show_access_info
}

# ==================== 卸载 / 重置 ====================
uninstall_smbox() {
    if ! is_installed; then
        error "PR-Sing 未安装"
        return 1
    fi
    echo ""
    red "警告：此操作将卸载 PR-Sing 并删除全部数据（节点/链/配置）！"
    echo ""
    read -r -p "确认卸载？(y/N): " confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        info "已取消卸载"
        return 0
    fi
    stop_service || true
    remove_service
    rm -rf "${INSTALL_DIR:?}"
    rm -f /usr/local/bin/pr-sing-manage
    if grep -q "^INSTALL_DIR=\"$INSTALL_DIR\"" "$MANAGE_CONF" 2>/dev/null; then
        rm -f "$MANAGE_CONF"
    fi
    info "PR-Sing 已卸载"
}

reset_config() {
    if ! is_installed; then
        error "PR-Sing 未安装"
        return 1
    fi
    echo ""
    red "警告：此操作将重置所有配置和日志！"
    echo ""
    read -r -p "确认重置？请输入 YES 继续: " confirm
    if [ "$confirm" != "YES" ]; then
        info "已取消重置"
        return 0
    fi
    info "正在重置 PR-Sing 配置..."
    stop_service || true
    rm -rf "${INSTALL_DIR:?}/config" || return 1
    rm -rf "${INSTALL_DIR:?}/logs" || return 1
    start_service || return 1
    info "PR-Sing 配置重置完成"
}

# ==================== 设置 ====================
select_download_source() {
    echo ""
    echo "选择下载源:"
    echo "  1. GitHub 直连"
    echo "  2. gh-proxy.com"
    echo "  3. ghfast.top"
    echo ""
    read -r -p "请输入选项 [1-3] (当前: $DOWNLOAD_SOURCE): " s
    case "$s" in
        1|2|3)
            DOWNLOAD_SOURCE=$s
            save_manage_conf
            info "下载源已切换为: $s"
            ;;
        *)
            error "无效的选项"
            ;;
    esac
}

select_install_dir() {
    echo ""
    read -r -p "请输入新的安装目录 (当前: $INSTALL_DIR): " new_dir
    if [ -n "$new_dir" ]; then
        local previous_dir="$INSTALL_DIR"
        INSTALL_DIR="$new_dir"
        validate_install_dir || { INSTALL_DIR="$previous_dir"; return 1; }
        save_manage_conf
        info "安装目录已设置为: $INSTALL_DIR（下次部署生效）"
    fi
}

# ==================== 迁移 ====================
detect_old_installation() {
    # 旧版布局：PRSING_HOME 嵌套在 <某目录>/data 下（含 config/settings.json）
    local cand
    for cand in "$INSTALL_DIR/data" /opt/pr-sing/data; do
        if [ -f "$cand/config/settings.json" ] && [ "$cand" != "$INSTALL_DIR" ]; then
            printf '%s' "$cand"
            return 0
        fi
    done
    return 1
}

migrate_old_installation() {
    local old_path="$1"
    if [ ! -f "$old_path/config/settings.json" ]; then
        error "在 $old_path 未找到旧版本数据（缺少 config/settings.json）"
        return 1
    fi
    if [ "$old_path" = "$INSTALL_DIR" ]; then
        error "旧版本路径与安装目录相同，无需迁移"
        return 1
    fi
    info "从旧版本迁移数据: $old_path -> $INSTALL_DIR"
    info "  1. 停止服务"
    stop_service || true
    info "  2. 备份并复制配置与数据"
    mkdir -p "$INSTALL_DIR"
    local d
    for d in config data logs bin; do
        if [ -d "$old_path/$d" ]; then
            mkdir -p "$INSTALL_DIR/$d"
            cp -a "$old_path/$d/." "$INSTALL_DIR/$d/"
        fi
    done
    info "  3. 写入启动器与服务"
    create_launcher
    create_service || return 1
    info "  4. 启动服务"
    start_service || return 1
    info "迁移完成。旧数据仍保留在 $old_path，确认无误后可手动删除。"
}

migrate_from_old_version() {
    local old_path
    old_path=$(detect_old_installation) || true
    if [ -z "$old_path" ]; then
        error "未检测到旧版本安装（查找过: $INSTALL_DIR/data, /opt/pr-sing/data）"
        return 1
    fi
    yellow "检测到旧版本数据: $old_path"
    read -r -p "是否迁移到当前布局 ($INSTALL_DIR)? (y/N): " yn
    if [ "$yn" = "y" ] || [ "$yn" = "Y" ]; then
        migrate_old_installation "$old_path"
    else
        info "已取消迁移"
    fi
}

# ==================== 功能子菜单（PR-Sing） ====================
chain_menu() {
    while true; do
        echo ""
        cyan "---------- 链式代理管理 ----------"
        run_cli chain list || true
        echo ""
        echo "  1. 新建链（按顺序填成员）"
        echo "  2. 删除链"
        echo "  3. 测试链出口 IP"
        echo "  0. 返回主菜单"
        echo ""
        read -r -p "请输入选项 [0-3]: " c || return
        case "$c" in
            1)
                echo "可选节点:"
                run_cli node list || true
                read -r -p "链名称: " cname
                read -r -p "成员节点 id（逗号分隔，顺序即流量顺序，最后一个是出口）: " cmembers
                if [ -n "$cname" ] && [ -n "$cmembers" ]; then
                    run_cli chain add "$cname" "$cmembers" || true
                else
                    error "名称和成员不能为空"
                fi
                ;;
            2)
                read -r -p "输入要删除的链 id: " cid
                [ -n "$cid" ] && run_cli chain del "$cid" || true
                ;;
            3)
                read -r -p "输入要测试的链 id: " cid
                [ -n "$cid" ] && run_cli chain test "$cid" || true
                ;;
            0) return ;;
            *) error "无效的选项" ;;
        esac
        echo ""
        read -r -p "按 Enter 键继续..."
    done
}

node_menu() {
    while true; do
        echo ""
        cyan "---------- 节点管理 ----------"
        echo "  1. 查看节点列表"
        echo "  2. 导入分享链接（粘贴多行，最后空行结束）"
        echo "  3. 删除节点"
        echo "  4. 节点测速"
        echo "  0. 返回主菜单"
        echo ""
        read -r -p "请输入选项 [0-4]: " c || return
        case "$c" in
            1) run_cli node list || true ;;
            2)
                echo "请粘贴链接（每行一条，空行结束）:"
                run_cli node import - || true
                ;;
            3)
                run_cli node list || true
                read -r -p "输入要删除的节点 id: " nid
                [ -n "$nid" ] && run_cli node del "$nid" || true
                ;;
            4)
                run_cli node list || true
                read -r -p "输入要测速的节点 id: " nid
                [ -n "$nid" ] && run_cli node test "$nid" || true
                ;;
            0) return ;;
            *) error "无效的选项" ;;
        esac
        echo ""
        read -r -p "按 Enter 键继续..."
    done
}

# ==================== 菜单 ====================
show_menu() {
    while true; do
        clear 2>/dev/null || true
        echo "==================================================="
        cyan "          PR-Sing 安装管理脚本 v${VERSION}          "
        echo "==================================================="
        echo "系统: $OS / 架构: $ARCH_NAME / 初始化系统: $INIT_SYSTEM"
        echo "安装目录: ${INSTALL_DIR}"
        local source_name
        case $DOWNLOAD_SOURCE in
            1) source_name="GitHub直连" ;;
            2) source_name="gh-proxy.com" ;;
            3) source_name="ghfast.top" ;;
            *) source_name="未知" ;;
        esac
        [ -n "${GH_PROXY:-}" ] && source_name="GH_PROXY 环境变量"
        echo "下载源: $source_name"

        if is_installed; then
            green "状态: 已安装"
        else
            yellow "状态: 未安装"
        fi

        local old_version_path
        old_version_path=$(detect_old_installation 2>/dev/null || true)
        if [ -n "$old_version_path" ]; then
            yellow "旧版本: 检测到 ($old_version_path)"
        fi

        echo "---------------------------------------------------"
        echo ""
        yellow "部署 (自动检测安装/升级):"
        echo "  1. 部署 PR-Sing (稳定版)"
        echo "  2. 部署 PR-Sing (测试版)"
        echo ""
        yellow "管理:"
        echo "  3. 查看服务状态"
        echo "  4. 启动服务"
        echo "  5. 停止服务"
        echo "  6. 重启服务"
        echo ""
        yellow "维护:"
        echo "  7. 重置配置 (会丢失所有配置)"
        red "  8. 卸载 PR-Sing (会丢失所有数据)"
        echo ""
        yellow "设置:"
        echo "  9. 切换下载源"
        echo "  10. 设置安装目录"
        echo "  11. 配置系统环境"
        echo ""
        yellow "迁移:"
        echo "  12. 从旧版本迁移"
        echo ""
        yellow "功能 (PR-Sing):"
        echo "  13. 链式代理管理"
        echo "  14. 节点管理"
        echo ""
        red "  0. 退出脚本"
        echo ""
        echo "---------------------------------------------------"

        read -r -p "请输入选项 [0-14]: " choice || exit 0
        case $choice in
            1) deploy_smbox "release" || true ;;
            2) deploy_smbox "beta" || true ;;
            3) check_service_status ;;
            4) start_service || true ;;
            5) stop_service || true ;;
            6) restart_service || true ;;
            7) reset_config || true ;;
            8) uninstall_smbox || true ;;
            9) select_download_source ;;
            10) select_install_dir ;;
            11)
                install_dependencies || true
                configure_system || true
                ;;
            12)
                install_dependencies || true
                migrate_from_old_version || true
                ;;
            13)
                if is_installed; then chain_menu; else error "PR-Sing 未安装，请先部署"; fi
                ;;
            14)
                if is_installed; then node_menu; else error "PR-Sing 未安装，请先部署"; fi
                ;;
            0) exit 0 ;;
            *) error "无效的选项，请重新选择" ;;
        esac

        echo ""
        read -r -p "按 Enter 键返回菜单..."
    done
}

# ==================== 命令行参数支持 ====================
show_help() {
    echo "PR-Sing 安装管理脚本 v${VERSION}"
    echo ""
    echo "用法: $0 [命令] [选项]"
    echo ""
    echo "命令:"
    echo "  deploy [release|beta]   部署 PR-Sing (自动检测安装/升级)"
    echo "  install [release|beta]  同 deploy，自动检测安装或升级"
    echo "  uninstall               卸载 PR-Sing"
    echo "  start                   启动服务"
    echo "  stop                    停止服务"
    echo "  restart                 重启服务"
    echo "  status                  查看服务状态"
    echo "  reset                   重置配置"
    echo "  migrate [旧版本路径]    从旧版本迁移数据"
    echo "  node <...>              节点管理 (list|import|del|test)"
    echo "  chain <...>             链式代理 (list|add|del|test)"
    echo "  group list              节点组列表"
    echo "  sub <...>               订阅管理 (list|add|refresh)"
    echo "  help                    显示帮助"
    echo ""
    echo "选项:"
    echo "  --dir DIR               指定安装目录 (默认: /opt/pr-sing)"
    echo ""
    echo "示例:"
    echo "  $0                      显示交互式菜单"
    echo "  $0 deploy               部署稳定版 (未安装则安装，已安装则升级)"
    echo "  $0 deploy beta          部署测试版"
    echo "  $0 install              同 deploy"
    echo "  $0 --dir /root deploy   部署到 /root 目录"
    echo "  $0 chain list           查看链式代理"
    echo "  $0 migrate              自动检测并迁移旧版本"
}

# ==================== 主程序 ====================
main() {
    local action='' channel=release old_path=''
    load_manage_conf
    # Parse all options before running commands so --dir works in either position.
    while [[ $# -gt 0 ]]; do
        case $1 in
            --dir)
                if [ "$#" -lt 2 ] || [ -z "$2" ] || [[ "$2" == --* ]]; then
                    error "--dir 需要指定安装目录"; return 1
                fi
                INSTALL_DIR="$2"
                shift 2
                ;;
            deploy|install|upgrade)
                [ -z "$action" ] || { error "只能指定一个命令"; return 1; }
                action=deploy
                shift
                if [ "$#" -gt 0 ] && [[ "$1" != --* ]]; then channel="$1"; shift; fi
                case "$channel" in release|beta) ;; *) error "无效的版本通道: $channel"; return 1 ;; esac
                ;;
            migrate)
                [ -z "$action" ] || { error "只能指定一个命令"; return 1; }
                action=migrate
                shift
                if [ "$#" -gt 0 ] && [[ "$1" != --* ]]; then old_path="$1"; shift; fi
                ;;
            uninstall|start|stop|restart|status|reset)
                [ -z "$action" ] || { error "只能指定一个命令"; return 1; }
                action="$1"
                shift
                ;;
            node|chain|group|sub)
                [ -z "$action" ] || { error "只能指定一个命令"; return 1; }
                action=cli
                CLI_ARGS=("$1" "${@:2}")
                shift $#
                ;;
            help|--help|-h)
                show_help
                return 0
                ;;
            *)
                error "未知参数: $1"; return 1
                ;;
        esac
    done

    validate_install_dir || return 1
    check_root
    detect_os
    detect_arch
    detect_init
    case "$action" in
        deploy) deploy_smbox "$channel" ;;
        uninstall) uninstall_smbox ;;
        start) start_service ;;
        stop) stop_service ;;
        restart) restart_service ;;
        status) check_service_status ;;
        reset) reset_config ;;
        migrate)
            install_dependencies || return 1
            if [ -n "$old_path" ]; then
                migrate_old_installation "$old_path"
            else
                migrate_from_old_version
            fi ;;
        cli) run_cli "${CLI_ARGS[@]}" ;;
        '') show_menu ;;
    esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then main "$@"; fi
