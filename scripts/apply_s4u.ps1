$log = "C:\golddaytrador\data\s4u_apply.log"
try {
    $sid = "S-1-5-21-2893568753-2114575851-3395114977-1001"
    $p = New-ScheduledTaskPrincipal -UserId $sid -LogonType S4U -RunLevel Limited
    $s = (Get-ScheduledTask -TaskName Dispatch -TaskPath "\GoldDayTrader\").Settings
    $s.WakeToRun = $true
    Set-ScheduledTask -TaskName Dispatch -TaskPath "\GoldDayTrader\" -Principal $p -Settings $s | Out-Null
    $now = (Get-ScheduledTask -TaskName Dispatch -TaskPath "\GoldDayTrader\")
    "OK: LogonType=$($now.Principal.LogonType) WakeToRun=$($now.Settings.WakeToRun) at $(Get-Date -Format o)" | Out-File $log -Encoding utf8
} catch {
    "ERR: $_" | Out-File $log -Encoding utf8
}
