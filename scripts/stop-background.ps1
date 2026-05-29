#Requires -Version 5.1
<#
.SYNOPSIS
  Stop background cursor-telegram-bridge process started by start-background.ps1.
#>
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_bridge.ps1"

$bridgePid = Get-BridgeRunningPid
if (-not $bridgePid) {
    Write-Host "Bridge is not running (no valid PID in $BridgePidFile)."
    exit 0
}

Write-Host "Stopping bridge (PID $bridgePid)..."
Stop-Process -Id $bridgePid -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500
Remove-Item $BridgePidFile -Force -ErrorAction SilentlyContinue

if (Test-BridgeProcessAlive $bridgePid) {
    Write-Host "Warning: process $bridgePid may still be running."
    exit 1
}

Write-Host "Stopped."
