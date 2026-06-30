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
| 浏览器启动器 | 通过 `--proxy-server` 参数直接启动浏览器 | Edge / Chrome / Chromium（Firefox 不支持，需通过 GNOME 代理） |
| 浏览器包装脚本 | 创建始终带代理的启动脚本 | 可加入 PATH，每次启动都走代理 |
| 代理测试 | 通过 curl 测试代理是否可用，显示延迟 | — |
| 预设管理 | 保存常用代理配置，一键切换 | — |
| 状态实时检测 | 每 5 秒后台线程异步刷新，不阻塞 GUI | — |
| 多 Shell 支持 | 自动检测 bash/zsh 并写入对应配置文件 | — |
| KDE 桌面提示 | 检测到 KDE 环境时提示 gsettings 可能不生效 | — |

## 界面区域

程序界面包含以下区域：
- 当前代理状态（GNOME / 环境变量 / APT 三层面状态）
- 代理设置（地址、端口、no_proxy、预设管理）
- 作用域选择（勾选要应用的范围）
- 一键应用 / 测试代理 / 一键关闭
- 浏览器代理启动器

## 环境要求

- Python 3.6+
- Tkinter（`python3-tk`）
- `gsettings`（GNOME 桌面环境自带）
- 可选：`curl`（代理测试功能需要）
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

### 方式三：使用启动脚本

```bash
bash run.sh
# 启动脚本会自动检查 Python3 和 tkinter 依赖
```

## 使用方法

1. **启动程序**：`python3 proxy_setting_tool.py`
2. **填写代理地址和端口**（如 `127.0.0.1:7890`）
3. **勾选要应用的作用域**：
   - GNOME 系统代理（推荐，Edge/Chrome 即时生效）
   - 环境变量代理（命令行工具使用）
   - APT 包管理器代理（需 root 权限）
4. **点击"一键应用"**
5. 可点击"测试代理"验证代理是否可用
6. 如需单独启动带代理的浏览器，在"浏览器代理启动器"区域操作

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

写入 `~/.config/proxy_env.sh` 并自动检测用户 Shell（bash/zsh），在对应的配置文件（`~/.bashrc` / `~/.zshrc`）中 source：

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

> **注意**：Firefox 不支持 `--proxy-server` 命令行参数。Firefox 默认读取 GNOME 系统代理设置，请先通过本工具设置 GNOME 系统代理后再启动 Firefox。

### 代理测试

通过 curl 检测代理可用性：

```bash
curl -x http://127.0.0.1:7890 -s -o /dev/null -w "%{time_total}" http://httpbin.org/ip
```

## 适用系统

- Kali Linux (GNOME / XFCE)
- Debian 10+
- Ubuntu 18.04+
- Fedora 30+
- 其他使用 GNOME 桌面的 Linux 发行版
- KDE 环境：gsettings 代理可能不生效，建议使用环境变量代理或浏览器启动器

## 更新日志

### v1.1.0

**Bug 修复：**
- 修复 Firefox 不支持 `--proxy-server` 命令行参数的问题，改为提示用户通过 GNOME 系统代理设置
- 修复 `_auto_refresh` 在主线程调用 gsettings 导致 GUI 卡顿的问题（改为后台线程异步刷新）
- 修复状态刷新时预填逻辑覆盖用户正在输入的内容的问题
- 修复 APT 代理设置失败时临时文件 `/tmp/apt_proxy_95proxies` 未清理的问题
- 修复 Canvas 滚动区域不支持鼠标滚轮的问题

**改进：**
- 端口输入框添加数字验证，防止非法输入
- 所有端口转换添加异常处理，防止 ValueError 崩溃
- 支持 zsh，自动检测用户 Shell 并写入对应配置文件
- KDE 桌面环境检测与提示
- 删除未使用的 `DEFAULT_IGNORE_HOSTS` 和 `get_env_proxy` 方法
- 新增代理测试功能，通过 curl 检测代理是否可用并显示延迟

### v1.0.0

- 初始版本发布

## 许可证

MIT License

## 贡献

欢迎提交 Issue 或 Pull Request。
