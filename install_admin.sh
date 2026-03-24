#!/bin/bash
set -e

APP_DIR="/opt/socks5-admin"
SERVICE_FILE="/etc/systemd/system/socks5-admin.service"

echo "== 安装 SOCKS5 后台管理 =="

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 未安装，正在安装..."
  if [ -f /etc/debian_version ]; then
    apt-get update && apt-get install -y python3 python3-pip
  elif [ -f /etc/redhat-release ]; then
    yum install -y python3 python3-pip
  else
    echo "未知系统，请手动安装 python3/pip"
    exit 1
  fi
fi

mkdir -p "$APP_DIR"
cp -r admin_server.py templates "$APP_DIR"/

python3 -m pip install --upgrade pip
python3 -m pip install flask

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=SOCKS5 Admin Web
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR
Environment=SOCKS5_ADMIN_SECRET=change-this-secret
Environment=SOCKS5_ADMIN_USER=admin
Environment=SOCKS5_ADMIN_PASS=admin123
Environment=SOCKS5_ADMIN_DB=/var/lib/socks5-admin/admin.db
Environment=SOCKS5_CONFIG_FILE=/etc/sing-box/config.json
Environment=SOCKS5_ADMIN_CRED_FILE=/var/lib/socks5-admin/admin.credentials
Environment=SOCKS5_ADMIN_HOST=0.0.0.0
Environment=SOCKS5_ADMIN_PORT=9580
Environment=SOCKS5_COLLECT_INTERVAL_SEC=60
ExecStart=/usr/bin/python3 $APP_DIR/admin_server.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

mkdir -p /var/lib/socks5-admin
if [ ! -f /var/lib/socks5-admin/admin.credentials ]; then
  echo "admin:admin123" > /var/lib/socks5-admin/admin.credentials
  chmod 600 /var/lib/socks5-admin/admin.credentials
fi
systemctl daemon-reload
systemctl enable socks5-admin.service
systemctl restart socks5-admin.service

echo "== 安装完成 =="
echo "后台地址: http://服务器IP:9580"
echo "默认账号: admin"
echo "默认密码: admin123"
echo "请尽快修改服务环境变量中的默认密码。"
