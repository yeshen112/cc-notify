#!/usr/bin/env bash
# ============================================================
# cc-notify-hook.sh — CC Event Forwarder (macOS/Linux)
# Hook 触发后转发 JSON 到本地 TCP 19284（GUI 服务）
# ============================================================
set -e

HOST="127.0.0.1"
PORT=19284

raw=$(cat)
[[ -z "$raw" ]] && exit 0

if echo "$raw" | nc -w 2 "$HOST" "$PORT" 2>/dev/null; then
    : # 已发送，无需响应
fi

exit 0
