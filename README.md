# Systemo Agent

Phase 1 is a local Windows desktop agent MVP. It watches `jobs.json` and installs approved applications with `winget`.

There is no web app, no AI, and no arbitrary command execution in this phase. Jobs can only request approved apps and actions. The actual commands are loaded from `app_catalog.json`.

## Requirements

- Windows
- Python 3
- `winget` installed and available in your terminal

Some installs may require administrator permission. If an install fails because of permissions, run the terminal as Administrator and start the agent again.

## Run the agent

From this folder:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python agent.py
```

The agent checks `jobs.json` every 5 seconds. Logs are written to `logs/agent.log`, which is created automatically when the agent starts.

## Install Systemo Agent

Run from an Administrator PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_systemo_agent.ps1
```

The installer creates `.venv` if needed, installs `requirements.txt`, registers the scheduled task, starts it, and writes installer output to `logs/installer.log`.

Check whether the background task is running:

```powershell
Get-ScheduledTaskInfo -TaskName "Systemo Agent"
```

Manually start the background task:

```powershell
Start-ScheduledTask -TaskName "Systemo Agent"
```

## Test Jobs

Add a VLC install job:

```powershell
python .\agent_cli.py add-job vlc
```

Add a Chrome install job:

```powershell
python .\agent_cli.py add-job chrome
```

Check job status:

```powershell
python .\agent_cli.py status
```

View agent logs:

```powershell
python .\agent_cli.py logs
```

## Uninstall Systemo Agent

Run from an Administrator PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall_systemo_agent.ps1
```

The uninstaller stops and removes the scheduled task. It does not delete `jobs.json` or logs by default.

## Run in the Background

For the Phase 1.2 MVP, Systemo Agent uses Windows Task Scheduler as the background runner. A proper Windows Service can be added later during packaging.

Install the background task from an Administrator PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_task.ps1
```

Start manually:

```powershell
Start-ScheduledTask -TaskName "Systemo Agent"
```

Check task:

```powershell
Get-ScheduledTask -TaskName "Systemo Agent"
Get-ScheduledTaskInfo -TaskName "Systemo Agent"
```

Stop task:

```powershell
Stop-ScheduledTask -TaskName "Systemo Agent"
```

Uninstall task:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall_task.ps1
```

The scheduled task runs `scripts\start_agent.ps1`, which activates `.venv`, runs `python agent.py`, and writes task runner output to `logs/task-runner.log`.

## Troubleshooting

- Run PowerShell as Administrator when installing or uninstalling the scheduled task.
- Check `logs/task-runner.log` for Task Scheduler runner output.
- Check `logs/agent.log` for agent job processing logs.
- Open Task Scheduler and check Task Scheduler Library > Systemo Agent.
- During MVP testing, if a blank PowerShell window appears, do not close it because it is the background agent runner. Later packaging will hide this window properly.
- If the old pywin32 service was installed during earlier testing, remove it from an Administrator PowerShell with `sc.exe delete SystemoAgent`.

Do not bypass UAC. Do not auto-click UAC. Do not disable UAC.

## Trigger VLC install

Edit `jobs.json` so it contains a pending VLC install job:

```json
[
  {
    "id": "job-001",
    "app": "vlc",
    "action": "install",
    "status": "pending"
  }
]
```

## Trigger Chrome install

Edit `jobs.json` so it contains a pending Chrome install job:

```json
[
  {
    "id": "job-002",
    "app": "chrome",
    "action": "install",
    "status": "pending"
  }
]
```

## Job behavior

- Only jobs with `"status": "pending"` are processed.
- Only `"action": "install"` is allowed.
- Only apps listed in `app_catalog.json` are allowed.
- Before installation, the job status changes to `"installing"`.
- Successful installs change the job status to `"success"`.
- Failed installs change the job status to `"failed"` and save the error in `last_error`.
- Each processed job receives `started_at`, `finished_at`, and `last_error` fields.
