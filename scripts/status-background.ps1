#Requires -Version 5.1
<#
.SYNOPSIS
  Show whether cursor-telegram-bridge is running in the background.
#>
$ErrorActionPreference = "Continue"
. "$PSScriptRoot\_bridge.ps1"

$bridgePid = Get-BridgeRunningPid
if ($bridgePid) {
    Write-Host "RUNNING  PID=$bridgePid"
    Write-Host "Logs: $BridgeStderrLog"
} else {
    Write-Host "STOPPED"
}

$task = Get-ScheduledTask -TaskName $BridgeTaskName -ErrorAction SilentlyContinue
if ($task) {
    $info = Get-ScheduledTaskInfo -TaskName $BridgeTaskName -ErrorAction SilentlyContinue
    Write-Host "Scheduled task '$BridgeTaskName': State=$($task.State) LastRun=$($info.LastRunTime) Result=$($info.LastTaskResult)"
} else {
    Write-Host "Scheduled task '$BridgeTaskName': not registered (optional: .\scripts\install-task.ps1)"
}

if (Test-Path $BridgeStderrLog) {
    Write-Host "`n--- last 15 lines of bot-stderr.log ---"
    Get-Content $BridgeStderrLog -Tail 15 -ErrorAction SilentlyContinue
}
