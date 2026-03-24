# SOCKS5 工具箱

一键安装/卸载/管理 SOCKS5 服务的工具箱脚本。

现已支持安装 Web 后台管理（Flask + SQLite），可进行：
- 用户新增、删除、封禁、解封
- 用户备注管理
- 会话记录查看
- 从 sing-box 日志手动采集连接/流量（在仪表盘点击采集）
- 自动增量采集（基于 journal cursor，避免重复累计）
- 后台操作日志查看
- 后台修改管理员账号密码
- 登录失败防暴力破解（连续失败锁定 15 分钟）
- 按用户流量趋势图（近7天/30天）
- 每日汇总报表（用户维度）

## 使用方法

在终端执行下面命令即可一键运行：

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/guthy325630/s5/main/socks5_tool.sh)
```

### 一键运行（推荐）
```bash
bash <(command -v curl >/dev/null 2>&1 && \
curl -fsSL https://raw.githubusercontent.com/guthy325630/s5/main/socks5_tool.sh || \
wget -qO- https://raw.githubusercontent.com/guthy325630/s5/main/socks5_tool.sh)
```

## 后台管理默认信息

- 地址：`http://服务器IP:9580`
- 默认账号：`admin`
- 默认密码：`admin123`

也可以在后台仪表盘直接修改管理员账号密码。

## 菜单说明

- 工具箱菜单 `15. 查看后台访问地址` 会读取当前后台账号密码：
  - 优先读取 `/var/lib/socks5-admin/admin.credentials`
  - 无该文件时回退读取 `/etc/systemd/system/socks5-admin.service`
