#Requires -Version 5.1
<#
.SYNOPSIS
  Smoke test: config, proxy getMe, cursor CLI, optional ask ping.
#>
param(
    [switch]$SkipAgent
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$TelegramDir = Join-Path $RepoRoot "telegram-bot"
Set-Location $TelegramDir

function Read-ConfigValue([string]$Key) {
    $configPath = Join-Path $TelegramDir "config"
    if (-not (Test-Path $configPath)) {
        throw "Missing telegram-bot/config — copy from config.example"
    }
    foreach ($line in Get-Content $configPath) {
        $t = $line.Trim()
        if ($t -match "^\s*$Key\s*=\s*(.+)\s*$") {
            return $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
    return $null
}

Write-Host "== cursor-telegram-bridge smoke test =="

$token = Read-ConfigValue "TELEGRAM_BOT_TOKEN"
if (-not $token) { throw "TELEGRAM_BOT_TOKEN empty" }

$proxyUrls = Read-ConfigValue "PROXY_SOCKS5_URLS"
$workspace = Read-ConfigValue "CURSOR_WORKSPACE"
if (-not $workspace) { $workspace = $RepoRoot }

Write-Host "Workspace: $workspace"

python -c @"
import json, urllib.request
from config_loader import load_config, get_proxy_urls
import proxy
cfg = load_config()
proxy.configure(get_proxy_urls(cfg))
token = cfg['TELEGRAM_BOT_TOKEN']
req = urllib.request.Request(f'https://api.telegram.org/bot{token}/getMe')
with proxy.open_url(req, timeout=30) as r:
    data = json.loads(r.read().decode())
print('getMe ok:', data.get('result', {}).get('username'))
"@

if (-not $SkipAgent) {
    $cli = Read-ConfigValue "CURSOR_CLI"
    if ($cli) {
        $parts = $cli -split '\s+'
    } elseif (Get-Command agent -ErrorAction SilentlyContinue) {
        $parts = @("agent")
    } else {
        $parts = @("cursor", "agent")
    }
    $args = $parts + @("--print", "--trust", "--force", "--mode", "ask", "--workspace", $workspace, "Reply with exactly: smoke ok")
    Write-Host "Agent ping:" ($args -join ' ')
    & $parts[0] $args[1..($args.Length-1)]
}

Write-Host "Smoke test finished."
