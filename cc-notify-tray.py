"""
cc-notify — Claude Code 权限弹窗 → 手机通知
系统托盘常驻程序，监听 CC Hook 事件，通过企业微信推送到手机

用法:
    python cc-notify-tray.py       # 启动托盘
    python cc-notify-tray.py --cli # 控制台模式（调试用）
"""
import json
import os
import socket
import sys
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path


# ═══════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════

APP_NAME = "CC 通知"
APP_VERSION = "1.0.0"
TCP_HOST = "127.0.0.1"
TCP_PORT = 19284
CONFIG_FILE = Path(os.path.expanduser("~/.claude/cc-notify-config.json"))

DEFAULT_CONFIG = {
    "_说明": {
        "wecom_key": "企业微信机器人 Webhook Key，从群聊「消息推送」中添加机器人获取",
        "notify_permission": "CC 弹出权限确认窗口时发送通知 (true=通知, false=不通知)",
        "notify_session_start": "CC 会话启动时发送通知 (默认 false，按需开启)",
        "notify_stop": "CC 完成任务停止时发送通知 (true=通知, false=不通知)",
        "first_run": "内部标记，首次运行后自动设为 false",
    },
    "wecom_key": "",
    "first_run": True,
    "notify_permission": True,
    "notify_session_start": False,
    "notify_stop": True,
}

# 首次运行时自动创建默认配置
if not CONFIG_FILE.exists():
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False), encoding="utf-8")

LOG_LINES = []  # 最近 200 条日志
LOG_LOCK = threading.Lock()


# ═══════════════════════════════════════════════════════════
# 配置读写
# ═══════════════════════════════════════════════════════════

def load_config():
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            for k, v in DEFAULT_CONFIG.items():
                cfg.setdefault(k, v)
            return cfg
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


# ═══════════════════════════════════════════════════════════
# 企业微信通知
# ═══════════════════════════════════════════════════════════

def send_wecom(key, title, detail, timeout=10):
    """发送企业微信 Markdown 通知。返回 (ok, message)"""
    if not key or not key.strip():
        return False, "未配置 Webhook Key"

    markdown = f"## {title}\n>{detail}".replace("\n", "\n>")
    payload = json.dumps({
        "msgtype": "markdown",
        "markdown": {"content": markdown}
    }, ensure_ascii=False).encode("utf-8")

    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key.strip()}"
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json; charset=utf-8"
    })

    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
            if data.get("errcode") == 0:
                return True, "发送成功"
            return False, data.get("errmsg", f"errcode={data.get('errcode')}")
    except urllib.error.URLError as e:
        return False, f"网络错误: {e.reason}"
    except Exception as e:
        return False, str(e)


# ═══════════════════════════════════════════════════════════
# TCP 事件接收服务
# ═══════════════════════════════════════════════════════════

class EventServer(threading.Thread):

    def __init__(self):
        super().__init__(daemon=True)
        self._stop = threading.Event()
        self._icon = None  # 托盘图标引用，收到 EXIT 时用于关闭托盘
        self._active_sessions = 0  # 活跃 CC 会话计数
        self._session_lock = threading.Lock()

    @staticmethod
    def get_config():
        """每次调用都从磁盘重新读取配置"""
        return load_config()

    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((TCP_HOST, TCP_PORT))
            sock.listen(5)
            sock.settimeout(1.0)
        except OSError as e:
            log(f"[错误] 端口 {TCP_PORT} 被占用: {e}")
            return

        log(f"TCP 服务已启动 {TCP_HOST}:{TCP_PORT}")

        while not self._stop.is_set():
            try:
                conn, _ = sock.accept()
                threading.Thread(target=self._handle, args=(conn,), daemon=True).start()
            except socket.timeout:
                continue
            except Exception as e:
                if not self._stop.is_set():
                    log(f"[错误] {e}")

        sock.close()
        log("TCP 服务已停止")

    def _handle(self, conn):
        buf = b""
        try:
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buf += chunk
                if len(chunk) < 4096:
                    break
        except Exception as e:
            log(f"[警告] 接收数据时出错: {e}")

        if not buf:
            try:
                conn.close()
            except Exception:
                pass
            return

        text = buf.decode("utf-8").strip()

        # ── HELO: CC 实例启动时注册会话 ──
        if text == "HELO":
            with self._session_lock:
                self._active_sessions += 1
            log(f"CC 会话已注册 (活跃: {self._active_sessions})")
            try:
                conn.sendall(b"OK")
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
            return

        # ── EXIT: CC 实例退出时注销会话 ──
        if text == "EXIT":
            with self._session_lock:
                self._active_sessions = max(0, self._active_sessions - 1)
                remaining = self._active_sessions
            log(f"CC 会话已注销 (剩余活跃: {remaining})")
            if remaining <= 0:
                log("所有 CC 会话已结束，关闭服务...")
                self.stop()
                if self._icon:
                    self._icon.stop()
            try:
                conn.close()
            except Exception:
                pass
            return

        try:
            event = json.loads(text)
        except json.JSONDecodeError:
            return

        name = event.get("hook_event_name", "Unknown")
        tool = event.get("tool_name", "?")
        cfg = self.get_config()

        def _tool_detail():
            lines = [f"工具: **{tool}**"]
            if tool == "Bash":
                cmd = (event.get("tool_input", {}) or {}).get("command", "") or ""
                if len(cmd) > 120:
                    cmd = cmd[:120] + "..."
                lines.append(f"命令: `{cmd}`")
            elif tool in ("Write", "Edit", "NotebookEdit"):
                fp = (event.get("tool_input", {}) or {}).get("file_path", "") or ""
                lines.append(f"文件: {fp}")
            elif tool == "WebFetch":
                url = (event.get("tool_input", {}) or {}).get("url", "") or ""
                if len(url) > 80:
                    url = url[:80] + "..."
                lines.append(f"URL: {url}")
            elif tool == "WebSearch":
                q = (event.get("tool_input", {}) or {}).get("query", "") or ""
                if len(q) > 80:
                    q = q[:80] + "..."
                lines.append(f"搜索: {q}")
            lines.append(f"目录: {event.get('cwd', '?')}")
            lines.append(f"时间: {time.strftime('%H:%M:%S')}")
            return "\n".join(lines)

        # ════════════════════════════════════════════════
        # 🔔 PermissionRequest — 弹窗等待用户确认
        # ════════════════════════════════════════════════
        if name == "PermissionRequest" and cfg.get("notify_permission", True):
            mode = event.get("permission_mode", "?")
            lines = _tool_detail().split("\n")
            lines.insert(1, f"模式: {mode}")
            ok, msg = send_wecom(cfg.get("wecom_key", ""),
                                 f"🔔 请求确认 — {tool}", "\n".join(lines))
            log(f"权限请求 {tool} → {'✓' if ok else '✗'} {msg}")

        # ── CC 停止（仅最终停止，不含 SubagentStop）──
        elif name == "Stop" and cfg.get("notify_stop", True):
            detail = f"原因: {event.get('reason', '?')}\n时间: {time.strftime('%H:%M:%S')}"
            ok, _ = send_wecom(cfg.get("wecom_key", ""),
                               "⏹ CC 已停止，等待输入", detail)
            log(f"停止通知 → {'✓' if ok else '✗'}")

        # ── 返回审批决定 ──
        if name == "PermissionRequest":
            resp = json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PermissionRequest",
                    "permissionDecision": "allow",
                    "permissionDecisionReason": "cc-notify: 已推送通知"
                }
            }, ensure_ascii=False)
            try:
                conn.sendall(resp.encode("utf-8"))
            except Exception:
                pass

        try:
            conn.close()
        except Exception:
            pass

    def stop(self):
        self._stop.set()


# ═══════════════════════════════════════════════════════════
# 日志
# ═══════════════════════════════════════════════════════════

def log(msg):
    global LOG_LINES
    entry = f"[{time.strftime('%H:%M:%S')}] {msg}"
    with LOG_LOCK:
        LOG_LINES.append(entry)
        if len(LOG_LINES) > 200:
            LOG_LINES = LOG_LINES[-200:]
    print(entry, flush=True)


# ═══════════════════════════════════════════════════════════
# 生成托盘图标
# ═══════════════════════════════════════════════════════════

def make_icon(size=64, color=(76, 175, 80)):
    """生成圆形图标（需要 Pillow）"""
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        m = 4
        draw.ellipse([m, m, size - m, size - m], fill=color, outline=(50, 130, 54), width=2)
        return img
    except ImportError:
        return None


# ═══════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════

def run_tray():
    """系统托盘模式"""
    import pystray

    cfg = load_config()

    tray_img = make_icon()
    if tray_img is None:
        log("缺少 Pillow，无法创建托盘图标")
        log("运行: pip install Pillow")
        run_cli()
        return

    # 启动 TCP 服务
    server = EventServer()
    server.start()

    def open_config_file(icon=None, item=None):
        """用默认编辑器打开配置文件"""
        os.startfile(str(CONFIG_FILE))

    def test_notify(icon=None, item=None):
        cfg = load_config()
        ok, msg = send_wecom(cfg.get("wecom_key", ""), "🧪 测试消息",
                             f"CC 通知服务运行中\n时间: {time.strftime('%H:%M:%S')}")
        log(f"手动测试 → {'✓' if ok else '✗'} {msg}")

    def quit_app(icon, item):
        server.stop()
        icon.stop()
        log("已退出")

    menu = pystray.Menu(
        pystray.MenuItem("🧪 测试通知", test_notify, default=True),
        pystray.MenuItem("📝 编辑配置", open_config_file),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("❌ 退出", quit_app),
    )

    icon = pystray.Icon("cc-notify", tray_img, APP_NAME, menu)
    server._icon = icon  # 让 server 能关闭托盘（收到 EXIT 时）

    log(f"{APP_NAME} v{APP_VERSION} 已启动")
    log(f"配置: {CONFIG_FILE}")
    log(f"监听 {TCP_HOST}:{TCP_PORT}")
    if not cfg.get("wecom_key"):
        log("⚠ 未配置 Webhook Key，请右键 → 编辑配置")
    icon.run()
    server.stop()


def run_cli():
    """控制台模式（调试/无 GUI 时降级）"""
    server = EventServer()
    server.start()
    cfg = load_config()

    help_text = f"""
    ┌─────────────────────────────────┐
    │  CC 通知服务 v{APP_VERSION}        │
    │  运行中                         │
    ├─────────────────────────────────┤
    │  t  测试通知                     │
    │  e  打开配置文件                  │
    │  q  退出                         │
    └─────────────────────────────────┘
    """
    print(help_text)
    if not cfg.get("wecom_key"):
        print("  ⚠ 未配置 Webhook Key，请编辑配置文件:")
        print(f"    {CONFIG_FILE}\n")

    def input_loop():
        while True:
            try:
                cmd = input().strip().lower()
                if cmd == "t":
                    cfg = load_config()
                    ok, msg = send_wecom(cfg.get("wecom_key", ""), "🧪 测试消息",
                                         f"CC 通知服务运行中\n时间: {time.strftime('%H:%M:%S')}")
                    print(f"{'✓' if ok else '✗'} {msg}")
                elif cmd == "e":
                    cfg_file = str(CONFIG_FILE)
                    if sys.platform == "win32":
                        os.startfile(cfg_file)
                    else:
                        import subprocess
                        subprocess.call(["open", cfg_file])
                    print(f"已打开: {cfg_file}")
                elif cmd == "q":
                    print("退出...")
                    server.stop()
                    break
            except EOFError:
                break

    threading.Thread(target=input_loop, daemon=True).start()
    try:
        while server.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n退出...")
        server.stop()


if __name__ == "__main__":
    if "--cli" in sys.argv:
        run_cli()
    else:
        try:
            import pystray  # noqa: F401
            run_tray()
        except ImportError:
            print("pystray 未安装，降级到控制台模式")
            print("运行: pip install pystray Pillow\n")
            run_cli()
