#!/bin/bash

echo "==============================="
echo "一键卸载 Sing-box SOCKS5"
echo "==============================="

# 停止服务
echo "停止 Sing-box 服务..."
systemctl stop sing-box.service 2>/dev/null

# 禁用开机启动
echo "禁用开机启动..."
systemctl disable sing-box.service 2>/dev/null

# 删除 service 文件
echo "删除 systemd service 文件..."
rm -f /etc/systemd/system/sing-box.service
rm -f /usr/lib/systemd/system/sing-box.service
systemctl daemon-reload

# 删除可执行文件
echo "删除程序文件..."
rm -f /usr/bin/sing-box
rm -f /usr/local/bin/sing-box

# 删除配置文件夹
echo "删除配置目录..."
rm -rf /etc/sing-box
rm -rf /usr/local/etc/sing-box

echo "==============================="
echo "Sing-box 已成功卸载！"
echo "==============================="
echo ""
echo "提示：如果你之前开放过防火墙端口，需要手动删除，例如："
echo ""
echo "  ufw delete allow 1080/tcp"
echo ""
echo "根据你的端口替换即可。"
echo ""
