$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot
$LogsDirectory = Join-Path $ProjectRoot "logs"
$InstallerLog = Join-Path $LogsDirectory "installer.log"
$UninstallTaskScript = Join-Path $ProjectRoot "scripts\uninstall_task.ps1"
$TaskName = "Systemo Agent"

function Write-InstallerLog {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    $Line = "[$(Get-Date -Format o)] $Message"
    Write-Host $Message
    $Line | Out-File -FilePath $InstallerLog -Append -Encoding utf8
}

function Assert-Administrator {
    $Principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Run this uninstaller from PowerShell as Administrator."
    }
}

function Write-CommandOutput {
    process {
        $Text = $_ | Out-String
        $Text = $Text.TrimEnd()
        if ($Text.Length -gt 0) {
            Write-Host $Text
            $Text | Out-File -FilePath $InstallerLog -Append -Encoding utf8
        }
    }
}

New-Item -ItemType Directory -Path $LogsDirectory -Force | Out-Null

try {
    Write-InstallerLog "Starting Systemo Agent uninstaller"
    Assert-Administrator

    Set-Location $ProjectRoot
    Write-InstallerLog "Project directory: $ProjectRoot"

    $Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -ne $Task) {
        Write-InstallerLog "Stopping scheduled task if running"
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    }
    else {
        Write-InstallerLog "Scheduled task is not installed"
    }

    if (-not (Test-Path $UninstallTaskScript)) {
        throw "Missing scheduled task uninstaller: $UninstallTaskScript"
    }

    Write-InstallerLog "Unregistering scheduled task"
    powershell -NoProfile -ExecutionPolicy Bypass -File $UninstallTaskScript 2>&1 | Write-CommandOutput
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to unregister scheduled task"
    }

    Write-InstallerLog "Systemo Agent uninstalled successfully. jobs.json and logs were not deleted."
    exit 0
}
catch {
    Write-InstallerLog "Uninstaller failed: $($_.Exception.Message)"
    exit 1
}
