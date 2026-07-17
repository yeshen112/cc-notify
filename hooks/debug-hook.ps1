# Debug hook — 记录所有 hook 事件到日志文件
$logFile = "$env:USERPROFILE\.claude\hook-debug.log"
try {
    $raw = [Console]::In.ReadToEnd()
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $summary = if ($raw.Length -gt 300) { $raw.Substring(0, 300) + "..." } else { $raw }
    "[DEBUG $timestamp] RAW=$summary" | Out-File -Append -FilePath $logFile -Encoding UTF8

    # 提取事件名
    if ($raw -match '"hook_event_name"\s*:\s*"([^"]+)"') {
        $eventName = $matches[1]
        "  EVENT: $eventName" | Out-File -Append -FilePath $logFile -Encoding UTF8
    } else {
        "  EVENT: (unknown - no hook_event_name in JSON)" | Out-File -Append -FilePath $logFile -Encoding UTF8
        # 打印所有 key 帮助诊断
        if ($raw -match '"hook_event_name"') {
            "  (found hook_event_name but regex didn't match)" | Out-File -Append -FilePath $logFile -Encoding UTF8
        }
    }
} catch {
    "[DEBUG ERROR] $_" | Out-File -Append -FilePath $logFile -Encoding UTF8
}
