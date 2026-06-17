# Systemo Agent

Phase 1 is a local Windows desktop agent MVP. It watches `jobs.json` and installs or uninstalls approved applications with `winget`.

There is no web app, no AI, and no arbitrary command execution in this phase. Jobs can only request approved apps and actions. The actual install and uninstall commands are loaded from `app_catalog.json`.

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

On startup, Systemo Agent creates or updates `config/agent_config.json`. This file stores the local agent identity, including a stable `device_id`, hostname, OS, username when available, and the agent version. The `device_id` is generated once for this installed agent and is kept across restarts so the same client computer can be identified consistently later.

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

Add a 7-Zip install job:

```powershell
python .\agent_cli.py add-job 7zip install
```

Add a 7-Zip uninstall job:

```powershell
python .\agent_cli.py add-job 7zip uninstall
```

Add a VLC uninstall job:

```powershell
python .\agent_cli.py add-job vlc uninstall
```

Check job status:

```powershell
python .\agent_cli.py status
```

List all jobs newest first:

```powershell
python .\agent_cli.py list-jobs
```

Show one job:

```powershell
python .\agent_cli.py show-job <job_id>
```

Clear completed jobs:

```powershell
python .\agent_cli.py clear-completed
```

Clear failed jobs:

```powershell
python .\agent_cli.py clear-failed
```

Retry a failed job:

```powershell
python .\agent_cli.py retry-job <job_id>
```

View agent logs:

```powershell
python .\agent_cli.py logs
```

View local agent identity and config:

```powershell
python .\agent_cli.py info
```

Check local heartbeat health:

```powershell
python .\agent_cli.py health
```

Show current job source mode:

```powershell
python .\agent_cli.py mode
```

Run installed-app detection:

```powershell
python .\agent_cli.py detect vlc
python .\agent_cli.py detect chrome
python .\agent_cli.py detect 7zip
```

To test installed-app detection:

1. Add a VLC job and let the agent install VLC.
2. Add another VLC job:

```powershell
python .\agent_cli.py add-job vlc
```

3. Check status:

```powershell
python .\agent_cli.py status
```

The second VLC job should become `skipped` with the message `Application is already installed`.

## Phase 6 Mock API Mode

Local `jobs.json` mode remains the default. Phase 6 adds an optional mock backend API mode for testing backend polling.

Run the mock server in a separate terminal:

```powershell
python mock_server.py
```

After backend code changes, stop and restart `mock_server.py` so the new endpoints are loaded.

Set the agent to API mode:

```powershell
python .\agent_cli.py set-mode api
```

Restart the Systemo Agent scheduled task:

```powershell
Stop-ScheduledTask -TaskName "Systemo Agent"
Start-ScheduledTask -TaskName "Systemo Agent"
```

After agent code changes, restart the scheduled task so the running background agent loads the latest `agent.py`.

Clear mock API jobs:

```powershell
python .\agent_cli.py api-clear-jobs --yes
```

Add a test VLC job to the mock API:

```powershell
python .\agent_cli.py api-add-job vlc
```

Add API install/uninstall test jobs:

```powershell
python .\agent_cli.py api-add-job vlc uninstall
python .\agent_cli.py api-add-job 7zip install
python .\agent_cli.py api-add-job 7zip uninstall
```

List API jobs:

```powershell
python .\agent_cli.py api-list-jobs
```

Recommended API install/uninstall test flow:

```powershell
python .\agent_cli.py api-clear-jobs --yes
python .\agent_cli.py api-add-job 7zip install
python .\agent_cli.py api-list-jobs
python .\agent_cli.py api-add-job 7zip uninstall
python .\agent_cli.py api-list-jobs
```

Check agent health:

```powershell
python .\agent_cli.py health
```

Return to local mode:

```powershell
python .\agent_cli.py set-mode local
```

In API mode, the agent polls `GET /api/agent/jobs?device_id=<device_id>`, processes only jobs with `status` set to `approved`, and reports final results to `POST /api/agent/jobs/{job_id}/result`. API jobs are not copied into local `jobs.json`.

To test VLC detection after uninstall:

```powershell
winget uninstall --id VideoLAN.VLC
python .\agent_cli.py detect vlc
```

Expected detection result:

```text
installed: false
```

Then add a new API job:

```powershell
python .\agent_cli.py api-add-job vlc
python .\agent_cli.py api-list-jobs
```

Expected job result after the agent processes it:

```text
status: success
```

Job management examples:

```powershell
python .\agent_cli.py add-job vlc install
python .\agent_cli.py add-job 7zip uninstall
python .\agent_cli.py list-jobs
python .\agent_cli.py show-job job-20260617010101-abcd1234
python .\agent_cli.py clear-completed
python .\agent_cli.py retry-job job-20260617010101-abcd1234
```

`clear-completed` removes only `success` and `skipped` jobs. `clear-failed` removes only `failed` jobs. `retry-job` only works for failed jobs and sets the same job back to `pending`; it does not create a duplicate job.

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
- Run `python .\agent_cli.py health` to verify the background agent heartbeat.
- Open Task Scheduler and check Task Scheduler Library > Systemo Agent.
- If `winget` reports multiple versions installed during uninstall, the approved catalog can include `uninstall_all_versions` for that app. For 7-Zip, the catalog includes this so uninstall uses `--all-versions`.
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

## Trigger 7-Zip uninstall

Edit `jobs.json` so it contains a pending 7-Zip uninstall job:

```json
[
  {
    "id": "job-003",
    "app": "7zip",
    "action": "uninstall",
    "status": "pending"
  }
]
```

## Job behavior

- Only jobs with `"status": "pending"` are processed.
- Only `"action": "install"` and `"action": "uninstall"` are allowed.
- Only apps listed in `app_catalog.json` are allowed.
- Before installing, the agent checks `winget list --id <winget_id> --exact --accept-source-agreements`.
- If the app is already installed, the job status changes to `"skipped"` and no install command is run.
- Before installation, the job status changes to `"installing"`.
- Successful installs change the job status to `"success"`.
- Failed installs change the job status to `"failed"` and save the error in `last_error`.
- Before uninstalling, the agent checks whether the app is installed.
- If the app is not installed, the uninstall job status changes to `"skipped"` and no uninstall command is run.
- Uninstall jobs use only the approved catalog command: `winget uninstall --id <winget_id> --exact --silent --disable-interactivity --accept-source-agreements`.
- Apps that explicitly set `uninstall_all_versions` in `app_catalog.json` also include `--all-versions`; this is enabled for 7-Zip to handle machines with multiple installed versions.
- Successful uninstalls change the job status to `"success"`.
- If uninstall needs UI interaction or the user cancels it, the job status changes to `"requires_user_action"` or `"failed"` with a clear message and `last_error`.
- Each processed job receives `started_at`, `finished_at`, `message`, `attempts`, and `last_error` fields.
- `attempts` increments once when a pending job is processed. Failed jobs are not retried automatically yet.

Use 7-Zip as the primary install/uninstall automation test app. VLC uninstall may show UI on some machines.

## Agent Config

`config/agent_config.json` is created automatically if it does not exist. It contains:

- `agent_name`
- `agent_version`
- `device_id`
- `hostname`
- `os`
- `username`
- `created_at`
- `updated_at`

Do not store secrets in this file. Phase 3 is local-only and does not add a backend API, web app, or AI.

## Agent Heartbeat

The background agent writes `runtime/agent_state.json` when it starts and updates it every loop cycle. The state file includes:

- `status`
- `last_heartbeat_at`
- `device_id`
- `hostname`
- `agent_version`
- `current_pid`
- `last_loop_started_at`
- `last_loop_finished_at`
- `last_error`

Use this command to check whether the heartbeat is fresh:

```powershell
python .\agent_cli.py health
```

The health result is `healthy` when the heartbeat age is 15 seconds or less, `stale` when it is older than 15 seconds, and `missing` when `runtime/agent_state.json` does not exist.
