#Requires -Version 5.1
<#
.SYNOPSIS
  Start cursor-telegram-bridge in the background (detached, logs to telegram-bot/logs/).
.PARAMETER Force
  Stop existing instance (if any) and start a new one.
#>
param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_bridge.ps1"

Assert-BridgeBotScript
Ensure-BridgeLogDir

# Stop stray agent_bot.py instances (409 Conflict on getUpdates if two bots run).
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -like '*agent_bot.py*' } |
    ForEach-Object {
        $pidFile = Get-Content $BridgePidFile -ErrorAction SilentlyContinue
        if ($_.ProcessId -ne [int]$pidFile) {
            Write-Host "Stopping extra bot PID $($_.ProcessId)"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }

$existing = Get-BridgeRunningPid
if ($existing) {
    if (-not $Force) {
        Write-Host "Bridge already running (PID $existing)."
        Write-Host "Logs: $BridgeStderrLog"
        Write-Host "Stop:  .\scripts\stop-background.ps1"
        exit 0
    }
    Write-Host "Stopping existing bridge (PID $existing)..."
    Stop-Process -Id $existing -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    Remove-Item $BridgePidFile -Force -ErrorAction SilentlyContinue
}

$python = Get-BridgePython
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
foreach ($logPath in @($BridgeStdoutLog, $BridgeStderrLog)) {
    try {
        Add-Content -Path $logPath -Value "`n=== started $stamp ===" -ErrorAction Stop
    } catch {
        Write-Host "Note: could not append to $logPath (file may be locked by a running instance)."
    }
}

$sys32 = Join-Path $env:SystemRoot "System32"
$psDir = Join-Path $sys32 "WindowsPowerShell\v1.0"
$env:PATH = "$psDir;$sys32;$env:PATH"
$agentDir = Join-Path $env:LOCALAPPDATA "cursor-agent"
if (Test-Path $agentDir) {
    $env:PATH = "$agentDir;$env:PATH"
}
if (-not $env:ComSpec) {
    $env:ComSpec = Join-Path $sys32 "cmd.exe"
}

$proc = Start-Process -FilePath $python `
    -ArgumentList "`"$BridgeBotScript`"" `
    -WorkingDirectory $BridgeRepoRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $BridgeStdoutLog `
    -RedirectStandardError $BridgeStderrLog `
    -PassThru

Set-Content -Path $BridgePidFile -Value $proc.Id -Encoding ascii
Write-Host "cursor-telegram-bridge started in background (PID $($proc.Id))."
Write-Host "Stdout: $BridgeStdoutLog"
Write-Host "Stderr: $BridgeStderrLog"
Write-Host "Status: .\scripts\status-background.ps1"
Write-Host "Stop:   .\scripts\stop-background.ps1"
