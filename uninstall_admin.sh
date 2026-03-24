#!/bin/bash
set -e

echo "== 卸载 SOCKS5 后台管理 =="
systemctl stop socks5-admin.service 2>/dev/null || true
systemctl disable socks5-admin.service 2>/dev/null || true
rm -f /etc/systemd/system/socks5-admin.service
systemctl daemon-reload
rm -rf /opt/socks5-admin
echo "卸载完成（数据库默认保留在 /var/lib/socks5-admin/admin.db）。"
