# 系统代理设置工具 (Linux)

> 解决 Kali / Debian 等精简 Linux 系统缺少图形化代理设置界面，导致 Edge / Chrome 浏览器无法正常配置系统代理的问题。

## 问题背景

某些 Linux 系统（如 Kali Linux 的精简安装）缺少完整的 GNOME 设置面板或图形化代理配置工具。当用户在 Edge 浏览器中点击"打开系统代理设置"时，无法正常打开设置页面，直接报错。

本工具通过**多层面代理设置**，一站式解决该问题。

## 功能特性

| 功能 | 说明 | 生效范围 |
|------|------|----------|
| GNOME 系统代理 | 通过 `gsettings` 设置 `org.gnome.system.proxy` | 桌面应用、Edge/Chrome 浏览器（即时生效） |
| 环境变量代理 | 写入 `http_proxy` / `https_proxy` 等到 `~/.config/proxy_env.sh` | curl、wget、git 等命令行工具（重开终端生效） |
| APT 代理配置 | 写入 `/etc/apt/apt.conf.d/95proxies` | apt update / apt install（需 root 权限） |
| 浏览器启动器 | 通过 `--proxy-server` 参数直接启动浏览器 | Edge / Chrome / Chromium / Firefox |
| 浏览器包装脚本 | 创建始终带代理的启动脚本 | 可加入 PATH，每次启动都走代理 |
| 预设管理 | 保存常用代理配置，一键切换 | — |
| 状态实时检测 | 每 5 秒自动刷新，检测外部修改 | — |

## 截图

程序界面包含以下区域：
- 当前代理状态（GNOME / 环境变量 / APT 三层面状态）
- 代理设置（地址、端口、no_proxy、预设管理）
- 作用域选择（勾选要应用的范围）
- 一键应用 / 一键关闭
- 浏览器代理启动器

## 环境要求

- Python 3.6+
- Tkinter（`python3-tk`）
- `gsettings`（GNOME 桌面环境自带）
- 可选：`pkexec` 或 `sudo`（APT 代理设置需要）

## 安装

### 方式一：直接运行

```bash
# 安装 tkinter 依赖（如尚未安装）
sudo apt install python3-tk

# 下载并运行
python3 proxy_setting_tool.py
```

### 方式二：从 Release 下载

从 [Releases](../../releases) 页面下载打包好的文件，解压后运行。

## 使用方法

1. **启动程序**：`python3 proxy_setting_tool.py`
2. **填写代理地址和端口**（如 `127.0.0.1:7890`）
3. **勾选要应用的作用域**：
   - GNOME 系统代理（推荐，Edge/Chrome 即时生效）
   - 环境变量代理（命令行工具使用）
   - APT 包管理器代理（需 root 权限）
4. **点击"一键应用"**
5. 如需单独启动带代理的浏览器，在"浏览器代理启动器"区域操作

## 技术原理

### GNOME 系统代理

通过 `gsettings` 命令修改 GNOME 的代理配置：

```bash
gsettings set org.gnome.system.proxy mode 'manual'
gsettings set org.gnome.system.proxy.http host '127.0.0.1'
gsettings set org.gnome.system.proxy.http port 7890
# https / ftp / socks 同理
```

Edge / Chrome 浏览器在 Linux 上默认读取 GNOME 系统代理设置，修改后即时生效。

### 环境变量代理

写入 `~/.config/proxy_env.sh` 并在 `~/.bashrc` 中 source：

```bash
export http_proxy="http://127.0.0.1:7890"
export https_proxy="http://127.0.0.1:7890"
export no_proxy="localhost,127.0.0.0/8,..."
```

### APT 代理配置

写入 `/etc/apt/apt.conf.d/95proxies`：

```
Acquire::http::Proxy "http://127.0.0.1:7890/";
Acquire::https::Proxy "http://127.0.0.1:7890/";
```

### 浏览器启动器

通过 Chromium 内核的 `--proxy-server` 参数启动：

```bash
microsoft-edge --proxy-server="http://127.0.0.1:7890"
```

## 适用系统

- Kali Linux (GNOME / XFCE)
- Debian 10+
- Ubuntu 18.04+
- Fedora 30+
- 其他使用 GNOME 桌面的 Linux 发行版

## 许可证

MIT License

## 贡献

欢迎提交 Issue 或 Pull Request。
