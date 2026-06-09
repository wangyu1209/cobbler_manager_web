```markdown
# Cobbler Web 管理界面

基于 Flask 的 Cobbler Web 管理工具，提供系统部署、批量操作、IPMI 远程管理等功能。

## 功能概览

| 模块 | 功能 |
|------|------|
| 仪表盘 | 显示 Cobbler 连接状态、System/Profile 数量、快捷操作入口 |
| Systems 管理 | 查看所有 System 列表，支持多行关键词搜索、全选/反选、单台/批量重装、批量取消重装标记、单台预览 Kickstart、删除 |
| Profiles 管理 | 查看所有 Profile 列表 |
| Kickstart 模板 | 按 Profile 查看生成的 Kickstart 内容，支持一键复制 |
| IPMI 管理 | 批量远程电源控制（电源状态、重启、开机、关机）、PXE 启动、光驱启动、进入 BIOS |
| 添加 System | 单台添加 System（主机名、MAC、IP、网关、DNS、Profile） |
| 设置 | 配置 Cobbler API 连接信息（地址、用户名、密码），连接测试 |

## 系统架构

```
┌─────────────────────────────────────┐
│           浏览器（用户）              │
└──────────────┬──────────────────────┘
               │ HTTP
┌──────────────▼──────────────────────┐
│         cobbler-web 容器             │
│  ┌────────────────────────────────┐ │
│  │     Flask (app.py)            │ │
│  │  ┌──────────┐  ┌───────────┐  │ │
│  │  │ cobbler   │  │  ipmitool │  │ │
│  │  │ _client   │  │  (子进程) │  │ │
│  │  └─────┬────┘  └─────┬─────┘  │ │
│  └────────│──────────────│────────┘ │
└───────────│──────────────│──────────┘
            │ XML-RPC      │ IPMI lan+
┌───────────▼──┐     ┌─────▼────────┐
│   Cobbler    │     │  BMC 管理口   │
│   Server     │     │ (各设备)      │
└──────────────┘     └──────────────┘
```

## 目录结构

```
cobbler-web/
├── app.py                          # Flask 主应用（路由、业务逻辑）
├── cobbler_client.py               # Cobbler XML-RPC API 客户端封装
├── config_manager.py               # 配置文件读写
├── requirements.txt                # Python 依赖
├── Dockerfile                      # Docker 构建文件
├── templates/
│   ├── base.html                   # 基础布局（导航栏、全局样式、Flash 消息）
│   ├── index.html                  # 仪表盘
│   ├── systems.html                # System 列表（搜索、批量操作）
│   ├── profiles.html               # Profile 列表
│   ├── kickstart_templates.html    # Kickstart 模板列表
│   ├── kickstart_template_detail.html  # Kickstart 模板详情（内容查看、复制）
│   ├── ipmi.html                   # IPMI 管理页面
│   ├── add_system.html             # 添加 System 表单
│   ├── reinstall.html              # 单台重装表单
│   ├── preview.html                # Kickstart 预览
│   ├── batch_result.html           # 批量操作结果展示
│   └── settings.html               # Cobbler 连接设置
└── config/
    └── config.json                 # 运行时配置（自动生成，存储连接信息）
```

## 快速开始

### 环境要求

- Docker
- 可访问的 Cobbler API 服务
- 可访问的设备 BMC IPMI 管理口（如需 IPMI 功能）

### 构建镜像

```bash
docker build -t cobbler-web:latest .
```

### 运行容器

```bash
docker run -d \
    --name cobbler-web \
    --network host \
    -v /opt/cobbler-web/config:/app/config \
    --restart unless-stopped \
    cobbler-web:latest
```

> 使用 `--network host` 是因为 IPMI 功能需要容器直接访问 BMC 网段。

### 访问

浏览器打开：

```
http://<服务器IP>:5000
```

首次访问会自动跳转到设置页面，填入 Cobbler API 连接信息：

| 字段        | 示例                              |
| ----------- | --------------------------------- |
| Cobbler URL | `http://192.168.1.10/cobbler_api` |
| 用户名      | `cobbler`                         |
| 密码        | `your_password`                   |

点击「保存并测试连接」验证配置。

### 验证部署

```bash
# 确认容器运行中
docker ps | grep cobbler-web

# 确认 ipmitool 已安装
docker exec cobbler-web ipmitool -V

# 健康检查
curl http://localhost:5000/health
```

## 功能详细说明

### System 搜索

搜索框支持多行关键词输入，每行一个关键词，行之间为「且」（AND）关系，支持模糊匹配。

```
搜索范围：设备名称、Profile、IP、MAC

示例输入：
  2102310YQC
  centos

匹配规则：
  设备的名称/IP/MAC/Profile 必须同时包含 "2102310YQC" 和 "centos"
```

### System 批量操作

在 Systems 页面勾选设备后，可执行：

| 操作         | 说明                                                         |
| ------------ | ------------------------------------------------------------ |
| 批量重装     | 支持修改 Profile、IP（自动递增）、子网掩码、网关、DNS，提交后开启 PXE 并执行 sync |
| 取消重装标记 | 取消选中设备的 PXE 启动标记                                  |

### IPMI 管理

批量远程管理服务器 BMC，支持以下操作：

| 操作      | 执行命令                                                     | 说明                    |
| --------- | ------------------------------------------------------------ | ----------------------- |
| 电源状态  | `chassis power status`                                       | 查看设备当前开关机状态  |
| 重启      | `power cycle`                                                | 冷重启设备              |
| 开机      | `power on`                                                   | 远程开机                |
| 关机      | `power off`                                                  | 远程关机                |
| PXE 启动  | `bootdev pxe options=persistent` → `bootparam set bootflag force_pxe` → `power cycle` → `power on` | 设置永久 PXE 启动并重启 |
| 光驱启动  | `bootdev cdrom` → `power cycle` → `power on`                 | 设置光驱启动并重启      |
| 进入 BIOS | `bootdev bios` → `power cycle` → `power on`                  | 设置进入 BIOS 并重启    |

**设备列表格式：**

每行一台设备，支持两种格式：

```
# 格式一：仅 BMC IP（使用统一凭据）
10.16.107.101
10.16.107.102

# 格式二：BMC IP + 单独用户名 + 单独密码
10.16.107.103 admin admin123
10.16.107.104 root password456
```

IPMI 操作使用线程池并发执行，最多同时 10 个任务，每个命令超时 20 秒。

### Kickstart 模板查看

- 从所有 Profile 列表中读取关联的 Kickstart 模板
- 通过 Cobbler API 的 `generate_kickstart` 生成完整 KS 内容
- 支持一键复制 KS 内容（兼容 HTTP 环境）

### 批量重装流程

1. 在 Systems 页面搜索或浏览找到目标设备
2. 勾选设备（支持全选当前搜索结果）
3. 点击「批量重装」，在弹窗中填写配置
4. 确认提交后，Cobbler 执行以下操作：
   - 修改 System 配置（Profile、IP、网关等）
   - 开启 PXE 启动标记（`netboot_enabled=1`）
   - 执行 sync 同步到 TFTP
5. 配合 IPMI 重启设备即可开始自动安装

## 配置说明

配置文件存储在容器内 `/app/config/config.json`，通过宿主机挂载的目录持久化：

```json
{
    "cobbler_url": "http://192.168.1.10/cobbler_api",
    "cobbler_user": "cobbler",
    "cobbler_password": "your_password"
}
```

可通过 Web 设置页面修改，也可直接编辑文件后重启容器。

## 后续仅更新模板文件

如果只修改了 HTML 模板文件，无需重新构建镜像：

```bash
# 复制文件到宿主机挂载目录
cp templates/*.html /opt/cobbler-web/templates/

# 重启容器
docker restart cobbler-web
```

运行时挂载模板目录：

```bash
docker run -d \
    --name cobbler-web \
    --network host \
    -v /opt/cobbler-web/config:/app/config \
    -v /opt/cobbler-web/templates:/app/templates \
    --restart unless-stopped \
    cobbler-web:latest
```

## 技术栈

| 组件            | 版本/说明                                 |
| --------------- | ----------------------------------------- |
| Python          | 3.11                                      |
| Flask           | 3.0                                       |
| Gunicorn        | 生产 WSGI 服务器，4 workers               |
| Cobbler XML-RPC | 通过 `xmlrpc.client` 连接 Cobbler API     |
| ipmitool        | 通过 `subprocess` 调用，使用 lanplus 协议 |
| 前端            | 原生 HTML/CSS/JavaScript，无额外框架      |
| 字体            | DM Sans + Noto Sans SC（Google Fonts）    |
| 图标            | Bootstrap Icons 1.11.0                    |

## 端口

| 端口 | 用途          |
| ---- | ------------- |
| 5000 | Web 界面 HTTP |

## 环境变量

| 变量         | 默认值                          | 说明                             |
| ------------ | ------------------------------- | -------------------------------- |
| `SECRET_KEY` | `cobbler-web-dev-key-change-me` | Flask 会话密钥，生产环境建议修改 |

## 常见问题

### Kickstart 模板显示渲染错误

```
This kickstart had errors that prevented it from being rendered correctly.
```

这是 Cobbler 服务端的模板渲染失败，不是 Web 界面的问题。在 Cobbler 服务器上排查：

```bash
# 查看错误日志
tail -200 /var/log/cobbler/cobbler.log | grep -i error

# 测试渲染
cobbler profile getks --name=<profile名称>

# 检查 Profile 配置
cobbler profile report --name=<profile名称>
```

常见原因：ks 模板中引用了未定义的变量、Cheetah 模板语法错误、Profile 缺少必填字段。

### IPMI 操作超时

- 确认容器网络能访问 BMC IP（使用 `--network host`）
- 确认 BMC IP、用户名、密码正确
- 确认 BMC 管理口网络连通：`ping <BMC_IP>`

### ipmitool 未安装

```bash
# 检查是否安装
docker exec cobbler-web ipmitool -V

# 如果未安装，重新构建镜像
docker build -t cobbler-web:latest .
```
