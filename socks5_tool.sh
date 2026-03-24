#!/bin/bash

# ==========================================
#   SOCKS5 Toolbox (最终版，含 IPv6 一键配置修复)
# ==========================================

INSTALL_URL="https://raw.githubusercontent.com/guthy325630/s5/main/install_socks5.sh"
UNINSTALL_URL="https://raw.githubusercontent.com/guthy325630/s5/main/d_socks5.sh"
ADMIN_INSTALL_URL="https://raw.githubusercontent.com/guthy325630/s5/main/install_admin.sh"
ADMIN_UNINSTALL_URL="https://raw.githubusercontent.com/guthy325630/s5/main/uninstall_admin.sh"
CONFIG_FILE="/etc/sing-box/config.json"

get_ipv4() {
    curl -s ipv4.ip.sb || curl -s ifconfig.me
}

get_ipv6() {
    curl -6 -s ipv6.ip.sb 2>/dev/null
}

pause() {
    read -p "回车继续..." _
}

menu() {
    clear
    echo "======================================="
    echo "           SOCKS5 工具箱"
    echo "======================================="
    echo " 1. 安装 SOCKS5"
    echo " 2. 卸载 SOCKS5"
    echo " 3. 查看服务状态"
    echo " 4. 重启 SOCKS5"
    echo " 5. 修改端口或用户名/密码"
    echo " 6. 查看端口 / 用户名 / 密码"
    echo " 7. 随机重置端口 + 账号密码"
    echo " 8. 切换监听模式（IPv4 / IPv6）"
    echo " 9. 激活 IPv6（检测）"
    echo "10. 永久绑定服务商 IPv6"
    echo "11. 一键配置 IPv6 并绑定 SOCKS5"
    echo "12. 安装后台管理（Web）"
    echo "13. 卸载后台管理（Web）"
    echo "14. 查看后台服务状态"
    echo "15. 查看后台访问地址"
    echo " 0. 退出"
    echo "======================================="
    read -p "请输入选项 [0-15]: " choice

    case $choice in
        1) install_socks5 ;;
        2) uninstall_socks5 ;;
        3) status_socks5 ;;
        4) restart_socks5 ;;
        5) modify_socks5 ;;
        6) show_socks5 ;;
        7) random_reset ;;
        8) switch_ip ;;
        9) enable_ipv6 ;;
        10) bind_ipv6_netplan ;;
        11) auto_ipv6_setup ;;
        12) install_admin_web ;;
        13) uninstall_admin_web ;;
        14) status_admin_web ;;
        15) show_admin_web ;;
        0) exit 0 ;;
        *) echo "输入错误"; sleep 1; menu ;;
    esac
}

install_socks5() {
    bash <(curl -fsSL $INSTALL_URL)
    pause
    menu
}

uninstall_socks5() {
    bash <(curl -fsSL $UNINSTALL_URL)
    pause
    menu
}

status_socks5() {
    systemctl status sing-box.service
    pause
    menu
}

restart_socks5() {
    systemctl restart sing-box.service
    echo "✔ 已重启"
    sleep 1
    menu
}

modify_socks5() {
    [ ! -f "$CONFIG_FILE" ] && echo "未安装 SOCKS5" && pause && menu

    read -p "新端口（回车跳过）: " NEW_PORT
    read -p "新用户名（回车跳过）: " NEW_USER
    read -p "新密码（回车跳过）: " NEW_PASS

    # 修改端口（只匹配 listen_port）
    if [ -n "$NEW_PORT" ]; then
        sed -i -E 's/("listen_port"[[:space:]]*:[[:space:]]*)[0-9]+/\1'"$NEW_PORT"'/' "$CONFIG_FILE"
    fi

    # 修改用户名（只匹配 username 字段）
    if [ -n "$NEW_USER" ]; then
        sed -i -E 's/("username"[[:space:]]*:[[:space:]]*")[^"]+/\1'"$NEW_USER"'/' "$CONFIG_FILE"
    fi

    # 修改密码（只匹配 password 字段）
    if [ -n "$NEW_PASS" ]; then
        sed -i -E 's/("password"[[:space:]]*:[[:space:]]*")[^"]+/\1'"$NEW_PASS"'/' "$CONFIG_FILE"
    fi

    systemctl restart sing-box.service
    echo "✔ 修改完成并已重启 sing-box"
    pause
    menu
}

show_socks5() {
    [ ! -f "$CONFIG_FILE" ] && echo "未安装 SOCKS5" && pause && menu

    PORT=$(sed -nE 's/.*"listen_port"[[:space:]]*:[[:space:]]*([0-9]+).*/\1/p' "$CONFIG_FILE" | head -n1)
    USER=$(sed -nE 's/.*"username"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' "$CONFIG_FILE" | head -n1)
    PASS=$(sed -nE 's/.*"password"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' "$CONFIG_FILE" | head -n1)

    if [ -z "$PORT" ]; then
        echo "⚠ 端口解析失败（config.json 可能被破坏）"
        echo "配置文件路径: $CONFIG_FILE"
    fi

    IPV4=$(get_ipv4)
    IPV6=$(get_ipv6)

    echo "======================================="
    echo " SOCKS5 信息"
    echo "======================================="
    [ -n "$IPV4" ] && echo " IPv4 : $IPV4:$PORT"
    [ -n "$IPV6" ] && echo " IPv6 : [$IPV6]:$PORT"
    echo " 用户名 : $USER"
    echo " 密码   : $PASS"
    echo "======================================="
    pause
    menu
}

random_reset() {
    [ ! -f "$CONFIG_FILE" ] && echo "未安装 SOCKS5" && pause && menu

    P=$(shuf -i 10000-60000 -n 1)
    U=$(tr -dc a-z0-9 </dev/urandom | head -c 8)
    PW=$(tr -dc A-Za-z0-9 </dev/urandom | head -c 16)

    sed -i "s/\"listen_port\": [0-9]\+/\\"listen_port\\": $P/" $CONFIG_FILE
    sed -i "s/\"username\": \".*\"/\"username\": \"$U\"/" $CONFIG_FILE
    sed -i "s/\"password\": \".*\"/\"password\": \"$PW\"/" $CONFIG_FILE

    systemctl restart sing-box.service

    echo "✔ 已随机重置"
    echo " 端口: $P"
    echo " 用户: $U"
    echo " 密码: $PW"
    pause
    menu
}

switch_ip() {
    [ ! -f "$CONFIG_FILE" ] && echo "未安装 SOCKS5" && pause && menu

    if ip -6 addr show scope global | grep -q inet6; then
        read -p "切换为 IPv6 双栈监听？(y/n): " yn
        if [[ $yn == "y" ]]; then
            sed -i 's/"listen": "0.0.0.0"/"listen": "::"/' $CONFIG_FILE
            systemctl restart sing-box.service
            echo "✔ 已切换为 IPv6 + IPv4 双栈"
        fi
    else
        echo "❌ 未检测到公网 IPv6"
    fi
    pause
    menu
}

enable_ipv6() {
    IPV6=$(ip -6 addr show scope global | grep inet6 | awk '{print $2}' | cut -d/ -f1)

    if [ -n "$IPV6" ]; then
        echo "✔ 已检测到公网 IPv6: $IPV6"
    else
        echo "❌ 未检测到公网 IPv6（可能需要永久绑定）"
    fi
    pause
    menu
}

bind_ipv6_netplan() {
    echo "====== 永久绑定服务商 IPv6 ======"

    if ! command -v netplan >/dev/null 2>&1; then
        echo "❌ 当前系统不支持 netplan"
        pause
        menu
    fi

    IFACE=$(ip route | awk '/default/ {print $5}' | head -n1)
    [ -z "$IFACE" ] && echo "❌ 无法检测网卡" && pause && menu

    read -p "IPv6 地址 (例如 2404:c140:2100::1234): " IPV6_ADDR
    read -p "前缀长度 (例如 64): " IPV6_PREFIX
    read -p "IPv6 网关 (例如 2404:c140:2100::1): " IPV6_GW

    NETPLAN_FILE=$(ls /etc/netplan/*.yaml | head -n1)
    cp "$NETPLAN_FILE" "${NETPLAN_FILE}.bak.$(date +%s)"

cat > "$NETPLAN_FILE" <<EOF
network:
  version: 2
  renderer: networkd
  ethernets:
    $IFACE:
      dhcp4: true
      dhcp6: false
      addresses:
        - ${IPV6_ADDR}/${IPV6_PREFIX}
      routes:
        - to: default
          via: ${IPV6_GW}
      nameservers:
        addresses:
          - 8.8.8.8
          - 2001:4860:4860::8888
EOF

    chmod 600 "$NETPLAN_FILE"
    netplan apply
    echo "✔ IPv6 永久绑定完成"
    pause
    menu
}

auto_ipv6_setup() {
    echo "====== 一键 IPv6 配置并绑定 SOCKS5 ======"

    IFACE=$(ip route | awk '/default/ {print $5}' | head -n1)
    [ -z "$IFACE" ] && { echo "❌ 无法检测到主网卡"; pause; menu; }
    echo "✔ 检测到主网卡: $IFACE"

    IPV6=$(curl -6 -s ipv6.ip.sb 2>/dev/null)
    if [ -n "$IPV6" ]; then
        echo "✔ 已检测到公网 IPv6: $IPV6"
        read -p "是否使用检测到的 IPv6？(y/n): " use_ipv6
        if [[ $use_ipv6 != "y" ]]; then
            IPV6=""
        fi
    fi

    if [ -z "$IPV6" ]; then
        echo "⚠ 未检测到公网 IPv6，或者选择手动输入"
        read -p "请输入 IPv6 地址 (例如 2404:c140:2100::1234): " IPV6
        read -p "请输入 IPv6 前缀长度 (通常 64): " IPV6_PREFIX
        read -p "请输入 IPv6 网关 (例如 2404:c140:2100::1): " IPV6_GW
    fi

    NETPLAN_FILE=$(ls /etc/netplan/*.yaml | head -n1 2>/dev/null)
    if [ -z "$NETPLAN_FILE" ]; then
        echo "❌ 未找到 /etc/netplan/*.yaml 文件"
        pause
        menu
    fi

    cp "$NETPLAN_FILE" "${NETPLAN_FILE}.bak.$(date +%s)"

cat > "$NETPLAN_FILE" <<EOF
network:
  version: 2
  renderer: networkd
  ethernets:
    $IFACE:
      dhcp4: true
      dhcp6: false
      addresses:
        - ${IPV6}/${IPV6_PREFIX}
      routes:
        - to: default
          via: ${IPV6_GW}
      nameservers:
        addresses:
          - 8.8.8.8
          - 2001:4860:4860::8888
EOF

    chmod 600 "$NETPLAN_FILE"
    echo "✔ netplan 配置已写入，正在应用..."
    netplan apply
    sleep 2

    if [ -f "$CONFIG_FILE" ]; then
        sed -i 's/"listen": "0.0.0.0"/"listen": "::"/' "$CONFIG_FILE"
        systemctl restart sing-box.service
        echo "✔ SOCKS5 已切换为 IPv6 双栈"
    fi

    echo "✔ 完成 IPv6 配置"
    show_socks5
}

install_admin_web() {
    bash <(curl -fsSL $ADMIN_INSTALL_URL)
    pause
    menu
}

uninstall_admin_web() {
    bash <(curl -fsSL $ADMIN_UNINSTALL_URL)
    pause
    menu
}

status_admin_web() {
    echo "======================================="
    echo " SOCKS5 后台服务状态"
    echo "======================================="

    if ! systemctl list-unit-files | grep -q '^socks5-admin\.service'; then
        echo "❌ 未检测到 socks5-admin.service（可能尚未安装后台）"
        echo "提示：请先执行菜单 12 安装后台管理。"
        echo "======================================="
        pause
        menu
        return
    fi

    if systemctl is-active --quiet socks5-admin.service; then
        echo "运行状态 : ✅ 运行中 (active)"
    else
        STATE=$(systemctl is-active socks5-admin.service 2>/dev/null)
        [ -z "$STATE" ] && STATE="unknown"
        echo "运行状态 : ❌ 未运行 ($STATE)"
    fi

    if systemctl is-enabled --quiet socks5-admin.service 2>/dev/null; then
        echo "开机自启 : ✅ 已启用"
    else
        ENABLED=$(systemctl is-enabled socks5-admin.service 2>/dev/null)
        [ -z "$ENABLED" ] && ENABLED="disabled"
        echo "开机自启 : ❌ 未启用 ($ENABLED)"
    fi

    MAINPID=$(systemctl show -p MainPID --value socks5-admin.service 2>/dev/null)
    [ -z "$MAINPID" ] && MAINPID="0"
    if [ "$MAINPID" != "0" ]; then
        echo "进程 PID : $MAINPID"
    else
        echo "进程 PID : 无"
    fi

    echo "---------------------------------------"
    echo "最近日志（最后 8 行）:"
    journalctl -u socks5-admin.service -n 8 --no-pager -o cat 2>/dev/null || echo "暂无日志"
    echo "---------------------------------------"
    echo "原始状态详情:"
    systemctl status socks5-admin.service --no-pager -l 2>/dev/null
    echo "======================================="
    pause
    menu
}

show_admin_web() {
    SERVICE_FILE="/etc/systemd/system/socks5-admin.service"
    CRED_FILE="/var/lib/socks5-admin/admin.credentials"
    IPV4=$(get_ipv4)
    IPV6=$(get_ipv6)
    ADMIN_USER=""
    ADMIN_PASS=""

    if [ -f "$CRED_FILE" ]; then
        ADMIN_USER=$(cut -d: -f1 "$CRED_FILE" 2>/dev/null)
        ADMIN_PASS=$(cut -d: -f2- "$CRED_FILE" 2>/dev/null)
    fi

    if [ -z "$ADMIN_USER" ] && [ -f "$SERVICE_FILE" ]; then
        ADMIN_USER=$(sed -nE 's/^Environment=SOCKS5_ADMIN_USER=(.*)$/\1/p' "$SERVICE_FILE" | head -n1)
        ADMIN_PASS=$(sed -nE 's/^Environment=SOCKS5_ADMIN_PASS=(.*)$/\1/p' "$SERVICE_FILE" | head -n1)
    fi

    [ -z "$ADMIN_USER" ] && ADMIN_USER="admin"
    [ -z "$ADMIN_PASS" ] && ADMIN_PASS="admin123"

    echo "======================================="
    echo " SOCKS5 后台访问地址"
    echo "======================================="
    [ -n "$IPV4" ] && echo " http://$IPV4:9580"
    [ -n "$IPV6" ] && echo " http://[$IPV6]:9580"
    echo "当前账号: $ADMIN_USER"
    echo "当前密码: $ADMIN_PASS"
    echo "======================================="
    pause
    menu
}

menu
