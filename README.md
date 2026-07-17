# CC 通知 (cc-notify)

> Claude Code 权限弹窗 → 手机通知

当 Claude Code 弹出权限确认窗口时，自动通过**企业微信**推送通知到你的手机。带系统托盘 GUI，可视化配置，即装即用。

## 功能

- 🔔 CC 权限弹窗 → 手机实时通知
- ⚡ 工具调用预告（Bash / Write / Edit / WebFetch 等需要用户交互的工具）
- ⏹ CC 任务完成通知（可选）
- 🖥️ 系统托盘图标（绿色圆点 = 运行中）
- 📝 配置文件管理（JSON 文件，简洁明了）
- 🪶 和 cc-claw 等已有工具并存，互不干扰

## 工作原理

```
CC 触发 Hook 事件 (PermissionRequest / Stop)
    ↓
hooks/cc-notify-hook.ps1 (Win) / .sh (Mac/Linux)
    ↓  转发 JSON 到 TCP 127.0.0.1:19284
cc-notify-tray.py (系统托盘 + TCP 服务)
    ↓  调用企业微信 Webhook API
📱 手机收到通知
```

托盘程序在本地 `127.0.0.1:19284` 起一个 TCP 服务，Hook 脚本将 CC 事件 JSON 原样转发过来，托盘解析后通过企业微信机器人推送。

### 支持的事件

| 事件 | 触发时机 | 通知内容 |
|------|----------|----------|
| **PermissionRequest** | CC 弹窗等待确认时 | 权限请求详情（自动回复 allow） |
| **Stop** | CC 停止等待用户输入 | 停止原因 |

## 快速开始

### 1. 准备企业微信

1. 手机下载「企业微信」→ 注册（随便填企业名，免费）
2. 建一个群 → 右上角 `…` →「消息推送」→ 添加机器人
3. 复制 Webhook Key（`key=xxxx` 那串）

### 2. 一键安装

```bash
python setup.py
```

安装时选择运行模式：

| 模式 | 说明 | 适合 |
|------|------|------|
| **跟随 CC** | 用 `cc` 代替 `claude`，CC 启动时自动拉起托盘，CC 退出时托盘自动关闭 | 推荐 |
| 开机自启 | 托盘常驻系统栏，随时待命 | 重度 CC 用户 |
| 手动启动 | 每次用 CC 前手动启动 `pythonw cc-notify-tray.py` | 偶尔使用 |

### 3. 配置

安装时输入 Key 即自动保存到 `~/.claude/cc-notify-config.json`。后续修改有两种方式：

```bash
# 方式 1：右键托盘 → 📝 编辑配置 → 用记事本打开 JSON
# 方式 2：直接编辑文件
notepad ~/.claude/cc-notify-config.json    # Windows
open ~/.claude/cc-notify-config.json       # macOS
```

配置文件内容：
```json
{
  "_说明": {
    "wecom_key": "企业微信机器人 Webhook Key",
    "notify_permission": "权限确认窗口时通知",
    "notify_session_start": "CC 会话启动时通知",
    "notify_stop": "CC 任务完成时通知",
    "first_run": "内部标记"
  },
  "wecom_key": "你的Key",
  "notify_permission": true,
  "notify_session_start": false,
  "notify_stop": true,
  "first_run": false
}
```
| 字段 | 说明 | 默认值 |
|------|------|--------|
| `wecom_key` | 企业微信 Webhook Key（必填） | `""` |
| `notify_permission` | 权限请求通知 | `true` |
| `notify_session_start` | CC 会话启动通知 | `false` |
| `notify_stop` | CC 任务完成通知 | `true` |

## 日常使用

```bash
# 模式 1（跟随 CC）
cc                     # 托盘自动起 → CC 工作 → CC 退出 → 托盘自动关
cc "帮我修个 bug"       # 也可以直接带问题

# 模式 2/3 — 手动启停托盘
pythonw cc-notify-tray.py            # Windows（无控制台窗口）
python cc-notify-tray.py --cli       # 控制台模式（调试用）
```

右键系统托盘绿色圆点：
- **🧪 测试通知** — 发送一条测试消息到手机
- **📝 编辑配置** — 用记事本打开配置文件
- **❌ 退出** — 停止通知服务

## 项目结构

```
cc-notify/
├── cc-notify-tray.py          # 主程序（系统托盘 + TCP 服务 + 通知发送）
├── install-hook.py            # Hook 注册 / 卸载 / 状态查看
├── setup.py                   # 一键安装（跨平台）
├── hooks/
│   ├── cc-notify-hook.ps1     # Hook 转发脚本 (Windows)
│   ├── cc-notify-hook.sh      # Hook 转发脚本 (macOS/Linux)
│   └── debug-hook.ps1         # 调试用 Hook（记录所有事件到日志）
├── requirements.txt
└── README.md
```

## 卸载

```bash
python install-hook.py --uninstall   # 移除 Hook
# 删除项目目录即可
```

如果设置了开机自启，还需手动删除 `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\CC-Notify.vbs`。

## 故障排查

### 测试通知发送失败

1. 确认 Webhook Key 正确（不要有多余空格）
2. 确认企业微信群里机器人没有被移除
3. 企业微信免费版有频率限制（20条/分钟），超限会返回 `45009` 错误
4. 用控制台模式运行查看具体报错：`python cc-notify-tray.py --cli`

### Hook 未触发

```bash
python install-hook.py --status    # 查看 Hook 注册状态
```

如果 Hook 未注册，运行：
```bash
python install-hook.py             # 安装 Hook
```

### 调试 Hook 事件

将 `hooks/debug-hook.ps1` 注册到 CC settings.json 中，所有 hook 事件会记录到 `~/.claude/hook-debug.log`，方便排查哪些事件被触发、JSON 结构是否正确。

## License

MIT
