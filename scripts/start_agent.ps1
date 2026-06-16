$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LogDirectory = Join-Path $ProjectRoot "logs"
$LogFile = Join-Path $LogDirectory "task-runner.log"
$ActivateScript = Join-Path $ProjectRoot ".venv\Scripts\Activate.ps1"
$AgentScript = Join-Path $ProjectRoot "agent.py"

New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
Set-Location $ProjectRoot

"[$(Get-Date -Format o)] Starting Systemo Agent task runner" | Out-File -FilePath $LogFile -Append -Encoding utf8
"[$(Get-Date -Format o)] Project root: $ProjectRoot" | Out-File -FilePath $LogFile -Append -Encoding utf8
"[$(Get-Date -Format o)] PowerShell process id: $PID" | Out-File -FilePath $LogFile -Append -Encoding utf8

if (-not (Test-Path $ActivateScript)) {
    "[$(Get-Date -Format o)] Virtual environment not found at $ActivateScript" | Out-File -FilePath $LogFile -Append -Encoding utf8
    exit 1
}

. $ActivateScript

if (-not (Test-Path $AgentScript)) {
    "[$(Get-Date -Format o)] Agent script not found at $AgentScript" | Out-File -FilePath $LogFile -Append -Encoding utf8
    exit 1
}

"[$(Get-Date -Format o)] Activated virtual environment: $env:VIRTUAL_ENV" | Out-File -FilePath $LogFile -Append -Encoding utf8
"[$(Get-Date -Format o)] Python executable: $(Get-Command python | Select-Object -ExpandProperty Source)" | Out-File -FilePath $LogFile -Append -Encoding utf8
"[$(Get-Date -Format o)] Launching agent.py; this process remains running while the agent is active" | Out-File -FilePath $LogFile -Append -Encoding utf8

try {
    python agent.py *>> $LogFile
}
catch {
    "[$(Get-Date -Format o)] Systemo Agent task runner failed: $($_.Exception.Message)" | Out-File -FilePath $LogFile -Append -Encoding utf8
    throw
}
