$ErrorActionPreference = "Stop"

$TaskName = "Systemo Agent"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$StartScript = Join-Path $PSScriptRoot "start_agent.ps1"

$PrincipalCheck = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $PrincipalCheck.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "Run PowerShell as Administrator before installing the scheduled task."
}

if (-not (Test-Path $StartScript)) {
    Write-Error "Missing start script: $StartScript"
}

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$StartScript`"" `
    -WorkingDirectory $ProjectRoot

$LogonTrigger = New-ScheduledTaskTrigger -AtLogOn
$StartupTrigger = New-ScheduledTaskTrigger -AtStartup
$Triggers = @($LogonTrigger, $StartupTrigger)

$CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Principal = New-ScheduledTaskPrincipal `
    -UserId $CurrentUser `
    -LogonType Interactive `
    -RunLevel Highest

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -Hidden `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Triggers `
    -Principal $Principal `
    -Settings $Settings `
    -Description "Systemo Agent background runner" `
    -Force | Out-Null

Write-Host "Scheduled task '$TaskName' installed."
