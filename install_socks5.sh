#!/bin/bash

# ---------------------------
# 一键安装 SOCKS5（Sing-box）
# ---------------------------

echo "开始安装 Sing-box..."

# 1. 检查并安装 curl（如果未安装）
if ! command -v curl >/dev/null 2>&1; then
    echo "curl 未安装，正在安装 curl..."
    # 如果是基于 Debian/Ubuntu 的系统
    if [ -f /etc/debian_version ]; then
        apt-get update && apt-get install -y curl
    # 如果是基于 RedHat/CentOS 的系统
    elif [ -f /etc/redhat-release ]; then
        yum install -y curl
    # 如果是基于其他系统，提示用户手动安装 curl
    else
        echo "未知的操作系统，请手动安装 curl。"
        exit 1
    fi
    echo "curl 安装完成！"
else
    echo "curl 已安装，继续执行安装..."
fi

# 2. 安装 Sing-box
curl -fsSL https://sing-box.app/install.sh | bash

# 3. 生成随机端口、用户名、密码
PORT=$(shuf -i 10000-60000 -n 1)
USER=$(tr -dc 'a-z0-9' </dev/urandom | head -c 8)
PASS=$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 16)

# 4. 配置路径
CONFIG_DIR="/etc/sing-box"
[ ! -d "$CONFIG_DIR" ] && CONFIG_DIR="/usr/local/etc/sing-box"
CONFIG_FILE="$CONFIG_DIR/config.json"

# 5. 备份原配置
if [ -f "$CONFIG_FILE" ]; then
    mv "$CONFIG_FILE" "$CONFIG_FILE.bak"
fi

# 6. 写入新 config.json
cat > "$CONFIG_FILE" <<EOF
{
  "log": {
    "level": "info"
  },
  "inbounds": [
    {
      "type": "socks",
      "listen": "0.0.0.0",
      "listen_port": $PORT,
      "users": [
        {
          "username": "$USER",
          "password": "$PASS"
        }
      ]
    }
  ],
  "outbounds": [
    {
      "type": "direct"
    }
  ]
}
EOF

# 7. 开机启动 + 启动服务
systemctl enable sing-box.service
systemctl restart sing-box.service

# 8. 放行 UFW（如果 UFW 存在）
if command -v ufw >/dev/null 2>&1; then
    ufw allow $PORT/tcp
fi

# 9. 获取公网 IP
IPV4=$(curl -s ipv4.ip.sb || curl -s ifconfig.me)

echo ""
echo "======================================="
echo "✔ SOCKS5 安装完成！"
echo "======================================="
echo "服务器 IP:  $IPV4"
echo "端口:       $PORT"
echo "用户名:     $USER"
echo "密码:       $PASS"
echo ""
echo "SOCKS5 地址："
echo "$IPV4:$PORT"
echo ""
echo "======================================="
echo "已自动启动：systemctl status sing-box.service"
echo "======================================="
