"""
CC Notify — 一键安装脚本
用法: python setup.py
"""
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
HOOKS_DIR = Path.home() / ".claude" / "hooks"
SETTINGS_FILE = Path.home() / ".claude" / "settings.json"
CONFIG_FILE = Path.home() / ".claude" / "cc-notify-config.json"
BIN_DIR = Path.home() / ".local" / "bin"
PORT = 19284

# ============================================================
def header(text):
    print(f"\n{'='*50}")
    print(f"  {text}")
    print(f"{'='*50}")

def ok(msg):
    print(f"  [OK] {msg}")

def fail(msg):
    print(f"  [FAIL] {msg}")

def ask(msg):
    print(f"\n  {msg}")
    return input("  > ").strip()

# ============================================================
def check_python():
    header("Step 1/5: Check Python")
    print(f"  Python {sys.version}")
    ok(f"Python {sys.version_info.major}.{sys.version_info.minor}")

def install_deps():
    header("Step 2/5: Install dependencies")
    for pkg in ["pystray", "Pillow"]:
        try:
            __import__(pkg)
            ok(f"{pkg} already installed")
        except ImportError:
            print(f"  Installing {pkg}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])
            ok(f"{pkg} installed")

def deploy_hook():
    header("Step 3/5: Deploy hook script")
    HOOKS_DIR.mkdir(parents=True, exist_ok=True)

    if sys.platform == "win32":
        src = SCRIPT_DIR / "hooks" / "cc-notify-hook.ps1"
        hook_cmd = f"powershell.exe -NoProfile -ExecutionPolicy Bypass -File '{(HOOKS_DIR / 'cc-notify-hook.ps1').as_posix()}'"
    else:
        src = SCRIPT_DIR / "hooks" / "cc-notify-hook.sh"
        hook_cmd = f"bash '{HOOKS_DIR / 'cc-notify-hook.sh'}'"

    shutil.copy(src, HOOKS_DIR)
    ok(f"Copied to {HOOKS_DIR}")

    # Register hook in settings.json
    if SETTINGS_FILE.exists():
        settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    else:
        settings = {}

    settings.setdefault("hooks", {})

    # 需要注册的事件列表
    HOOK_EVENTS = ["PermissionRequest", "Stop"]
    entry = {
        "matcher": "*",
        "hooks": [{"type": "command", "command": hook_cmd}]
    }

    # 检查每个事件是否已注册，仅注册缺失的
    all_installed = True
    for evt in HOOK_EVENTS:
        existing = settings["hooks"].get(evt, [])
        found = False
        for e in existing:
            for h in e.get("hooks", []):
                if h.get("command") == hook_cmd:
                    found = True
                    break
            if found:
                break
        if not found:
            all_installed = False
            settings["hooks"][evt] = existing + [entry]
            ok(f"Registered hook for: {evt}")

    if all_installed:
        ok("All hooks already registered")

    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
    ok(f"Hook config saved to {SETTINGS_FILE}")

def configure():
    header("Step 4/5: Configure notification")

    # Load existing config
    if CONFIG_FILE.exists():
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        existing_key = cfg.get("wecom_key", "")
        if existing_key:
            print(f"  Existing key found: {existing_key[:20]}...")
            if ask("Keep this key? (Y/n)").lower() != "n":
                ok("Keeping existing config")
                cfg["first_run"] = False
                # 确保有 _说明 字段
                cfg.setdefault("_说明", {
                    "wecom_key": "企业微信机器人 Webhook Key，从群聊「消息推送」中添加机器人获取",
                    "notify_permission": "CC 弹出权限确认窗口时发送通知 (true=通知, false=不通知)",
                    "notify_session_start": "CC 会话启动时发送通知 (默认 false，按需开启)",
                    "notify_stop": "CC 完成任务停止时发送通知 (true=通知, false=不通知)",
                    "first_run": "内部标记，首次运行后自动设为 false",
                })
                CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
                return

    print()
    print("  How to get a Webhook Key:")
    print("    1. Download '企业微信' on your phone")
    print("    2. Register (company name can be anything)")
    print("    3. Create a group chat")
    print("    4. Group settings -> Message Push -> Add Bot")
    print("    5. Copy the 'key=xxx' part from the webhook URL")
    print()

    # 配置项说明（写入 JSON 方便用户编辑时理解）
    _说明 = {
        "wecom_key": "企业微信机器人 Webhook Key，从群聊「消息推送」中添加机器人获取",
        "notify_permission": "CC 弹出权限确认窗口时发送通知 (true=通知, false=不通知)",
        "notify_session_start": "CC 会话启动时发送通知 (默认 false，按需开启)",
        "notify_stop": "CC 完成任务停止时发送通知 (true=通知, false=不通知)",
        "first_run": "内部标记，首次运行后自动设为 false",
    }

    key = ask("Paste your WeCom Webhook Key").strip()
    if not key:
        print("\n  Skipped. You can configure later.")
        print(f"  Edit: {CONFIG_FILE}")
        cfg = {"_说明": _说明, "wecom_key": "", "notify_permission": True,
               "notify_session_start": False, "notify_stop": True,
               "first_run": True}
    else:
        notify_stop = ask("Notify when CC finishes a task? (Y/n)").lower() != "n"
        cfg = {"_说明": _说明, "wecom_key": key, "notify_permission": True,
               "notify_session_start": False, "notify_stop": notify_stop,
               "first_run": False}

    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    ok("Config saved")

    # Test notification
    if cfg["wecom_key"]:
        print("  Testing notification...")
        ok_test, msg = send_test(cfg["wecom_key"])
        if ok_test:
            ok("Test sent — check your phone!")
        else:
            fail(f"Test failed: {msg}")
            print("  You can re-run: python setup.py")

def send_test(key):
    body = json.dumps({
        "msgtype": "text",
        "text": {"content": "CC Notify ready! Permission alerts will appear here."}
    }, ensure_ascii=False).encode("utf-8")
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}"
    req = urllib.request.Request(url, data=body,
        headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
            return data.get("errcode") == 0, data.get("errmsg", "unknown")
    except Exception as e:
        return False, str(e)

def setup_cc_command():
    header("Step 5/5: Setup 'cc' command")
    BIN_DIR.mkdir(parents=True, exist_ok=True)

    # Generate cc.bat with hardcoded project path (%~dp0 won't work after copy)
    cc_bat_content = f'''@echo off
:: Switch to UTF-8 to handle Chinese paths correctly
chcp 65001 >nul 2>&1
setlocal
set "PROJECT_DIR={SCRIPT_DIR}"
set "TRAY_SCRIPT={SCRIPT_DIR / 'cc-notify-tray.py'}"
set "TRAY_PORT=19284"

:: Check if tray is already running
python -c "import socket; s=socket.socket(); s.settimeout(0.5); s.connect(('127.0.0.1',%TRAY_PORT%)); s.close()" >nul 2>&1
if %errorlevel% neq 0 (
    echo [CC Notify] Starting notification tray...
    start "" pythonw "%TRAY_SCRIPT%"
    ping -n 3 127.0.0.1 >nul
)

:: Start Claude Code
claude %*

:: CC exited, signal tray to quit
python -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1',%TRAY_PORT%)); s.sendall(b'EXIT'); s.close()" >nul 2>&1
'''
    (BIN_DIR / "cc.bat").write_text(cc_bat_content, encoding="utf-8")
    ok(f"cc.bat installed to {BIN_DIR}")

    # Add to PATH — use Windows registry API (reliable across all users)
    if sys.platform == "win32":
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ | winreg.KEY_WRITE)
        try:
            current_path, _ = winreg.QueryValueEx(key, "PATH")
        except FileNotFoundError:
            current_path = ""

        if str(BIN_DIR) not in current_path:
            new_path = current_path.rstrip(";") + ";" + str(BIN_DIR)
            winreg.SetValueEx(key, "PATH", 0, winreg.REG_EXPAND_SZ, new_path)
            # Notify the system that environment changed
            import ctypes
            ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, None)
            ok("Added to PATH (restart terminal to use 'cc')")
        else:
            ok("Already in PATH")
        winreg.CloseKey(key)
    else:
        # macOS/Linux: add to shell profile
        shell_profile = Path.home() / ".bashrc"
        line = f'\nexport PATH="$PATH:{BIN_DIR}"  # cc-notify\n'
        if line not in shell_profile.read_text() if shell_profile.exists() else True:
            with open(shell_profile, "a") as f:
                f.write(line)
            ok(f"Added to {shell_profile}")

def launch_tray():
    print(f"\n{'='*50}")
    print("  Setup complete! Launching tray...")
    print(f"{'='*50}")
    print()
    print("  The green dot will appear in your system tray.")
    print("  Right-click it for config, test, or quit.")
    print()
    print("  To use:  cc          (instead of 'claude')")
    print("           cc 'fix bug' (with a question)")
    print()

    # Launch without console window
    if sys.platform == "win32":
        pythonw = Path(sys.executable).parent / "pythonw.exe"
        subprocess.Popen([str(pythonw), str(SCRIPT_DIR / "cc-notify-tray.py")],
                         creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        subprocess.Popen([sys.executable, str(SCRIPT_DIR / "cc-notify-tray.py")],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("  Tray launched. You can close this window.")

def main():
    print()
    print("  ╔══════════════════════════════════╗")
    print("  ║   CC Notify — Setup             ║")
    print("  ║   Claude Code alerts -> Phone   ║")
    print("  ╚══════════════════════════════════╝")

    check_python()
    install_deps()
    deploy_hook()
    configure()
    setup_cc_command()
    launch_tray()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Cancelled.")
    except Exception as e:
        print(f"\n  Error: {e}")
        print("  Please report this issue.")
