#!/bin/bash
set -e

APP_DIR="/opt/socks5-admin"
SERVICE_FILE="/etc/systemd/system/socks5-admin.service"
REPO_RAW_BASE="https://raw.githubusercontent.com/guthy325630/s5/main"
MAX_RETRY=3

download_file() {
  local url="$1"
  local output="$2"
  local name="$3"
  local i code

  for i in $(seq 1 "$MAX_RETRY"); do
    code=$(curl -L --connect-timeout 10 --max-time 30 -sS -w "%{http_code}" -o "$output.tmp" "$url" || echo "000")
    if [ "$code" = "200" ]; then
      mv -f "$output.tmp" "$output"
      echo "✔ 下载成功: $name"
      return 0
    fi

    rm -f "$output.tmp"
    if [ "$i" -lt "$MAX_RETRY" ]; then
      echo "⚠ 下载失败: $name（第 $i 次，HTTP=$code），正在重试..."
      sleep 1
    fi
  done

  echo "❌ 下载失败: $name"
  if [ "$code" = "404" ]; then
    echo "原因: 远程文件不存在（404）"
    echo "请检查 GitHub 仓库名、分支名、文件路径是否正确。"
  elif [ "$code" = "000" ]; then
    echo "原因: 网络连接失败或 DNS 解析失败"
    echo "请检查服务器网络、DNS、以及是否可访问 raw.githubusercontent.com。"
  else
    echo "原因: 远程返回异常状态码 HTTP=$code"
  fi
  echo "下载地址: $url"
  exit 1
}

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
mkdir -p "$APP_DIR/templates"

echo "下载后台文件..."
download_file "$REPO_RAW_BASE/admin_server.py" "$APP_DIR/admin_server.py" "admin_server.py"
download_file "$REPO_RAW_BASE/templates/base.html" "$APP_DIR/templates/base.html" "templates/base.html"
download_file "$REPO_RAW_BASE/templates/login.html" "$APP_DIR/templates/login.html" "templates/login.html"
download_file "$REPO_RAW_BASE/templates/dashboard.html" "$APP_DIR/templates/dashboard.html" "templates/dashboard.html"
download_file "$REPO_RAW_BASE/templates/users.html" "$APP_DIR/templates/users.html" "templates/users.html"
download_file "$REPO_RAW_BASE/templates/sessions.html" "$APP_DIR/templates/sessions.html" "templates/sessions.html"
download_file "$REPO_RAW_BASE/templates/reports.html" "$APP_DIR/templates/reports.html" "templates/reports.html"

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
