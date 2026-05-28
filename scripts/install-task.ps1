#Requires -Version 5.1
<#
.SYNOPSIS
  Register cursor-telegram-bridge bot in Task Scheduler (At logon + At startup).
#>
param(
    [int]$StartupDelaySec = 30
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$BotScript = Join-Path $RepoRoot "telegram-bot\agent_bot.py"
$LogDir = Join-Path $RepoRoot "telegram-bot\logs"
$LogFile = Join-Path $LogDir "bot-stderr.log"
$TaskName = "cursor-telegram-bridge"

if (-not (Test-Path $BotScript)) {
    throw "Missing $BotScript"
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$pyCmd = Get-Command python -ErrorAction SilentlyContinue
$python = if ($pyCmd) { $pyCmd.Source } else { $null }
if (-not $python) {
    $py3Cmd = Get-Command python3 -ErrorAction SilentlyContinue
    $python = if ($py3Cmd) { $py3Cmd.Source } else { $null }
}
if (-not $python) {
    throw "python not found on PATH"
}

$action = New-ScheduledTaskAction -Execute $python -Argument "`"$BotScript`"" -WorkingDirectory $RepoRoot
$triggerLogon = New-ScheduledTaskTrigger -AtLogOn
$triggerBoot = New-ScheduledTaskTrigger -AtStartup
$triggerBoot.Delay = "PT${StartupDelaySec}S"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($triggerLogon, $triggerBoot) -Settings $settings -Force | Out-Null

Write-Host "Registered scheduled task: $TaskName"
Write-Host "Start now: Start-ScheduledTask -TaskName $TaskName"
Write-Host "Logs: redirect stderr manually if needed -> $LogFile"
