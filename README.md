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

## Phase 7 Device Registration

When the agent is in API mode, it checks in with the mock backend using `POST /api/agent/check-in`. The backend stores known devices in `mock_backend/devices.json` and updates `last_seen_at` on each check-in.

Test device registration:

```powershell
python mock_server.py
python .\agent_cli.py set-mode api
Stop-ScheduledTask -TaskName "Systemo Agent"
Start-ScheduledTask -TaskName "Systemo Agent"
```

Wait 10-20 seconds, then list registered devices:

```powershell
python .\agent_cli.py api-list-devices
```

Show one device:

```powershell
python .\agent_cli.py api-show-device <device_id>
```

Verify that your local `device_id` appears and that `last_seen_at` updates while the agent is running in API mode.

## Phase 8 Mock Web Dashboard

The mock backend serves a local development dashboard at:

```text
http://127.0.0.1:8008
```

Run the mock server:

```powershell
python mock_server.py
```

Open the dashboard in your browser:

```text
http://127.0.0.1:8008
```

Set the agent to API mode and restart the scheduled task:

```powershell
python .\agent_cli.py set-mode api
Stop-ScheduledTask -TaskName "Systemo Agent"
Start-ScheduledTask -TaskName "Systemo Agent"
```

From the dashboard, create a `7zip` `install` job, wait for the job table to update, then create a `7zip` `uninstall` job. The dashboard uses the mock API and approved catalog options only; it is for local development testing and does not include authentication yet.

## Phase 9 Tenants / Companies

The mock backend stores tenants in `mock_backend/tenants.json`. Tenants are local mock company records only; Phase 9 does not add enrollment tokens, agent enrollment, device approval, login, ticket approval, or AI.

Start the mock server:

```powershell
python .\mock_server.py
```

Create tenant:

```powershell
python .\agent_cli.py api-create-tenant "Ybalai Builders"
```

List tenants:

```powershell
python .\agent_cli.py api-list-tenants
```

Show tenant:

```powershell
python .\agent_cli.py api-show-tenant <tenant_id>
```

Update tenant name:

```powershell
python .\agent_cli.py api-update-tenant <tenant_id> --name "Ybalai Builders Corp"
```

Deactivate tenant:

```powershell
python .\agent_cli.py api-update-tenant <tenant_id> --status inactive
```

Reactivate tenant:

```powershell
python .\agent_cli.py api-update-tenant <tenant_id> --status active
```

Confirm the existing API job flow still works:

```powershell
python .\agent_cli.py api-clear-jobs --yes
python .\agent_cli.py api-add-job 7zip install
Start-Sleep -Seconds 45
python .\agent_cli.py api-list-jobs
python .\agent_cli.py detect 7zip
```

The dashboard at `http://127.0.0.1:8008` also includes a Tenants / Companies section that lists tenants and creates a tenant by company name.

## Phase 10A Company Enrollment

Phase 10A adds manual company enrollment and device approval. The mock backend uses company records in `mock_backend/tenants.json` with a stable `company_id`, such as `Ybalai Builders` becoming `ybalai-builders`. Devices that check in with a new company name automatically create that company.

New devices start with `approval_status` set to `pending_approval`. Pending or rejected devices do not receive executable API jobs. Approved devices only receive jobs for their own company.

Start the mock server:

```powershell
python .\mock_server.py
```

Enroll this device under a manually typed company name:

```powershell
python .\agent_cli.py enroll-device --company "Ybalai Builders"
python .\agent_cli.py set-mode api
Stop-ScheduledTask -TaskName "Systemo Agent"
Start-ScheduledTask -TaskName "Systemo Agent"
```

Wait 10-20 seconds, then verify the device appears as pending:

```powershell
python .\agent_cli.py api-list-companies
python .\agent_cli.py api-list-devices
```

Approve the device:

```powershell
python .\agent_cli.py api-approve-device <device_id>
```

Create and verify an API install job:

```powershell
python .\agent_cli.py api-clear-jobs --yes
python .\agent_cli.py api-add-job 7zip install
Start-Sleep -Seconds 45
python .\agent_cli.py api-list-jobs
python .\agent_cli.py detect 7zip
```

Create and verify an API uninstall job:

```powershell
python .\agent_cli.py api-add-job 7zip uninstall
Start-Sleep -Seconds 45
python .\agent_cli.py api-list-jobs
python .\agent_cli.py detect 7zip
```

Verify pending or rejected devices do not execute jobs:

```powershell
python .\agent_cli.py api-reject-device <device_id>
python .\agent_cli.py api-add-job 7zip install
Start-Sleep -Seconds 20
python .\agent_cli.py api-list-jobs
```

The job should remain `approved` with `attempts: 0` until the device is approved again.

```powershell
python .\agent_cli.py api-approve-device <device_id>
```

The dashboard at `http://127.0.0.1:8008` shows companies, devices with approval status, approve/reject buttons, and a company-scoped job creation form.

## Phase 10B Dashboard Login and Roles

The mock dashboard now requires login. Prototype users are stored in `mock_backend/users.json` and are seeded automatically when missing.

Default users:

- `admin` / `admin123` / `system_admin`
- `ybalai_admin` / `admin123` / `company_admin` for `ybalai-builders`
- `ybalai_viewer` / `admin123` / `viewer` for `ybalai-builders`

Dashboard role rules:

- `system_admin` can view all companies, devices, and jobs, approve/reject any device, and create jobs for any company.
- `company_admin` can only view and manage its own company devices/jobs.
- `viewer` can only view its assigned company and cannot approve/reject devices or create jobs.

The agent check-in and job polling endpoints remain tokenless for this prototype, but approved-device and company-scoping checks still apply.

Start the mock server:

```powershell
python .\mock_server.py
```

Enroll device under a company:

```powershell
python .\agent_cli.py enroll-device --company "Ybalai Builders"
python .\agent_cli.py set-mode api
Stop-ScheduledTask -TaskName "Systemo Agent"
Start-ScheduledTask -TaskName "Systemo Agent"
```

Open the dashboard:

```text
http://127.0.0.1:8008
```

Login as system admin:

```text
username: admin
password: admin123
```

Verify all companies/devices are visible, approve the pending device, then create a `7zip` install job from the dashboard. Confirm the agent executes it:

```powershell
Start-Sleep -Seconds 45
python .\agent_cli.py api-list-jobs
python .\agent_cli.py detect 7zip
```

Create a `7zip` uninstall job from the dashboard and confirm it executes:

```powershell
Start-Sleep -Seconds 45
python .\agent_cli.py api-list-jobs
python .\agent_cli.py detect 7zip
```

Logout, then login as company admin:

```text
username: ybalai_admin
password: admin123
```

Verify only the `Ybalai Builders` company, devices, and jobs are visible. Company admins cannot access other company actions through protected dashboard APIs.

Logout, then login as viewer:

```text
username: ybalai_viewer
password: admin123
```

Verify the dashboard is read-only: no create job form and no approve/reject buttons. Agent job processing still works for approved jobs created by an admin.

## Phase 10C App Request Approval Flow

The dashboard now uses app requests as the default workflow. Viewers and company admins submit app requests, then a company admin or system admin approves or rejects them. Approved requests are converted into executable jobs for the agent.

Request rules:

- `system_admin` can view, create, approve, and reject requests for any company.
- `company_admin` can view, create, approve, and reject requests for their own company only.
- `viewer` can view and create requests for their own company only.
- Viewers cannot approve or reject requests.
- Existing CLI `api-add-job` still works for the prototype admin flow, but dashboard users should use app requests.

Start the mock server:

```powershell
python .\mock_server.py
```

Make sure the agent is enrolled and running in API mode:

```powershell
python .\agent_cli.py enroll-device --company "Ybalai Builders"
python .\agent_cli.py set-mode api
Stop-ScheduledTask -TaskName "Systemo Agent"
Start-ScheduledTask -TaskName "Systemo Agent"
```

Open the dashboard:

```text
http://127.0.0.1:8008
```

Login as viewer and create a 7-Zip install request:

```text
username: ybalai_viewer
password: admin123
```

Use Create App Request:

- Company: `ybalai-builders`
- Device target: `any`
- App: `7zip`
- Action: `install`

Verify the request is `pending` and that the viewer has no approve/reject buttons.

Logout, then login as company admin:

```text
username: ybalai_admin
password: admin123
```

Approve the pending request. The request should change to `converted_to_job` and show `linked_job_id`. Confirm the agent executes the install job:

```powershell
Start-Sleep -Seconds 45
python .\agent_cli.py api-list-jobs
python .\agent_cli.py detect 7zip
```

Create and approve a 7-Zip uninstall request from the dashboard, then confirm uninstall:

```powershell
Start-Sleep -Seconds 45
python .\agent_cli.py api-list-jobs
python .\agent_cli.py detect 7zip
```

Logout, then login as system admin:

```text
username: admin
password: admin123
```

Verify all companies, requests, jobs, and devices are visible. Company admins and viewers remain restricted to their assigned company through protected dashboard APIs.

Confirm the existing CLI direct job path still works if needed:

```powershell
python .\agent_cli.py api-add-job 7zip install
Start-Sleep -Seconds 45
python .\agent_cli.py api-list-jobs
```

## Phase 10D Audit Logs and Activity Timeline

The mock backend writes audit logs to `mock_backend/audit_logs.json`. The dashboard includes an Audit Logs section that shows the latest activity first.

Audit events include:

- User login success, login failure, and logout.
- Device enrollment, first heartbeat, approval, and rejection.
- App request creation, approval, and rejection.
- Job creation, agent job start, success, failure, and skipped results.
- Useful unauthorized access attempts.

Audit access follows dashboard roles:

- `system_admin` can see all audit logs.
- `company_admin` can see only their company audit logs.
- `viewer` can see only their company audit logs.

Start the mock server:

```powershell
python .\mock_server.py
```

Login as system admin and verify the login audit appears:

```text
http://127.0.0.1:8008
username: admin
password: admin123
```

Enroll and start the agent in API mode:

```powershell
python .\agent_cli.py enroll-device --company "Ybalai Builders"
python .\agent_cli.py set-mode api
Stop-ScheduledTask -TaskName "Systemo Agent"
Start-ScheduledTask -TaskName "Systemo Agent"
```

Wait 10-20 seconds, refresh the dashboard, and approve the pending device. The audit timeline should show device enrollment, first heartbeat, and device approval.

Logout, then login as viewer:

```text
username: ybalai_viewer
password: admin123
```

Create a `7zip install` app request and verify the audit timeline shows `APP_REQUEST_CREATED`. The viewer should not see approve/reject controls.

Logout, then login as company admin:

```text
username: ybalai_admin
password: admin123
```

Approve the request and verify the timeline shows `APP_REQUEST_APPROVED` and `JOB_CREATED`.

Confirm the agent executes the job:

```powershell
Start-Sleep -Seconds 45
python .\agent_cli.py api-list-jobs
python .\agent_cli.py detect 7zip
```

Refresh the dashboard and verify the timeline shows `JOB_STARTED` and `JOB_SUCCESS` or `JOB_SKIPPED`.

Test failed login auditing:

```text
Logout, then try username admin with password wrong-password.
```

Login again as `admin / admin123` and verify `USER_LOGIN_FAILED` appears.

To verify role scoping, create or use another company/device, then compare the Audit Logs section:

- `admin` should see all company audit logs.
- `ybalai_admin` should see only `Ybalai Builders` audit logs.
- `ybalai_viewer` should see only `Ybalai Builders` audit logs and has read-only access.

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
