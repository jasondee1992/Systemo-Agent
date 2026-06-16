$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot
$LogsDirectory = Join-Path $ProjectRoot "logs"
$InstallerLog = Join-Path $LogsDirectory "installer.log"
$VenvDirectory = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvDirectory "Scripts\python.exe"
$RequirementsFile = Join-Path $ProjectRoot "requirements.txt"
$InstallTaskScript = Join-Path $ProjectRoot "scripts\install_task.ps1"
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
        throw "Run this installer from PowerShell as Administrator."
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
    Write-InstallerLog "Starting Systemo Agent installer"
    Assert-Administrator

    Set-Location $ProjectRoot
    Write-InstallerLog "Project directory: $ProjectRoot"

    if (-not (Test-Path $VenvDirectory)) {
        Write-InstallerLog "Creating virtual environment"
        python -m venv .venv 2>&1 | Write-CommandOutput
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create virtual environment"
        }
    }
    else {
        Write-InstallerLog "Virtual environment already exists"
    }

    if (-not (Test-Path $VenvPython)) {
        throw "Virtual environment Python not found at $VenvPython"
    }

    Write-InstallerLog "Upgrading pip"
    & $VenvPython -m pip install --upgrade pip 2>&1 | Write-CommandOutput
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upgrade pip"
    }

    if (-not (Test-Path $RequirementsFile)) {
        throw "Missing requirements file: $RequirementsFile"
    }

    Write-InstallerLog "Installing requirements"
    & $VenvPython -m pip install -r $RequirementsFile 2>&1 | Write-CommandOutput
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install requirements"
    }

    if (-not (Test-Path $InstallTaskScript)) {
        throw "Missing scheduled task installer: $InstallTaskScript"
    }

    Write-InstallerLog "Registering scheduled task"
    powershell -NoProfile -ExecutionPolicy Bypass -File $InstallTaskScript 2>&1 | Write-CommandOutput
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to register scheduled task"
    }

    Write-InstallerLog "Starting scheduled task: $TaskName"
    Start-ScheduledTask -TaskName $TaskName

    Write-InstallerLog "Systemo Agent installed and started successfully"
    exit 0
}
catch {
    Write-InstallerLog "Installer failed: $($_.Exception.Message)"
    exit 1
}
