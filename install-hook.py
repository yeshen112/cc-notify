"""
install-hook.py — 自动注册/卸载 CC 通知 Hook

用法:
    python install-hook.py            # 安装 Hook
    python install-hook.py --uninstall # 卸载 Hook
    python install-hook.py --status    # 查看 Hook 状态
"""
import json
import os
import sys
import argparse
from pathlib import Path

# 要注册的 Hook 条目模板
def _make_entry(hook_command):
    return {
        "matcher": "*",
        "hooks": [
            {
                "type": "command",
                "command": hook_command
            }
        ]
    }

HOOK_ID = "cc-notify"  # 用于标记我们的条目


def get_settings_path():
    """获取 CC 用户级配置文件路径"""
    home = Path(os.path.expanduser("~"))
    return home / ".claude" / "settings.json"


def get_hook_command():
    """获取当前平台的 Hook 命令"""
    if sys.platform == "win32":
        hooks_dir = Path(os.path.expanduser("~")) / ".claude" / "hooks"
        script = hooks_dir / "cc-notify-hook.ps1"
        # 用正斜杠保持与 settings.json 中其他条目格式一致
        return f"powershell.exe -NoProfile -ExecutionPolicy Bypass -File '{script.as_posix()}'"
    else:
        hooks_dir = Path(os.path.expanduser("~")) / ".claude" / "hooks"
        script = hooks_dir / "cc-notify-hook.sh"
        return f"bash '{script}'"


def install():
    """安装 Hook"""
    settings_path = get_settings_path()
    hook_command = get_hook_command()

    # 构建 Hook 条目
    entry = _make_entry(hook_command)

    # 读取现有配置
    if settings_path.exists():
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
        except json.JSONDecodeError:
            print(f"[错误] {settings_path} JSON 格式错误，请先修复")
            return False
    else:
        settings = {}

    # 需要注册的事件列表
    HOOK_EVENTS = ["PermissionRequest", "Stop"]

    # 确保 hooks 对象存在
    if "hooks" not in settings:
        settings["hooks"] = {}

    # 检查是否已全部安装
    all_installed = True
    for evt in HOOK_EVENTS:
        existing = settings["hooks"].get(evt, [])
        found = False
        for e in existing:
            for h in e.get("hooks", []):
                if h.get("command") == hook_command:
                    found = True
                    break
            if found:
                break
        if not found:
            all_installed = False
            # 追加新条目
            settings["hooks"][evt] = existing + [entry]
            print(f"[+] 注册事件: {evt}")

    if all_installed:
        print("[✓] 所有 Hook 已注册，无需重复安装")
        return True

    # 写入
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)

    print(f"[✓] Hook 已注册到 {settings_path}")
    print(f"    事件: {', '.join(HOOK_EVENTS)}")
    print(f"    命令: {hook_command}")
    print()
    print("  现在启动 cc-notify-tray.py 即可开始接收通知")
    return True


def uninstall():
    """卸载 Hook"""
    settings_path = get_settings_path()
    hook_command = get_hook_command()

    if not settings_path.exists():
        print("[i] 未找到 settings.json，无需卸载")
        return True

    with open(settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)

    hooks = settings.get("hooks", {})
    total_removed = 0
    HOOK_EVENTS = ["PermissionRequest", "Stop"]

    for evt in HOOK_EVENTS:
        evt_hooks = hooks.get(evt, [])
        new_evt_hooks = []
        evt_removed = 0
        for e in evt_hooks:
            new_hooks = []
            for h in e.get("hooks", []):
                if h.get("command") == hook_command:
                    evt_removed += 1
                else:
                    new_hooks.append(h)
            if new_hooks:
                e_new = dict(e)
                e_new["hooks"] = new_hooks
                new_evt_hooks.append(e_new)
        if new_evt_hooks:
            hooks[evt] = new_evt_hooks
        elif evt in hooks:
            del hooks[evt]
        total_removed += evt_removed

    if total_removed == 0:
        print("[i] 未找到 cc-notify Hook，无需卸载")
        return True

    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)

    print(f"[✓] 已移除 {total_removed} 条 cc-notify Hook")
    return True


def status():
    """查看状态"""
    settings_path = get_settings_path()
    hook_command = get_hook_command()

    if not settings_path.exists():
        print("[i] 未找到 settings.json")
        return

    with open(settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)

    hooks = settings.get("hooks", {})

    print(f"配置文件: {settings_path}")
    print(f"已配置事件: {', '.join(hooks.keys()) if hooks else '(无)'}")
    print()

    HOOK_EVENTS = ["PermissionRequest", "Stop"]
    any_installed = False
    for evt in HOOK_EVENTS:
        found = False
        for e in hooks.get(evt, []):
            for h in e.get("hooks", []):
                if h.get("command") == hook_command:
                    found = True
                    break
            if found:
                break
        if found:
            any_installed = True
            print(f"  [✓] {evt}")
        else:
            print(f"  [✗] {evt}")

    if any_installed:
        print(f"\n[✓] cc-notify Hook 已安装")
        print(f"    命令: {hook_command}")
    else:
        print("\n[✗] cc-notify Hook 未安装")
        print("    运行 install-hook.py 来安装")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CC 通知 Hook 安装/卸载")
    parser.add_argument("--uninstall", action="store_true", help="卸载 Hook")
    parser.add_argument("--status", action="store_true", help="查看状态")
    args = parser.parse_args()

    if args.uninstall:
        uninstall()
    elif args.status:
        status()
    else:
        install()
