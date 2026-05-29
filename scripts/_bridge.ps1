#Requires -Version 5.1
# Shared helpers for cursor-telegram-bridge background scripts.

$script:BridgeRepoRoot = Split-Path -Parent $PSScriptRoot
$script:BridgeBotScript = Join-Path $BridgeRepoRoot "telegram-bot\agent_bot.py"
$script:BridgeLogDir = Join-Path $BridgeRepoRoot "telegram-bot\logs"
$script:BridgePidFile = Join-Path $BridgeRepoRoot "telegram-bot\.bot.pid"
$script:BridgeStdoutLog = Join-Path $BridgeLogDir "bot-stdout.log"
$script:BridgeStderrLog = Join-Path $BridgeLogDir "bot-stderr.log"
$script:BridgeTaskName = "cursor-telegram-bridge"

function Get-BridgePython {
    $venvPy = Join-Path $BridgeRepoRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPy) { return $venvPy }
    $pyCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pyCmd) { return $pyCmd.Source }
    $py3Cmd = Get-Command python3 -ErrorAction SilentlyContinue
    if ($py3Cmd) { return $py3Cmd.Source }
    throw "python not found (install Python 3.10+ or create .venv)"
}

function Test-BridgeProcessAlive([int]$ProcessId) {
    if ($ProcessId -le 0) { return $false }
    try {
        $p = Get-Process -Id $ProcessId -ErrorAction Stop
        return $null -ne $p -and -not $p.HasExited
    } catch {
        return $false
    }
}

function Get-BridgeRunningPid {
    if (-not (Test-Path $BridgePidFile)) { return $null }
    try {
        $bridgePid = [int](Get-Content $BridgePidFile -Raw).Trim()
    } catch {
        return $null
    }
    if (Test-BridgeProcessAlive $bridgePid) { return $bridgePid }
    Remove-Item $BridgePidFile -Force -ErrorAction SilentlyContinue
    return $null
}

function Ensure-BridgeLogDir {
    New-Item -ItemType Directory -Force -Path $BridgeLogDir | Out-Null
}

function Assert-BridgeBotScript {
    if (-not (Test-Path $BridgeBotScript)) {
        throw "Missing $BridgeBotScript"
    }
}
