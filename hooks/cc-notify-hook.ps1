# ============================================================
# cc-notify-hook.ps1 — CC Event Forwarder (Windows)
# Hook 触发后转发 JSON 到本地 TCP 19284（GUI 服务）
# 完全独立于 cc-claw
# ============================================================
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.Encoding]::UTF8

$TCP_HOST = '127.0.0.1'
$TCP_PORT = 19284
$LOG_FILE = "$env:USERPROFILE\.claude\cc-notify-hook.log"

function Write-Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts $msg" | Out-File -Append -FilePath $LOG_FILE -Encoding UTF8
}

try {
    $raw = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }

    # 提取事件名用于日志
    $eventName = "?"
    if ($raw -match '"hook_event_name"\s*:\s*"([^"]+)"') { $eventName = $matches[1] }
    $toolName = "?"
    if ($raw -match '"tool_name"\s*:\s*"([^"]*)"') { $toolName = $matches[1] }
    Write-Log "RECV $eventName tool=$toolName len=$($raw.Length)"

    $isPermission = $eventName -eq "PermissionRequest"

    $client = [System.Net.Sockets.TcpClient]::new($TCP_HOST, $TCP_PORT)
    $stream = $client.GetStream()
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($raw)
    $stream.Write($bytes, 0, $bytes.Length)
    $stream.Flush()
    $client.Client.Shutdown([System.Net.Sockets.SocketShutdown]::Send)

    if ($isPermission) {
        $reader = [System.IO.StreamReader]::new($stream, [System.Text.Encoding]::UTF8)
        $response = $reader.ReadToEnd()
        if ($response) {
            [Console]::Out.Write($response)
            [Console]::Out.Flush()
        }
        $reader.Close()
    } else {
        # 给 tray 端一点时间处理，避免 Close() 发 RST 导致 tray 丢数据
        Start-Sleep -Milliseconds 150
    }
    $client.Close()
    Write-Log "SENT $eventName → OK"
} catch {
    Write-Log "FAIL $($_.Exception.Message)"
}
