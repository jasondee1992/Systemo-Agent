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
