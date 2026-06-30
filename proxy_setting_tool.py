# -*- coding: utf-8 -*-
"""
系统代理设置工具 (Linux 版)
============================
解决某些 Linux 系统（如 Kali）缺少图形化代理设置界面，
导致 Edge / Chrome 浏览器无法正常配置系统代理的问题。

本工具通过多层面设置实现完整的代理覆盖：
1. GNOME 系统代理 (gsettings) —— 桌面应用和 Edge/Chrome 浏览器读取
2. 环境变量 (http_proxy / https_proxy) —— 命令行工具 curl/wget/git 等
3. APT 代理配置 —— apt 包管理器
4. 浏览器启动器 —— 通过 --proxy-server 参数启动 Edge/Chrome

适用于 Kali / Debian / Ubuntu / Fedora 等主流 Linux 发行版。
"""

import os
import sys
import json
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

# ============================================================
# 平台检测
# ============================================================
if sys.platform != "linux":
    print("本工具专为 Linux 设计。当前系统：{}".format(sys.platform))
    sys.exit(1)


# ============================================================
# 配置文件路径
# ============================================================
CONFIG_FILE = Path.home() / ".config" / "proxy_setting_tool.json"

# 环境变量代理脚本路径（被 shell 配置文件 source）
ENV_PROXY_SCRIPT = Path.home() / ".config" / "proxy_env.sh"

# APT 代理配置文件路径
APT_PROXY_FILE = Path("/etc/apt/apt.conf.d/95proxies")

# 默认绕过列表
DEFAULT_NO_PROXY = (
    "localhost,127.0.0.0/8,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
)


# ============================================================
# 工具函数
# ============================================================
def run_cmd(cmd, timeout=5):
    """运行命令，返回 (返回码, stdout, stderr)。"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "命令超时"
    except FileNotFoundError:
        return -1, "", "命令不存在：{}".format(
            cmd[0] if isinstance(cmd, list) else cmd
        )
    except Exception as e:
        return -1, "", str(e)


def has_command(name):
    """检查系统中是否存在某命令。"""
    return shutil.which(name) is not None


def is_root():
    """检查是否以 root 运行。"""
    return os.geteuid() == 0


def sudo_prefix():
    """返回需要 sudo 时的前缀。"""
    if is_root():
        return []
    return ["pkexec"] if has_command("pkexec") else ["sudo"]


def detect_shell_config():
    """检测当前用户的 shell 配置文件。
    返回需要写入 source 行的 shell 配置文件列表。"""
    shells = os.environ.get("SHELL", "")
    config_files = []

    # 始终检查 .bashrc
    bashrc = Path.home() / ".bashrc"
    if bashrc.exists() or "bash" in shells:
        config_files.append(bashrc)

    # 如果使用 zsh，也写入 .zshrc
    zshrc = Path.home() / ".zshrc"
    if "zsh" in shells or zshrc.exists():
        config_files.append(zshrc)

    # 如果都没有，默认创建 .bashrc
    if not config_files:
        config_files.append(bashrc)

    return config_files


def validate_port(port_str):
    """验证端口字符串是否合法。"""
    if not port_str:
        return False
    if not port_str.isdigit():
        return False
    port = int(port_str)
    return 1 <= port <= 65535


# ============================================================
# 代理管理器
# ============================================================
class ProxyManager:
    """封装多层面的代理设置操作。"""

    def __init__(self):
        self.last_error = ""
        self.has_gsettings = has_command("gsettings")
        self.has_apt = Path("/etc/apt").exists()
        self.has_curl = has_command("curl")
        self.desktop = self._detect_desktop()

    # ---------- 桌面环境检测 ----------
    def _detect_desktop(self):
        """检测当前桌面环境。"""
        de = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
        session = os.environ.get("DESKTOP_SESSION", "").lower()
        if "GNOME" in de or "GNOME" in session:
            return "GNOME"
        if "XFCE" in de or "xfce" in session:
            return "XFCE"
        if "KDE" in de:
            return "KDE"
        return de or "未知"

    @property
    def gnome_compatible(self):
        """当前桌面环境是否兼容 GNOME gsettings 代理设置。"""
        # GNOME/XFCE 可用 gsettings；KDE 通常不适用
        return self.desktop in ("GNOME", "XFCE")

    # ============================================================
    # 1. GNOME 系统代理 (gsettings)
    # ============================================================
    def get_gnome_proxy(self):
        """读取 GNOME 系统代理设置。"""
        if not self.has_gsettings:
            return {
                "available": False, "mode": "none", "http": "",
                "https": "", "ftp": "", "socks": "",
                "ignore_hosts": "", "autoconfig_url": "",
            }

        result = {
            "available": True, "mode": "none", "http": "",
            "https": "", "ftp": "", "socks": "",
            "ignore_hosts": "", "autoconfig_url": "",
        }

        # 读取模式
        code, mode, _ = run_cmd(
            ["gsettings", "get", "org.gnome.system.proxy", "mode"]
        )
        if code == 0:
            # gsettings 返回 'manual' 格式，去掉单引号
            result["mode"] = mode.strip("'\"")

        # 读取各协议代理
        for proto in ["http", "https", "ftp", "socks"]:
            _, host, _ = run_cmd(
                ["gsettings", "get",
                 "org.gnome.system.proxy.{}".format(proto), "host"]
            )
            _, port, _ = run_cmd(
                ["gsettings", "get",
                 "org.gnome.system.proxy.{}".format(proto), "port"]
            )
            host = host.strip("'\"")
            port = port.strip()
            if host and port and port != "0":
                result[proto] = "{}:{}".format(host, port)

        # 读取忽略主机
        _, ignore, _ = run_cmd(
            ["gsettings", "get", "org.gnome.system.proxy", "ignore-hosts"]
        )
        result["ignore_hosts"] = ignore.strip()

        # 读取 PAC 自动配置 URL
        _, url, _ = run_cmd(
            ["gsettings", "get", "org.gnome.system.proxy", "autoconfig-url"]
        )
        result["autoconfig_url"] = url.strip("'\"")

        return result

    def set_gnome_proxy(self, address, port, no_proxy_list=None):
        """设置 GNOME 手动代理。"""
        if not self.has_gsettings:
            self.last_error = "未安装 gsettings，无法设置 GNOME 系统代理。"
            return False
        if not address:
            self.last_error = "代理地址不能为空。"
            return False

        # [修复] 端口转换添加异常处理
        try:
            port = int(port)
        except (ValueError, TypeError):
            self.last_error = "端口必须是数字。"
            return False

        if not (1 <= port <= 65535):
            self.last_error = "端口必须在 1-65535 范围内。"
            return False

        # 设置各协议代理
        commands = [
            ["gsettings", "set", "org.gnome.system.proxy", "mode", "manual"],
            ["gsettings", "set", "org.gnome.system.proxy.http",
             "host", address],
            ["gsettings", "set", "org.gnome.system.proxy.http",
             "port", str(port)],
            ["gsettings", "set", "org.gnome.system.proxy.https",
             "host", address],
            ["gsettings", "set", "org.gnome.system.proxy.https",
             "port", str(port)],
            ["gsettings", "set", "org.gnome.system.proxy.ftp",
             "host", address],
            ["gsettings", "set", "org.gnome.system.proxy.ftp",
             "port", str(port)],
            ["gsettings", "set", "org.gnome.system.proxy.socks",
             "host", address],
            ["gsettings", "set", "org.gnome.system.proxy.socks",
             "port", str(port)],
        ]

        # 设置忽略主机列表
        if no_proxy_list:
            ignore_val = "['{}']".format("', '".join(
                h.strip() for h in no_proxy_list.split(",")
                if h.strip()
            ))
            commands.append(
                ["gsettings", "set", "org.gnome.system.proxy",
                 "ignore-hosts", ignore_val]
            )

        for cmd in commands:
            code, _, err = run_cmd(cmd)
            if code != 0:
                self.last_error = "gsettings 设置失败：{}".format(err)
                return False
        return True

    def disable_gnome_proxy(self):
        """关闭 GNOME 系统代理。"""
        if not self.has_gsettings:
            return True  # 没有 gsettings 视为已关闭
        code, _, err = run_cmd(
            ["gsettings", "set", "org.gnome.system.proxy", "mode", "none"]
        )
        if code != 0:
            self.last_error = "关闭 GNOME 代理失败：{}".format(err)
            return False
        return True

    # ============================================================
    # 2. 环境变量代理 (http_proxy 等)
    # ============================================================
    def get_persistent_env_proxy(self):
        """读取持久化的环境变量代理配置文件。"""
        if ENV_PROXY_SCRIPT.exists():
            content = ENV_PROXY_SCRIPT.read_text(encoding="utf-8")
            result = {}
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("export "):
                    line = line[7:]
                    if "=" in line:
                        key, val = line.split("=", 1)
                        val = val.strip('"\'')
                        result[key] = val
            return result
        return {}

    def set_env_proxy(self, address, port, no_proxy=None):
        """写入环境变量代理脚本，并添加到 shell 配置文件。"""
        # [修复] 端口转换异常处理
        try:
            port_int = int(port)
        except (ValueError, TypeError):
            self.last_error = "端口必须是数字。"
            return False

        proxy_url = "http://{}:{}".format(address, port_int)
        content = (
            "# 由系统代理设置工具生成\n"
            "export http_proxy=\"{proxy}\"\n"
            "export https_proxy=\"{proxy}\"\n"
            "export HTTP_PROXY=\"{proxy}\"\n"
            "export HTTPS_PROXY=\"{proxy}\"\n"
            "export no_proxy=\"{no_proxy}\"\n"
            "export NO_PROXY=\"{no_proxy}\"\n"
        ).format(proxy=proxy_url, no_proxy=no_proxy or DEFAULT_NO_PROXY)

        try:
            ENV_PROXY_SCRIPT.parent.mkdir(parents=True, exist_ok=True)
            ENV_PROXY_SCRIPT.write_text(content, encoding="utf-8")
            ENV_PROXY_SCRIPT.chmod(0o644)

            # [修复] 确保被所有 shell 配置文件 source
            self._ensure_shell_source()
            return True
        except PermissionError:
            self.last_error = "写入环境变量配置被拒绝。"
            return False
        except Exception as e:
            self.last_error = "写入环境变量配置失败：{}".format(e)
            return False

    def _ensure_shell_source(self):
        """[修复] 确保所有 shell 配置文件中都有 source proxy_env.sh 的行。"""
        source_line = 'source "$HOME/.config/proxy_env.sh" 2>/dev/null'
        config_files = detect_shell_config()

        for config_file in config_files:
            existing = ""
            if config_file.exists():
                existing = config_file.read_text(
                    encoding="utf-8", errors="ignore"
                )

            if source_line not in existing:
                with open(config_file, "a", encoding="utf-8") as f:
                    f.write("\n# 加载代理环境变量\n")
                    f.write(source_line + "\n")

    def disable_env_proxy(self):
        """移除环境变量代理配置。"""
        try:
            if ENV_PROXY_SCRIPT.exists():
                ENV_PROXY_SCRIPT.unlink()
            # [修复] 从所有 shell 配置文件移除 source 行
            config_files = detect_shell_config()
            for config_file in config_files:
                if config_file.exists():
                    lines = config_file.read_text(
                        encoding="utf-8", errors="ignore"
                    ).splitlines()
                    new_lines = [
                        line for line in lines
                        if "proxy_env.sh" not in line
                        and "# 加载代理环境变量" not in line
                    ]
                    config_file.write_text(
                        "\n".join(new_lines) + "\n", encoding="utf-8"
                    )
            return True
        except Exception as e:
            self.last_error = "移除环境变量代理失败：{}".format(e)
            return False

    # ============================================================
    # 3. APT 代理配置
    # ============================================================
    def get_apt_proxy(self):
        """读取 APT 代理配置。"""
        if not self.has_apt:
            return {"available": False, "http": "", "https": ""}
        result = {"available": True, "http": "", "https": ""}
        if APT_PROXY_FILE.exists():
            content = APT_PROXY_FILE.read_text(encoding="utf-8")
            for line in content.splitlines():
                line = line.strip()
                if "Acquire::http::Proxy" in line:
                    result["http"] = (
                        line.split('"')[1] if '"' in line else ""
                    )
                elif "Acquire::https::Proxy" in line:
                    result["https"] = (
                        line.split('"')[1] if '"' in line else ""
                    )
        return result

    def set_apt_proxy(self, address, port):
        """写入 APT 代理配置文件（需要 root 权限）。"""
        if not self.has_apt:
            self.last_error = "未检测到 APT 包管理器。"
            return False

        # [修复] 端口转换异常处理
        try:
            port_int = int(port)
        except (ValueError, TypeError):
            self.last_error = "端口必须是数字。"
            return False

        proxy_url = "http://{}:{}/".format(address, port_int)
        content = (
            "# 由系统代理设置工具生成\n"
            'Acquire::http::Proxy "{proxy}";\n'
            'Acquire::https::Proxy "{proxy}";\n'
        ).format(proxy=proxy_url)

        # [修复] 使用 try/finally 确保临时文件被清理
        tmp = None
        try:
            if is_root():
                APT_PROXY_FILE.parent.mkdir(parents=True, exist_ok=True)
                APT_PROXY_FILE.write_text(content, encoding="utf-8")
            else:
                # 通过 pkexec / sudo 写入临时文件再移动
                tmp = Path("/tmp/apt_proxy_95proxies")
                tmp.write_text(content, encoding="utf-8")
                prefix = sudo_prefix()
                if not prefix:
                    self.last_error = (
                        "需要 root 权限写入 APT 配置，"
                        "但未找到 pkexec/sudo。"
                    )
                    return False
                cmd = prefix + ["cp", str(tmp), str(APT_PROXY_FILE)]
                code, _, err = run_cmd(cmd)
                if code != 0:
                    self.last_error = (
                        "写入 APT 配置失败（需要权限）：{}".format(err)
                    )
                    return False
            return True
        except Exception as e:
            self.last_error = "写入 APT 代理配置失败：{}".format(e)
            return False
        finally:
            # [修复] 无论成功失败都清理临时文件
            if tmp is not None and tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass

    def disable_apt_proxy(self):
        """移除 APT 代理配置文件。"""
        if not self.has_apt:
            return True
        if not APT_PROXY_FILE.exists():
            return True
        try:
            if is_root():
                APT_PROXY_FILE.unlink()
            else:
                prefix = sudo_prefix()
                if not prefix:
                    self.last_error = "需要 root 权限删除 APT 配置。"
                    return False
                cmd = prefix + ["rm", "-f", str(APT_PROXY_FILE)]
                code, _, err = run_cmd(cmd)
                if code != 0:
                    self.last_error = "删除 APT 配置失败：{}".format(err)
                    return False
            return True
        except Exception as e:
            self.last_error = "移除 APT 代理失败：{}".format(e)
            return False

    # ============================================================
    # 4. 浏览器启动器
    # ============================================================
    def find_browser(self):
        """查找已安装的浏览器，返回 {名称: 路径} 字典。"""
        browsers = {}
        candidates = [
            ("Microsoft Edge",
             ["microsoft-edge", "microsoft-edge-stable"]),
            ("Google Chrome",
             ["google-chrome", "google-chrome-stable", "chromium"]),
            ("Chromium",
             ["chromium-browser", "chromium"]),
            ("Firefox",
             ["firefox", "firefox-esr"]),
        ]
        for name, cmds in candidates:
            for cmd in cmds:
                path = shutil.which(cmd)
                if path:
                    browsers[name] = path
                    break
        return browsers

    def launch_browser_with_proxy(self, browser_name, browser_path,
                                  address, port):
        """使用 --proxy-server 参数启动浏览器。
        [修复] Firefox 不支持 --proxy-server，需要特殊处理。"""
        # [修复] Firefox 不支持 --proxy-server 命令行参数
        # Firefox 默认读取 GNOME 系统代理设置
        if "firefox" in browser_name.lower():
            self.last_error = (
                "Firefox 不支持 --proxy-server 命令行参数。"
                "Firefox 默认读取 GNOME 系统代理设置，"
                "请先通过本工具设置 GNOME 系统代理后再启动 Firefox。"
            )
            return False

        # [修复] 端口转换异常处理
        try:
            port_int = int(port)
        except (ValueError, TypeError):
            self.last_error = "端口必须是数字。"
            return False

        proxy_arg = "http://{}:{}".format(address, port_int)
        try:
            subprocess.Popen(
                [browser_path, "--proxy-server=" + proxy_arg],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception as e:
            self.last_error = "启动浏览器失败：{}".format(e)
            return False

    def create_browser_wrapper(self, browser_path, address, port):
        """创建浏览器包装脚本，始终带代理启动。"""
        # [修复] 端口转换异常处理
        try:
            port_int = int(port)
        except (ValueError, TypeError):
            self.last_error = "端口必须是数字。"
            return None

        proxy_arg = "http://{}:{}".format(address, port_int)
        wrapper_dir = Path.home() / ".local" / "bin"
        wrapper_dir.mkdir(parents=True, exist_ok=True)

        browser_name = Path(browser_path).name
        wrapper = wrapper_dir / "{}-proxy".format(browser_name)

        content = (
            "#!/bin/bash\n"
            "# 由系统代理设置工具生成的浏览器代理启动器\n"
            '# 始终通过 {} 代理启动 {}\n'
            'exec "{}" --proxy-server="{}" "$@"\n'
        ).format(proxy_arg, browser_name, browser_path, proxy_arg)

        try:
            wrapper.write_text(content, encoding="utf-8")
            wrapper.chmod(0o755)
            return str(wrapper)
        except Exception as e:
            self.last_error = "创建浏览器包装脚本失败：{}".format(e)
            return None

    # ============================================================
    # 5. 代理测试 [新增]
    # ============================================================
    def test_proxy(self, address, port, timeout=5):
        """通过 curl 测试代理是否可用。
        返回 (是否成功, 延迟毫秒, 错误信息)。"""
        if not self.has_curl:
            return False, 0, "系统未安装 curl，无法测试。"

        proxy_url = "http://{}:{}".format(address, port)
        # 使用 httpbin 检测 IP，同时测量延迟
        cmd = [
            "curl", "-x", proxy_url,
            "-s", "-o", "/dev/null",
            "-w", "%{time_total}",
            "--connect-timeout", str(timeout),
            "--max-time", str(timeout + 5),
            "http://httpbin.org/ip",
        ]
        import time
        start = time.time()
        code, stdout, stderr = run_cmd(cmd, timeout=timeout + 10)
        elapsed = (time.time() - start) * 1000  # 转为毫秒

        if code == 0:
            try:
                delay = int(float(stdout) * 1000)
                return True, delay, ""
            except (ValueError, TypeError):
                return True, int(elapsed), ""
        else:
            return False, int(elapsed), stderr or "连接失败"

    # ============================================================
    # 一键应用 / 关闭
    # ============================================================
    def apply_all(self, address, port, no_proxy=None, enable_gnome=True,
                  enable_env=True, enable_apt=False):
        """一键设置所有层面的代理。"""
        results = []
        if enable_gnome and self.has_gsettings:
            if self.set_gnome_proxy(address, port, no_proxy):
                results.append("GNOME 系统代理：已设置")
            else:
                results.append(
                    "GNOME 系统代理：失败 - {}".format(self.last_error)
                )

        if enable_env:
            if self.set_env_proxy(address, port, no_proxy):
                results.append(
                    "环境变量代理：已设置（重新打开终端生效）"
                )
            else:
                results.append(
                    "环境变量代理：失败 - {}".format(self.last_error)
                )

        if enable_apt and self.has_apt:
            if self.set_apt_proxy(address, port):
                results.append("APT 代理：已设置")
            else:
                results.append(
                    "APT 代理：失败 - {}".format(self.last_error)
                )

        return results

    def disable_all(self, disable_gnome=True, disable_env=True,
                    disable_apt=False):
        """一键关闭所有层面的代理。"""
        results = []
        if disable_gnome and self.has_gsettings:
            if self.disable_gnome_proxy():
                results.append("GNOME 系统代理：已关闭")
            else:
                results.append(
                    "GNOME 系统代理：失败 - {}".format(self.last_error)
                )

        if disable_env:
            if self.disable_env_proxy():
                results.append("环境变量代理：已移除")
            else:
                results.append(
                    "环境变量代理：失败 - {}".format(self.last_error)
                )

        if disable_apt and self.has_apt:
            if self.disable_apt_proxy():
                results.append("APT 代理：已移除")
            else:
                results.append(
                    "APT 代理：失败 - {}".format(self.last_error)
                )

        return results


# ============================================================
# 配置保存/加载
# ============================================================
def save_config(config):
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def load_config():
    default = {
        "presets": [],
        "last_address": "127.0.0.1",
        "last_port": "7890",
    }
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                default.update(cfg)
    except Exception:
        pass
    return default


# ============================================================
# GUI 主程序
# ============================================================
class ProxySettingApp:
    """系统代理设置工具的主界面。"""

    BG = "#f5f6f8"
    CARD_BG = "#ffffff"
    ACCENT = "#2b6cb0"
    ACCENT_HOVER = "#2c5282"
    DANGER = "#c53030"
    SUCCESS = "#2f855a"
    WARNING = "#d69e2e"
    TEXT = "#1a202c"
    MUTED = "#718096"

    def __init__(self, root):
        self.root = root
        self.manager = ProxyManager()
        self.config = load_config()

        # [修复] 标记是否已完成初始化预填
        self._initialized = False

        self._setup_window()
        self._build_styles()
        self._build_ui()

        # [修复] 初始化时预填一次当前 GNOME 代理
        self._prefill_from_current()

        self._initialized = True
        self._refresh_status_async()

    # ---------- 窗口 ----------
    def _setup_window(self):
        self.root.title("系统代理设置工具 (Linux)")
        self.root.geometry("620x780")
        self.root.minsize(580, 700)
        self.root.configure(bg=self.BG)

    # ---------- 样式 ----------
    def _build_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("TFrame", background=self.BG)
        style.configure("Card.TFrame", background=self.CARD_BG)
        style.configure("TLabel", background=self.BG, foreground=self.TEXT)
        style.configure("Card.TLabel",
                        background=self.CARD_BG, foreground=self.TEXT)
        style.configure("Title.TLabel",
                        background=self.BG, foreground=self.TEXT,
                        font=("Sans", 16, "bold"))
        style.configure("Subtitle.TLabel",
                        background=self.BG, foreground=self.MUTED,
                        font=("Sans", 9))
        style.configure("Status.TLabel",
                        background=self.CARD_BG,
                        font=("Sans", 10, "bold"))
        style.configure("Muted.TLabel",
                        background=self.CARD_BG,
                        foreground=self.MUTED, font=("Sans", 9))
        style.configure("Accent.TButton", font=("Sans", 10, "bold"))
        style.map("Accent.TButton",
                  background=[
                      ("active", self.ACCENT_HOVER),
                      ("!disabled", self.ACCENT),
                  ],
                  foreground=[("!disabled", "#ffffff")])
        style.configure("Danger.TButton", font=("Sans", 10))
        style.map("Danger.TButton",
                  background=[
                      ("active", "#9b2c2c"),
                      ("!disabled", self.DANGER),
                  ],
                  foreground=[("!disabled", "#ffffff")])
        style.configure("Test.TButton", font=("Sans", 10))
        style.map("Test.TButton",
                  background=[
                      ("active", "#319795"),
                      ("!disabled", "#319795"),
                  ],
                  foreground=[("!disabled", "#ffffff")])

    # ---------- 构建 UI ----------
    def _build_ui(self):
        # [修复] 使用 Canvas + Scrollbar 支持滚动 + 鼠标滚轮
        self.canvas = tk.Canvas(
            self.root, bg=self.BG, highlightthickness=0
        )
        scrollbar = ttk.Scrollbar(
            self.root, orient="vertical", command=self.canvas.yview
        )
        self.main = ttk.Frame(self.canvas)
        self.main.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            )
        )
        self.canvas_window = self.canvas.create_window(
            (0, 0), window=self.main, anchor="nw"
        )
        # [修复] 绑定 canvas 宽度变化，使内容自适应
        self.canvas.bind(
            "<Configure>",
            self._on_canvas_configure
        )
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # [修复] 绑定鼠标滚轮事件
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)

        # 内部 padding 容器
        content = ttk.Frame(self.main)
        content.pack(fill="both", expand=True, padx=20, pady=15)

        # ---- 标题区 ----
        header = ttk.Frame(content)
        header.pack(fill="x")
        ttk.Label(
            header, text="系统代理设置工具", style="Title.TLabel"
        ).pack(anchor="w")

        # [修复] KDE 桌面环境提示
        header_info = "桌面环境：{}  |  gsettings：{}  |  APT：{}".format(
            self.manager.desktop,
            "可用" if self.manager.has_gsettings else "不可用",
            "可用" if self.manager.has_apt else "不可用",
        )
        if (self.manager.desktop == "KDE"
                and not self.manager.gnome_compatible):
            header_info += "\n[提示] KDE 环境下 gsettings 代理可能不生效，建议使用环境变量代理或浏览器启动器。"
        ttk.Label(
            header, text=header_info, style="Subtitle.TLabel"
        ).pack(anchor="w", pady=(2, 0))

        # ---- 当前状态卡片 ----
        status_card = self._card(content, "当前代理状态")
        self.status_label = ttk.Label(
            status_card, text="检测中...", style="Status.TLabel",
            foreground=self.MUTED
        )
        self.status_label.pack(anchor="w", pady=(0, 4))
        self.status_detail = ttk.Label(
            status_card, text="", style="Muted.TLabel",
            wraplength=540, justify="left"
        )
        self.status_detail.pack(anchor="w")
        ttk.Button(
            status_card, text="刷新", command=self._refresh_status_async
        ).pack(anchor="e", pady=(6, 0))

        # ---- 代理设置卡片 ----
        proxy_card = self._card(content, "代理设置")
        self._build_proxy_inputs(proxy_card)

        # ---- 作用域选择 ----
        scope_card = self._card(content, "作用域（勾选要应用的范围）")
        self.scope_gnome = tk.BooleanVar(value=True)
        self.scope_env = tk.BooleanVar(value=True)
        self.scope_apt = tk.BooleanVar(value=False)

        for var, label, desc in [
            (self.scope_gnome, "GNOME 系统代理",
             "桌面应用和 Edge/Chrome 浏览器读取（推荐）"),
            (self.scope_env, "环境变量代理",
             "命令行工具 curl/wget/git 等（需重开终端生效）"),
            (self.scope_apt, "APT 包管理器代理",
             "apt update/install 走代理（需 root 权限）"),
        ]:
            row = ttk.Frame(scope_card, style="Card.TFrame")
            row.pack(fill="x", pady=2)
            ttk.Checkbutton(
                row, text=label, variable=var
            ).pack(anchor="w")
            ttk.Label(
                row, text=desc, style="Muted.TLabel"
            ).pack(anchor="w", padx=(20, 0))

        # ---- 按钮区 ----
        btn_frame = ttk.Frame(content)
        btn_frame.pack(fill="x", pady=(4, 0))
        ttk.Button(
            btn_frame, text="一键应用", style="Accent.TButton",
            command=self._apply_all
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ttk.Button(
            btn_frame, text="测试代理", style="Test.TButton",
            command=self._test_proxy
        ).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(
            btn_frame, text="一键关闭", style="Danger.TButton",
            command=self._disable_all
        ).pack(side="left", fill="x", expand=True, padx=(4, 0))

        # ---- 浏览器启动区 ----
        browser_card = self._card(content, "浏览器代理启动器")
        self._build_browser_section(browser_card)

        # ---- 底部提示 ----
        ttk.Label(
            content,
            text="提示：GNOME 代理即时生效；环境变量需重新打开终端；"
                 "APT 配置需要管理员权限。Firefox 请通过 GNOME 系统代理设置。",
            style="Subtitle.TLabel", wraplength=560,
        ).pack(anchor="w", pady=(8, 0))

    def _build_proxy_inputs(self, parent):
        # 地址
        addr_row = ttk.Frame(parent, style="Card.TFrame")
        addr_row.pack(fill="x", pady=(0, 6))
        ttk.Label(
            addr_row, text="代理地址：", style="Card.TLabel", width=10
        ).pack(side="left")
        self.addr_entry = ttk.Entry(addr_row, width=40)
        self.addr_entry.pack(side="left", fill="x", expand=True)
        self.addr_entry.insert(
            0, self.config.get("last_address", "127.0.0.1")
        )

        # [修复] 端口输入框添加数字验证
        port_row = ttk.Frame(parent, style="Card.TFrame")
        port_row.pack(fill="x", pady=(0, 6))
        ttk.Label(
            port_row, text="端口：", style="Card.TLabel", width=10
        ).pack(side="left")
        vcmd = (self.root.register(self._validate_port_input), "%P")
        self.port_entry = ttk.Entry(
            port_row, width=10, validate="key", validatecommand=vcmd
        )
        self.port_entry.pack(side="left")
        self.port_entry.insert(
            0, self.config.get("last_port", "7890")
        )

        # 预设
        preset_row = ttk.Frame(parent, style="Card.TFrame")
        preset_row.pack(fill="x", pady=(0, 6))
        ttk.Label(
            preset_row, text="常用预设：", style="Card.TLabel", width=10
        ).pack(side="left")
        self.preset_combo = ttk.Combobox(
            preset_row, state="readonly", width=28
        )
        self.preset_combo.pack(side="left", padx=(0, 6))
        ttk.Button(
            preset_row, text="保存预设",
            command=self._save_preset
        ).pack(side="left")
        ttk.Button(
            preset_row, text="删除",
            command=self._delete_preset
        ).pack(side="left", padx=(4, 0))
        self._update_preset_combo()
        self.preset_combo.bind("<<ComboboxSelected>>", self._load_preset)

        # no_proxy
        np_row = ttk.Frame(parent, style="Card.TFrame")
        np_row.pack(fill="x", pady=(0, 6))
        ttk.Label(
            np_row, text="no_proxy：", style="Card.TLabel", width=10
        ).pack(side="left")
        self.noproxy_entry = ttk.Entry(np_row, width=40)
        self.noproxy_entry.pack(side="left", fill="x", expand=True)
        self.noproxy_entry.insert(0, DEFAULT_NO_PROXY)

    def _build_browser_section(self, parent):
        browsers = self.manager.find_browser()
        if not browsers:
            ttk.Label(
                parent, text="未检测到已安装的浏览器。",
                style="Muted.TLabel"
            ).pack(anchor="w")
            return

        ttk.Label(
            parent,
            text="点击启动浏览器（带 --proxy-server 参数）。\n"
                 "注意：Firefox 不支持命令行代理参数，请先设置 GNOME 系统代理。",
            style="Muted.TLabel", wraplength=540, justify="left"
        ).pack(anchor="w", pady=(0, 4))

        for name, path in browsers.items():
            row = ttk.Frame(parent, style="Card.TFrame")
            row.pack(fill="x", pady=2)
            ttk.Button(
                row, text="启动 {}".format(name), width=18,
                command=lambda n=name, p=path: self._launch_browser(n, p),
            ).pack(side="left")
            ttk.Button(
                row, text="创建包装脚本", width=14,
                command=lambda n=name, p=path: self._create_wrapper(n, p),
            ).pack(side="left", padx=(6, 0))
            ttk.Label(
                row, text=path, style="Muted.TLabel"
            ).pack(side="left", padx=(6, 0))

    # ---------- 卡片辅助 ----------
    def _card(self, parent, title):
        card = tk.Frame(
            parent, bg=self.CARD_BG,
            highlightbackground="#e2e8f0", highlightthickness=1, bd=0
        )
        card.pack(fill="x", pady=(0, 10))
        inner = tk.Frame(card, bg=self.CARD_BG)
        inner.pack(fill="x", padx=12, pady=10)
        tk.Label(
            inner, text=title, bg=self.CARD_BG, fg=self.TEXT,
            font=("Sans", 11, "bold"), anchor="w"
        ).pack(fill="x", pady=(0, 6))
        content = tk.Frame(inner, bg=self.CARD_BG)
        content.pack(fill="x")
        return content

    # ---------- [修复] Canvas 相关 ----------
    def _on_canvas_configure(self, event):
        """Canvas 大小变化时，调整内部 frame 宽度以自适应。"""
        self.canvas.itemconfig(
            self.canvas_window, width=event.width
        )

    def _on_mousewheel(self, event):
        """[修复] 鼠标滚轮滚动支持。"""
        if event.num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(1, "units")
        else:
            # Linux 上通常无 event.num，使用 event.delta
            self.canvas.yview_scroll(
                int(-1 * (event.delta / 120)), "units"
            )

    # ---------- [修复] 端口输入验证 ----------
    def _validate_port_input(self, new_value):
        """只允许输入数字（或空）。"""
        if not new_value:
            return True
        return new_value.isdigit() and len(new_value) <= 5

    # ---------- [修复] 初始化预填 ----------
    def _prefill_from_current(self):
        """初始化时从当前 GNOME 代理预填地址和端口。"""
        g = self.manager.get_gnome_proxy()
        if g["available"] and g["mode"] == "manual" and g["http"]:
            try:
                addr, port = g["http"].rsplit(":", 1)
                self.addr_entry.delete(0, tk.END)
                self.addr_entry.insert(0, addr)
                self.port_entry.delete(0, tk.END)
                self.port_entry.insert(0, port)
            except (ValueError, IndexError):
                pass

    # ---------- 应用 / 关闭 ----------
    def _apply_all(self):
        address = self.addr_entry.get().strip()
        port = self.port_entry.get().strip()
        no_proxy = self.noproxy_entry.get().strip()

        if not address:
            messagebox.showerror("错误", "代理地址不能为空。")
            return
        if not validate_port(port):
            messagebox.showerror("错误", "端口必须是 1-65535 之间的数字。")
            return

        results = self.manager.apply_all(
            address, port, no_proxy,
            enable_gnome=self.scope_gnome.get(),
            enable_env=self.scope_env.get(),
            enable_apt=self.scope_apt.get(),
        )

        self.config["last_address"] = address
        self.config["last_port"] = port
        save_config(self.config)

        self._refresh_status_async()
        messagebox.showinfo(
            "结果", "\n".join(results) if results else "无操作"
        )

    def _disable_all(self):
        results = self.manager.disable_all(
            disable_gnome=self.scope_gnome.get(),
            disable_env=self.scope_env.get(),
            disable_apt=self.scope_apt.get(),
        )
        self._refresh_status_async()
        messagebox.showinfo(
            "结果", "\n".join(results) if results else "无操作"
        )

    # ---------- [新增] 测试代理 ----------
    def _test_proxy(self):
        address = self.addr_entry.get().strip()
        port = self.port_entry.get().strip()

        if not address:
            messagebox.showerror("错误", "代理地址不能为空。")
            return
        if not validate_port(port):
            messagebox.showerror("错误", "端口必须是 1-65535 之间的数字。")
            return

        # 创建进度窗口
        dlg = tk.Toplevel(self.root)
        dlg.title("测试代理")
        dlg.geometry("300x100")
        dlg.transient(self.root)
        dlg.grab_set()
        ttk.Label(
            dlg, text="正在测试代理 {}:{}...".format(address, port),
            padding=20
        ).pack()
        pb = ttk.Progressbar(dlg, mode="indeterminate")
        pb.pack(fill="x", padx=20, pady=(0, 20))
        pb.start(10)
        dlg.update()

        # 在后台线程测试
        def run_test():
            ok, delay, err = self.manager.test_proxy(address, port)
            dlg.after(0, lambda: self._show_test_result(dlg, ok, delay, err))

        threading.Thread(target=run_test, daemon=True).start()

    def _show_test_result(self, dlg, ok, delay, err):
        """显示测试结果。"""
        try:
            pb = dlg.winfo_children()[1]
            pb.stop()
        except (IndexError, tk.TclError):
            pass
        dlg.destroy()

        if ok:
            messagebox.showinfo(
                "测试成功",
                "代理 {} 可用！\n延迟：{} ms".format(
                    self.addr_entry.get().strip() + ":"
                    + self.port_entry.get().strip(),
                    delay
                )
            )
        else:
            messagebox.showerror(
                "测试失败",
                "代理连接失败。\n错误：{}".format(err)
            )

    # ---------- [修复] 后台线程刷新状态 ----------
    def _refresh_status_async(self):
        """在后台线程中获取代理状态，避免阻塞 GUI。"""
        def worker():
            # 在后台线程中执行所有 gsettings 命令
            gnome = self.manager.get_gnome_proxy()
            env = self.manager.get_persistent_env_proxy()
            apt = self.manager.get_apt_proxy()
            # 在主线程更新 GUI
            self.root.after(
                0, lambda: self._update_status_ui(gnome, env, apt)
            )

        threading.Thread(target=worker, daemon=True).start()

    def _update_status_ui(self, g, env, apt):
        """在主线程中更新状态 UI。"""
        lines = []

        # GNOME 代理
        if g["available"]:
            if g["mode"] == "manual":
                lines.append("[GNOME] 手动代理已开启")
                for proto in ["http", "https", "ftp", "socks"]:
                    if g[proto]:
                        lines.append(
                            "  {} -> {}".format(proto.upper(), g[proto])
                        )
                if g["ignore_hosts"]:
                    lines.append(
                        "  忽略主机：{}".format(g["ignore_hosts"])
                    )
            elif g["mode"] == "auto":
                lines.append("[GNOME] PAC 自动代理已开启")
                lines.append("  PAC URL：{}".format(g["autoconfig_url"]))
            else:
                lines.append("[GNOME] 代理已关闭（直连）")
        else:
            lines.append("[GNOME] gsettings 不可用")

        # 环境变量代理
        if env.get("http_proxy"):
            lines.append("[环境变量] 代理已设置")
            lines.append("  http_proxy={}".format(env["http_proxy"]))
        else:
            lines.append("[环境变量] 代理未配置")

        # APT 代理
        if apt["available"]:
            if apt["http"] or apt["https"]:
                lines.append("[APT] 代理已设置")
                if apt["http"]:
                    lines.append("  HTTP: {}".format(apt["http"]))
                if apt["https"]:
                    lines.append("  HTTPS: {}".format(apt["https"]))
            else:
                lines.append("[APT] 代理未配置")
        else:
            lines.append("[APT] APT 不可用")

        detail_text = "\n".join(lines)
        has_proxy = (
            (g["available"] and g["mode"] in ("manual", "auto"))
            or bool(env.get("http_proxy"))
            or bool(apt.get("http") or apt.get("https"))
        )

        if has_proxy:
            self.status_label.configure(
                text="● 代理已开启", foreground=self.SUCCESS
            )
        else:
            self.status_label.configure(
                text="○ 代理已关闭", foreground=self.MUTED
            )
        self.status_detail.configure(text=detail_text)

        # [修复] 不再在自动刷新时预填，避免覆盖用户输入

    def _auto_refresh(self):
        """定时异步刷新状态。"""
        self._refresh_status_async()
        self.root.after(5000, self._auto_refresh)

    # ---------- 预设管理 ----------
    def _save_preset(self):
        address = self.addr_entry.get().strip()
        port = self.port_entry.get().strip()
        if not address or not port:
            messagebox.showerror("错误", "请先填写地址和端口。")
            return
        name = "{}:{}".format(address, port)
        presets = self.config.setdefault("presets", [])
        if not any(p.get("name") == name for p in presets):
            presets.append(
                {"name": name, "address": address, "port": port}
            )
            save_config(self.config)
            self._update_preset_combo()
            messagebox.showinfo("成功", "已保存预设 {}。".format(name))
        else:
            messagebox.showwarning("提示", "该预设已存在。")

    def _delete_preset(self):
        name = self.preset_combo.get()
        if not name:
            return
        self.config["presets"] = [
            p for p in self.config.get("presets", [])
            if p.get("name") != name
        ]
        save_config(self.config)
        self._update_preset_combo()
        messagebox.showinfo("成功", "已删除预设 {}。".format(name))

    def _update_preset_combo(self):
        names = [p.get("name", "")
                 for p in self.config.get("presets", [])]
        self.preset_combo.configure(values=names)
        if names:
            self.preset_combo.set(names[0])

    def _load_preset(self, event=None):
        name = self.preset_combo.get()
        for p in self.config.get("presets", []):
            if p.get("name") == name:
                self.addr_entry.delete(0, tk.END)
                self.addr_entry.insert(0, p["address"])
                self.port_entry.delete(0, tk.END)
                self.port_entry.insert(0, str(p["port"]))
                break

    # ---------- 浏览器 ----------
    def _launch_browser(self, name, path):
        address = self.addr_entry.get().strip()
        port = self.port_entry.get().strip()
        if not address or not port:
            messagebox.showerror("错误", "请先填写代理地址和端口。")
            return
        if self.manager.launch_browser_with_proxy(
            name, path, address, port
        ):
            messagebox.showinfo(
                "成功", "已启动 {}（代理 {}:{}）。".format(
                    name, address, port
                )
            )
        else:
            messagebox.showerror("错误", self.manager.last_error)

    def _create_wrapper(self, name, path):
        address = self.addr_entry.get().strip()
        port = self.port_entry.get().strip()
        if not address or not port:
            messagebox.showerror("错误", "请先填写代理地址和端口。")
            return
        wrapper = self.manager.create_browser_wrapper(
            path, address, port
        )
        if wrapper:
            messagebox.showinfo(
                "成功",
                "已创建包装脚本：{}\n"
                "可通过命令行运行该脚本始终带代理启动浏览器。\n"
                "建议将 ~/.local/bin 加入 PATH。".format(wrapper)
            )
        else:
            messagebox.showerror("错误", self.manager.last_error)


# ============================================================
# 入口
# ============================================================
def main():
    root = tk.Tk()
    app = ProxySettingApp(root)
    # [修复] 在 GUI 初始化后启动自动刷新
    root.after(5000, app._auto_refresh)
    root.mainloop()


if __name__ == "__main__":
    main()
