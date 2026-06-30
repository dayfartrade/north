# Install GoldDayTrader Windows Task Scheduler entries.
# Run in elevated PowerShell:
#   .\install_tasks.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "Installing GoldDayTrader scheduled tasks..."

# Remove any existing tasks at our paths so re-running is idempotent
Get-ScheduledTask -TaskPath '\GoldDayTrader\' -ErrorAction SilentlyContinue | Unregister-ScheduledTask -Confirm:$false

$dispatch_xml = Get-Content "$PSScriptRoot\TASK_dispatch_30min.xml" -Raw
$daily_xml    = Get-Content "$PSScriptRoot\TASK_daily_refresh.xml" -Raw

Register-ScheduledTask -TaskName "Dispatch"     -TaskPath "\GoldDayTrader\" -Xml $dispatch_xml -Force
Register-ScheduledTask -TaskName "DailyRefresh" -TaskPath "\GoldDayTrader\" -Xml $daily_xml    -Force

Write-Host ""
Write-Host "Installed:"
Get-ScheduledTask -TaskPath '\GoldDayTrader\' | Format-Table TaskName, State, @{n='NextRun';e={(Get-ScheduledTaskInfo $_).NextRunTime}}

Write-Host ""
Write-Host "To remove later: Get-ScheduledTask -TaskPath '\GoldDayTrader\' | Unregister-ScheduledTask -Confirm:$false"
