import argparse
import json
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from agent import (
    AGENT_STATE_FILE,
    CONFIG_FILE,
    DEFAULT_API_BASE_URL,
    DEFAULT_JOB_SOURCE,
    detect_app_installation,
    load_or_create_agent_config,
    report_inventory_to_api,
    save_json,
    scan_installed_apps,
)


BASE_DIR = Path(__file__).resolve().parent
CATALOG_FILE = BASE_DIR / "app_catalog.json"
JOBS_FILE = BASE_DIR / "jobs.json"
AGENT_LOG_FILE = BASE_DIR / "logs" / "agent.log"
INSTALL_TASK_SCRIPT = BASE_DIR / "scripts" / "install_task.ps1"
UNINSTALL_TASK_SCRIPT = BASE_DIR / "scripts" / "uninstall_task.ps1"
TASK_NAME = "Systemo Agent"
ALLOWED_ACTIONS = {"install", "uninstall"}
COMPLETED_STATUSES = {"success", "skipped"}
FAILED_STATUS = "failed"
RETRY_MESSAGE = "Retry requested"
JOB_DISPLAY_FIELDS = [
    "id",
    "app",
    "action",
    "status",
    "attempts",
    "message",
    "last_error",
    "started_at",
    "finished_at",
]
DEVICE_DISPLAY_FIELDS = [
    "device_id",
    "company_name",
    "company_id",
    "hostname",
    "username",
    "os",
    "agent_version",
    "status",
    "approval_status",
    "last_seen_at",
]
COMPANY_DISPLAY_FIELDS = [
    "company_id",
    "company_name",
    "created_at",
    "updated_at",
]
INVENTORY_DISPLAY_FIELDS = [
    "display_name",
    "detected_name",
    "detected_id",
    "version",
    "source",
    "is_catalog_match",
    "last_seen_at",
]
TENANT_DISPLAY_FIELDS = [
    "tenant_id",
    "company_name",
    "status",
    "created_at",
    "updated_at",
]


def load_json(path, default):
    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_jobs(jobs):
    temp_file = JOBS_FILE.with_suffix(".json.tmp")
    with temp_file.open("w", encoding="utf-8") as file:
        json.dump(jobs, file, indent=2)
        file.write("\n")
    temp_file.replace(JOBS_FILE)


def load_catalog():
    catalog = load_json(CATALOG_FILE, {})
    if not isinstance(catalog, dict):
        raise ValueError("app_catalog.json must contain a JSON object")
    return catalog


def load_jobs():
    jobs = load_json(JOBS_FILE, [])
    if not isinstance(jobs, list):
        raise ValueError("jobs.json must contain a JSON array")
    return jobs


def get_requests_module():
    import requests

    return requests


def get_api_base_url(config):
    return str(config.get("api_base_url") or DEFAULT_API_BASE_URL).rstrip("/")


def normalize_api_url(api_url):
    api_url = (api_url or DEFAULT_API_BASE_URL).strip().rstrip("/")
    if not api_url:
        raise ValueError("API URL is required")
    if not re.match(r"^https?://", api_url, re.IGNORECASE):
        raise ValueError("API URL must start with http:// or https://")
    return api_url


def slugify_company_name(company_name):
    normalized_name = (company_name or "").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized_name).strip("-")
    if not slug:
        raise ValueError("Company name must contain letters or numbers")
    return slug


def run_powershell(command, check=True):
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        cwd=BASE_DIR,
        text=True,
        capture_output=True,
    )
    if check and completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(message or f"PowerShell command failed with exit code {completed.returncode}")
    return completed


def run_powershell_file(script_path):
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
        ],
        cwd=BASE_DIR,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(message or f"PowerShell script failed: {script_path}")
    return completed


def get_scheduled_task_status():
    command = rf"""
$Task = Get-ScheduledTask -TaskName "{TASK_NAME}" -ErrorAction SilentlyContinue
if ($null -eq $Task) {{
    [pscustomobject]@{{ installed = $false; state = "missing"; last_task_result = $null; last_run_time = $null; next_run_time = $null }} | ConvertTo-Json -Compress
    exit 0
}}
$Info = Get-ScheduledTaskInfo -TaskName "{TASK_NAME}" -ErrorAction SilentlyContinue
[pscustomobject]@{{
    installed = $true
    state = [string]$Task.State
    last_task_result = if ($Info) {{ $Info.LastTaskResult }} else {{ $null }}
    last_run_time = if ($Info) {{ $Info.LastRunTime }} else {{ $null }}
    next_run_time = if ($Info) {{ $Info.NextRunTime }} else {{ $null }}
}} | ConvertTo-Json -Compress
"""
    try:
        completed = run_powershell(command, check=False)
    except FileNotFoundError:
        return {"installed": False, "state": "unavailable", "error": "powershell not found"}

    if completed.returncode != 0:
        return {
            "installed": False,
            "state": "unknown",
            "error": (completed.stderr or completed.stdout or "").strip(),
        }

    try:
        status = json.loads(completed.stdout.strip())
    except json.JSONDecodeError:
        return {"installed": False, "state": "unknown", "error": completed.stdout.strip()}

    return status if isinstance(status, dict) else {"installed": False, "state": "unknown"}


def print_scheduled_task_status(prefix="scheduled_task"):
    status = get_scheduled_task_status()
    print(f"{prefix}_installed: {str(bool(status.get('installed'))).lower()}")
    print(f"{prefix}_state: {status.get('state') or '-'}")
    print(f"{prefix}_last_task_result: {status.get('last_task_result') if status.get('last_task_result') is not None else '-'}")
    print(f"{prefix}_last_run_time: {status.get('last_run_time') or '-'}")
    if status.get("error"):
        print(f"{prefix}_error: {status.get('error')}")


def stop_scheduled_task_if_exists():
    run_powershell(
        f'Stop-ScheduledTask -TaskName "{TASK_NAME}" -ErrorAction SilentlyContinue',
        check=False,
    )


def start_scheduled_task():
    run_powershell(f'Start-ScheduledTask -TaskName "{TASK_NAME}"')


def install_or_update_scheduled_task():
    if not INSTALL_TASK_SCRIPT.exists():
        raise ValueError(f"Missing scheduled task installer: {INSTALL_TASK_SCRIPT}")
    return run_powershell_file(INSTALL_TASK_SCRIPT)


def uninstall_scheduled_task():
    if not UNINSTALL_TASK_SCRIPT.exists():
        raise ValueError(f"Missing scheduled task uninstaller: {UNINSTALL_TASK_SCRIPT}")
    return run_powershell_file(UNINSTALL_TASK_SCRIPT)


def register_company(company_name):
    normalized_name = (company_name or "").strip()
    if not normalized_name:
        raise ValueError("Company name is required")

    config = load_or_create_agent_config()
    config["company_name"] = normalized_name
    config["company_id"] = slugify_company_name(normalized_name)
    save_json(CONFIG_FILE, config)
    print(f"Registered company {config['company_name']} ({config['company_id']}).")


def save_agent_api_config(company_name, api_url):
    normalized_company_name = (company_name or "").strip()
    if not normalized_company_name:
        raise ValueError("Company name is required")

    config = load_or_create_agent_config()
    config["job_source"] = "api"
    config["api_base_url"] = normalize_api_url(api_url)
    config["company_name"] = normalized_company_name
    config["company_id"] = slugify_company_name(normalized_company_name)
    save_json(CONFIG_FILE, config)
    return config


def validate_api_health(api_url):
    requests = get_requests_module()
    response = requests.get(f"{normalize_api_url(api_url)}/health", timeout=10)
    response.raise_for_status()
    health = response.json()
    if not isinstance(health, dict) or health.get("status") != "ok":
        raise ValueError(f"API health check did not return status ok: {health}")
    return health


def build_device_check_in_payload(config):
    return {
        "device_id": config.get("device_id"),
        "company_id": config.get("company_id"),
        "company_name": config.get("company_name"),
        "hostname": config.get("hostname"),
        "username": config.get("username"),
        "os": config.get("os"),
        "agent_name": config.get("agent_name") or "Systemo Agent",
        "agent_version": config.get("agent_version") or "0.3.0",
        "status": "online",
    }


def register_device_with_api(config):
    requests = get_requests_module()
    response = requests.post(
        f"{get_api_base_url(config)}/api/agent/check-in",
        json=build_device_check_in_payload(config),
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def get_current_api_device(config):
    if not config.get("device_id"):
        return None

    try:
        requests = get_requests_module()
        response = requests.get(
            f"{get_api_base_url(config)}/api/devices/{config.get('device_id')}",
            timeout=10,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        device = response.json()
        return device if isinstance(device, dict) else None
    except Exception:
        return None


def prompt_for_install_value(prompt, default=None):
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def wait_for_agent_health(timeout_seconds=20):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        state = load_json(AGENT_STATE_FILE, {}) if AGENT_STATE_FILE.exists() else {}
        heartbeat_age = get_heartbeat_age_seconds(state.get("last_heartbeat_at")) if isinstance(state, dict) else None
        if heartbeat_age is not None and heartbeat_age <= 15:
            return "healthy"
        time.sleep(2)
    return "stale"


def install_agent(company_name=None, api_url=None):
    api_url = normalize_api_url(api_url or prompt_for_install_value("API URL", DEFAULT_API_BASE_URL))
    company_name = company_name or prompt_for_install_value("Company Name")
    if not company_name:
        raise ValueError("Company Name is required")

    print(f"Checking API: {api_url}")
    validate_api_health(api_url)
    print("API health: ok")

    config = save_agent_api_config(company_name, api_url)
    device = register_device_with_api(config)
    approval_status = device.get("approval_status") if isinstance(device, dict) else None
    print(f"Device registered: {config.get('device_id')}")

    print("Installing or updating scheduled task...")
    install_or_update_scheduled_task()
    stop_scheduled_task_if_exists()
    start_scheduled_task()
    agent_status = wait_for_agent_health()

    refreshed_device = get_current_api_device(config) or device or {}
    print("")
    print("Systemo Agent install status")
    print(f"device_id: {config.get('device_id')}")
    print(f"company_name: {config.get('company_name')}")
    print(f"company_id: {config.get('company_id')}")
    print(f"api_base_url: {config.get('api_base_url')}")
    print(f"approval_status: {refreshed_device.get('approval_status') or approval_status or '-'}")
    print(f"agent_status: {agent_status}")
    print_scheduled_task_status()
    if (refreshed_device.get("approval_status") or approval_status) != "approved":
        print("next_instruction: wait for an admin to approve this device in the dashboard")
    else:
        print("next_instruction: device is approved and ready for API jobs")


def uninstall_agent(purge=False):
    print("Stopping scheduled task if it is running...")
    stop_scheduled_task_if_exists()
    print("Removing scheduled task...")
    uninstall_scheduled_task()

    if purge:
        if CONFIG_FILE.exists():
            CONFIG_FILE.unlink()
            print("Removed config/agent_config.json")
        if AGENT_STATE_FILE.exists():
            AGENT_STATE_FILE.unlink()
            print("Removed runtime/agent_state.json")
    else:
        print("Config preserved. Use --purge to remove local config and runtime state.")

    print_scheduled_task_status()


def validate_app_action(app, action):
    catalog = load_catalog()
    if app not in catalog:
        approved_apps = ", ".join(sorted(catalog.keys())) or "<none>"
        raise ValueError(f"Unsupported app '{app}'. Approved apps: {approved_apps}")

    if action not in ALLOWED_ACTIONS:
        approved_actions = ", ".join(sorted(ALLOWED_ACTIONS))
        raise ValueError(f"Unsupported action '{action}'. Approved actions: {approved_actions}")


def add_job(app, action="install"):
    validate_app_action(app, action)

    jobs = load_jobs()
    job = {
        "id": f"job-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}",
        "app": app,
        "action": action,
        "status": "pending",
        "attempts": 0,
        "message": None,
    }
    jobs.append(job)
    save_jobs(jobs)
    print(f"Added job {job['id']} for {app} {action}")


def print_mode():
    config = load_or_create_agent_config()
    print(f"job_source: {config.get('job_source') or DEFAULT_JOB_SOURCE}")
    print(f"api_base_url: {config.get('api_base_url') or DEFAULT_API_BASE_URL}")


def set_mode(mode):
    if mode not in {"local", "api"}:
        raise ValueError("Mode must be 'local' or 'api'")

    config = load_or_create_agent_config()
    config["job_source"] = mode
    config["api_base_url"] = config.get("api_base_url") or DEFAULT_API_BASE_URL
    save_json(CONFIG_FILE, config)
    print(f"Job source set to {mode}.")


def api_add_job(app, action="install"):
    validate_app_action(app, action)

    config = load_or_create_agent_config()
    requests = get_requests_module()
    payload = {"device_id": "any", "app": app, "action": action}
    if config.get("company_id"):
        payload["company_id"] = config.get("company_id")
    if config.get("company_name"):
        payload["company_name"] = config.get("company_name")
    response = requests.post(
        f"{get_api_base_url(config)}/api/agent/jobs",
        json=payload,
        timeout=10,
    )
    response.raise_for_status()
    job = response.json()
    print(f"Created API job {job.get('id')} for {app} {action}")


def api_list_jobs():
    config = load_or_create_agent_config()
    requests = get_requests_module()
    response = requests.get(f"{get_api_base_url(config)}/api/agent/jobs/all", timeout=10)
    response.raise_for_status()
    jobs = response.json()
    if not isinstance(jobs, list):
        raise ValueError("API jobs response must be a JSON array")
    print_jobs(list(reversed(jobs)))


def api_clear_jobs(yes=False):
    if not yes:
        answer = input("Remove all mock API jobs? Type 'yes' to continue: ")
        if answer.strip().lower() != "yes":
            print("Canceled.")
            return

    config = load_or_create_agent_config()
    requests = get_requests_module()
    response = requests.delete(f"{get_api_base_url(config)}/api/agent/jobs/all", timeout=10)
    response.raise_for_status()
    result = response.json()
    removed_count = result.get("removed")
    if not isinstance(removed_count, int):
        raise ValueError("API clear response missing removed count")
    print(f"Removed {removed_count} API job(s).")


def print_device(device):
    if not isinstance(device, dict):
        print("- Invalid device entry")
        return

    print(f"- {get_job_value(device, 'device_id')}")
    for field in DEVICE_DISPLAY_FIELDS[1:]:
        print(f"  {field}: {get_job_value(device, field)}")


def print_devices(devices):
    if not devices:
        print("No devices found.")
        return

    for device in devices:
        print_device(device)


def api_list_devices():
    config = load_or_create_agent_config()
    requests = get_requests_module()
    response = requests.get(f"{get_api_base_url(config)}/api/devices", timeout=10)
    response.raise_for_status()
    devices = response.json()
    if not isinstance(devices, list):
        raise ValueError("API devices response must be a JSON array")
    print_devices(devices)


def api_show_device(device_id):
    config = load_or_create_agent_config()
    requests = get_requests_module()
    response = requests.get(f"{get_api_base_url(config)}/api/devices/{device_id}", timeout=10)
    response.raise_for_status()
    device = response.json()
    print_device(device)


def print_company(company):
    if not isinstance(company, dict):
        print("- Invalid company entry")
        return

    print(f"- {get_job_value(company, 'company_id')}")
    for field in COMPANY_DISPLAY_FIELDS[1:]:
        print(f"  {field}: {get_job_value(company, field)}")


def print_companies(companies):
    if not companies:
        print("No companies found.")
        return

    for company in companies:
        print_company(company)


def api_list_companies():
    config = load_or_create_agent_config()
    requests = get_requests_module()
    response = requests.get(f"{get_api_base_url(config)}/api/admin/companies", timeout=10)
    response.raise_for_status()
    companies = response.json()
    if not isinstance(companies, list):
        raise ValueError("API companies response must be a JSON array")
    print_companies(companies)


def api_approve_device(device_id):
    config = load_or_create_agent_config()
    requests = get_requests_module()
    response = requests.post(
        f"{get_api_base_url(config)}/api/admin/devices/{device_id}/approve",
        timeout=10,
    )
    response.raise_for_status()
    device = response.json()
    print(f"Approved device {device.get('device_id')}.")


def api_reject_device(device_id):
    config = load_or_create_agent_config()
    requests = get_requests_module()
    response = requests.post(
        f"{get_api_base_url(config)}/api/admin/devices/{device_id}/reject",
        timeout=10,
    )
    response.raise_for_status()
    device = response.json()
    print(f"Rejected device {device.get('device_id')}.")


def print_tenant(tenant):
    if not isinstance(tenant, dict):
        print("- Invalid tenant entry")
        return

    print(f"- {get_job_value(tenant, 'tenant_id')}")
    for field in TENANT_DISPLAY_FIELDS[1:]:
        print(f"  {field}: {get_job_value(tenant, field)}")


def print_tenants(tenants):
    if not tenants:
        print("No tenants found.")
        return

    for tenant in tenants:
        print_tenant(tenant)


def api_create_tenant(company_name):
    config = load_or_create_agent_config()
    requests = get_requests_module()
    response = requests.post(
        f"{get_api_base_url(config)}/api/admin/tenants",
        json={"company_name": company_name},
        timeout=10,
    )
    response.raise_for_status()
    tenant = response.json()
    print(f"Created tenant {tenant.get('tenant_id')} for {tenant.get('company_name')}")


def api_list_tenants():
    config = load_or_create_agent_config()
    requests = get_requests_module()
    response = requests.get(f"{get_api_base_url(config)}/api/admin/tenants", timeout=10)
    response.raise_for_status()
    tenants = response.json()
    if not isinstance(tenants, list):
        raise ValueError("API tenants response must be a JSON array")
    print_tenants(tenants)


def api_show_tenant(tenant_id):
    config = load_or_create_agent_config()
    requests = get_requests_module()
    response = requests.get(f"{get_api_base_url(config)}/api/admin/tenants/{tenant_id}", timeout=10)
    response.raise_for_status()
    tenant = response.json()
    print_tenant(tenant)


def api_update_tenant(tenant_id, company_name=None, status=None):
    if company_name is None and status is None:
        raise ValueError("Provide --name and/or --status")

    payload = {}
    if company_name is not None:
        payload["company_name"] = company_name
    if status is not None:
        payload["status"] = status

    config = load_or_create_agent_config()
    requests = get_requests_module()
    response = requests.patch(
        f"{get_api_base_url(config)}/api/admin/tenants/{tenant_id}",
        json=payload,
        timeout=10,
    )
    response.raise_for_status()
    tenant = response.json()
    print(f"Updated tenant {tenant.get('tenant_id')}.")


def detect_app(app):
    catalog = load_catalog()
    if app not in catalog:
        approved_apps = ", ".join(sorted(catalog.keys())) or "<none>"
        raise ValueError(f"Unsupported app '{app}'. Approved apps: {approved_apps}")

    result = detect_app_installation(app)
    print(f"app: {app}")
    print(f"installed: {str(result.get('installed')).lower()}")
    print(f"winget_id: {result.get('winget_id') or '-'}")
    print(f"return_code: {result.get('return_code') if result.get('return_code') is not None else '-'}")
    print(f"output_preview: {result.get('output_preview') or '-'}")


def print_inventory_app(app):
    if not isinstance(app, dict):
        print("- Invalid inventory entry")
        return

    label = app.get("display_name") or app.get("detected_name") or app.get("name") or "-"
    print(f"- {label}")
    for field in INVENTORY_DISPLAY_FIELDS[1:]:
        print(f"  {field}: {get_job_value(app, field)}")


def print_inventory_apps(apps, limit=None):
    if not apps:
        print("No inventory records found.")
        return

    visible_apps = apps[:limit] if limit else apps
    for app in visible_apps:
        print_inventory_app(app)
    if limit and len(apps) > limit:
        print(f"... {len(apps) - limit} more app(s)")


def scan_inventory():
    config = load_or_create_agent_config()
    apps = scan_installed_apps()
    print(f"local_apps_found: {len(apps)}")

    if (config.get("job_source") or DEFAULT_JOB_SOURCE) == "api":
        result = report_inventory_to_api(config, apps, status="success")
        print(f"api_scan_id: {result.get('scan_id')}")
        print(f"api_status: {result.get('status')}")
        print(f"api_apps_found: {result.get('apps_found_count')}")
        print(f"api_catalog_matches: {result.get('catalog_matches_count')}")
    else:
        print_inventory_apps(apps, limit=25)


def api_device_inventory(device_id):
    config = load_or_create_agent_config()
    requests = get_requests_module()
    response = requests.get(
        f"{get_api_base_url(config)}/api/devices/{device_id}/inventory",
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    device = payload.get("device") if isinstance(payload, dict) else {}
    latest_scan = payload.get("latest_scan") if isinstance(payload, dict) else None
    apps = payload.get("apps") if isinstance(payload, dict) else []
    print(f"device_id: {device.get('device_id') or device_id}")
    print(f"company_name: {device.get('company_name') or '-'}")
    print(f"latest_scan_status: {(latest_scan or {}).get('status') or '-'}")
    print(f"latest_scan_finished_at: {(latest_scan or {}).get('finished_at') or '-'}")
    print(f"apps_found: {len(apps) if isinstance(apps, list) else 0}")
    print_inventory_apps(apps if isinstance(apps, list) else [])


def print_inventory():
    config = load_or_create_agent_config()
    if (config.get("job_source") or DEFAULT_JOB_SOURCE) == "api" and config.get("device_id"):
        api_device_inventory(config.get("device_id"))
        return

    apps = scan_installed_apps()
    print(f"local_apps_found: {len(apps)}")
    print_inventory_apps(apps, limit=25)


def get_job_value(job, field):
    value = job.get(field)
    if value is None or value == "":
        return "-"
    return value


def print_job(job):
    if not isinstance(job, dict):
        print("- Invalid job entry")
        return

    print(f"- {get_job_value(job, 'id')}")
    for field in JOB_DISPLAY_FIELDS[1:]:
        print(f"  {field}: {get_job_value(job, field)}")


def find_job(jobs, job_id):
    for index, job in enumerate(jobs):
        if isinstance(job, dict) and job.get("id") == job_id:
            return index, job
    return None, None


def validate_retry_job(job):
    catalog = load_catalog()
    app = job.get("app")
    action = job.get("action")

    if app not in catalog:
        approved_apps = ", ".join(sorted(catalog.keys())) or "<none>"
        raise ValueError(
            f"Cannot retry job with unsupported app '{app}'. Approved apps: {approved_apps}"
        )

    if action not in ALLOWED_ACTIONS:
        raise ValueError(f"Cannot retry unsupported action '{action}'")


def print_jobs(jobs):
    if not jobs:
        print("No jobs found.")
        return

    for job in jobs:
        print_job(job)


def print_status():
    jobs = load_jobs()
    print_jobs(jobs)


def list_jobs():
    jobs = load_jobs()
    print_jobs(list(reversed(jobs)))


def clear_completed():
    jobs = load_jobs()
    kept_jobs = [
        job
        for job in jobs
        if not (isinstance(job, dict) and job.get("status") in COMPLETED_STATUSES)
    ]
    removed_count = len(jobs) - len(kept_jobs)
    save_jobs(kept_jobs)
    print(f"Removed {removed_count} completed job(s).")


def clear_failed():
    jobs = load_jobs()
    kept_jobs = [
        job
        for job in jobs
        if not (isinstance(job, dict) and job.get("status") == FAILED_STATUS)
    ]
    removed_count = len(jobs) - len(kept_jobs)
    save_jobs(kept_jobs)
    print(f"Removed {removed_count} failed job(s).")


def retry_job(job_id):
    jobs = load_jobs()
    _, job = find_job(jobs, job_id)
    if job is None:
        raise ValueError(f"Job not found: {job_id}")

    if job.get("status") != FAILED_STATUS:
        raise ValueError("Only failed jobs can be retried")

    validate_retry_job(job)
    job["status"] = "pending"
    job["last_error"] = None
    job["message"] = RETRY_MESSAGE
    job["started_at"] = None
    job["finished_at"] = None
    save_jobs(jobs)
    print(f"Retry requested for job {job_id}.")


def show_job(job_id):
    jobs = load_jobs()
    _, job = find_job(jobs, job_id)
    if job is None:
        raise ValueError(f"Job not found: {job_id}")

    print_job(job)


def print_logs():
    if not AGENT_LOG_FILE.exists():
        print("logs/agent.log does not exist yet.")
        return

    with AGENT_LOG_FILE.open("r", encoding="utf-8", errors="replace") as file:
        lines = file.readlines()

    for line in lines[-50:]:
        print(line.rstrip())


def print_info():
    config = load_or_create_agent_config()
    fields = [
        "agent_name",
        "agent_version",
        "device_id",
        "job_source",
        "api_base_url",
        "company_id",
        "company_name",
        "hostname",
        "os",
        "username",
        "created_at",
        "updated_at",
    ]

    for field in fields:
        print(f"{field}: {config.get(field) or '-'}")

    device = get_current_api_device(config) if (config.get("job_source") == "api") else None
    print(f"approval_status: {device.get('approval_status') or '-' if device else '-'}")
    print_scheduled_task_status()


def parse_timestamp(timestamp):
    if not timestamp:
        return None

    try:
        return datetime.fromisoformat(timestamp)
    except ValueError:
        return None


def get_heartbeat_age_seconds(last_heartbeat_at):
    heartbeat_time = parse_timestamp(last_heartbeat_at)
    if heartbeat_time is None:
        return None

    if heartbeat_time.tzinfo is None:
        heartbeat_time = heartbeat_time.replace(tzinfo=timezone.utc)

    return max(0, int((datetime.now(timezone.utc) - heartbeat_time).total_seconds()))


def print_health():
    config = load_or_create_agent_config()
    state_exists = AGENT_STATE_FILE.exists()
    state = load_json(AGENT_STATE_FILE, {}) if state_exists else {}
    if not isinstance(state, dict):
        state = {}

    last_heartbeat_at = state.get("last_heartbeat_at")
    heartbeat_age = get_heartbeat_age_seconds(last_heartbeat_at)

    if not state_exists:
        health_result = "missing"
    elif heartbeat_age is not None and heartbeat_age <= 15:
        health_result = "healthy"
    else:
        health_result = "stale"

    print(f"agent_name: {config.get('agent_name') or '-'}")
    print(f"agent_version: {state.get('agent_version') or config.get('agent_version') or '-'}")
    print(f"device_id: {state.get('device_id') or config.get('device_id') or '-'}")
    print(f"hostname: {state.get('hostname') or config.get('hostname') or '-'}")
    print(f"status: {state.get('status') or '-'}")
    print(f"current_pid: {state.get('current_pid') or '-'}")
    print(f"last_heartbeat_at: {last_heartbeat_at or '-'}")
    print(f"heartbeat_age_seconds: {heartbeat_age if heartbeat_age is not None else '-'}")
    print(f"health_result: {health_result}")
    job_source = config.get("job_source") or DEFAULT_JOB_SOURCE
    print(f"job_source: {job_source}")
    if job_source == "api":
        print(f"api_base_url: {config.get('api_base_url') or DEFAULT_API_BASE_URL}")
        print(f"company_id: {config.get('company_id') or '-'}")
        print(f"company_name: {config.get('company_name') or '-'}")
        device = get_current_api_device(config)
        print(f"approval_status: {device.get('approval_status') or '-' if device else '-'}")
        if not config.get("company_id") and not config.get("company_name"):
            print("company_warning: no company configured; API check-in and jobs are company-scoped")
    print_scheduled_task_status()


def build_parser():
    parser = argparse.ArgumentParser(description="Systemo Agent local test CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_job_parser = subparsers.add_parser("add-job", help="Append an approved job")
    add_job_parser.add_argument("app")
    add_job_parser.add_argument("action", nargs="?", default="install", choices=sorted(ALLOWED_ACTIONS))

    subparsers.add_parser("mode", help="Print current job source mode")

    install_agent_parser = subparsers.add_parser("install-agent", help="Enroll and install the background agent")
    install_agent_parser.add_argument("--company", dest="company_name")
    install_agent_parser.add_argument("--api-url", dest="api_url")

    uninstall_agent_parser = subparsers.add_parser("uninstall-agent", help="Stop and remove the background agent task")
    uninstall_agent_parser.add_argument("--purge", action="store_true", help="Remove local config and runtime state")

    register_company_parser = subparsers.add_parser("register-company", help="Store local company enrollment")
    register_company_parser.add_argument("company_name")

    enroll_device_parser = subparsers.add_parser("enroll-device", help="Store local device company enrollment")
    enroll_device_parser.add_argument("--company", required=True)

    set_mode_parser = subparsers.add_parser("set-mode", help="Set job source mode")
    set_mode_parser.add_argument("mode", choices=["local", "api"])

    api_add_job_parser = subparsers.add_parser("api-add-job", help="Create an approved mock API job")
    api_add_job_parser.add_argument("app")
    api_add_job_parser.add_argument("action", nargs="?", default="install", choices=sorted(ALLOWED_ACTIONS))

    subparsers.add_parser("api-list-jobs", help="List mock API jobs")

    api_clear_jobs_parser = subparsers.add_parser("api-clear-jobs", help="Remove all mock API jobs")
    api_clear_jobs_parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")

    subparsers.add_parser("api-list-devices", help="List mock API devices")

    api_show_device_parser = subparsers.add_parser("api-show-device", help="Show one mock API device")
    api_show_device_parser.add_argument("device_id")

    subparsers.add_parser("api-list-companies", help="List mock API companies")

    api_approve_device_parser = subparsers.add_parser("api-approve-device", help="Approve a mock API device")
    api_approve_device_parser.add_argument("device_id")

    api_reject_device_parser = subparsers.add_parser("api-reject-device", help="Reject a mock API device")
    api_reject_device_parser.add_argument("device_id")

    api_create_tenant_parser = subparsers.add_parser("api-create-tenant", help="Create a mock API tenant")
    api_create_tenant_parser.add_argument("company_name")

    subparsers.add_parser("api-list-tenants", help="List mock API tenants")

    api_show_tenant_parser = subparsers.add_parser("api-show-tenant", help="Show one mock API tenant")
    api_show_tenant_parser.add_argument("tenant_id")

    api_update_tenant_parser = subparsers.add_parser("api-update-tenant", help="Update a mock API tenant")
    api_update_tenant_parser.add_argument("tenant_id")
    api_update_tenant_parser.add_argument("--name", dest="company_name")
    api_update_tenant_parser.add_argument("--status", choices=["active", "inactive"])

    detect_parser = subparsers.add_parser("detect", help="Run approved app detection")
    detect_parser.add_argument("app")

    subparsers.add_parser("scan-inventory", help="Scan installed apps and report to API in API mode")
    subparsers.add_parser("inventory", help="Show local or API inventory summary")

    api_device_inventory_parser = subparsers.add_parser("api-device-inventory", help="Show API inventory for one device")
    api_device_inventory_parser.add_argument("device_id")

    subparsers.add_parser("status", help="Print current jobs")
    subparsers.add_parser("logs", help="Print the last 50 agent log lines")
    subparsers.add_parser("info", help="Print local agent identity and config")
    subparsers.add_parser("health", help="Print local agent heartbeat health")
    subparsers.add_parser("list-jobs", help="Print all jobs newest first")
    subparsers.add_parser("clear-completed", help="Remove success and skipped jobs")
    subparsers.add_parser("clear-failed", help="Remove failed jobs")

    retry_job_parser = subparsers.add_parser("retry-job", help="Retry a failed job")
    retry_job_parser.add_argument("job_id")

    show_job_parser = subparsers.add_parser("show-job", help="Print one job")
    show_job_parser.add_argument("job_id")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "add-job":
            add_job(args.app, args.action)
        elif args.command == "mode":
            print_mode()
        elif args.command == "install-agent":
            install_agent(args.company_name, args.api_url)
        elif args.command == "uninstall-agent":
            uninstall_agent(args.purge)
        elif args.command == "register-company":
            register_company(args.company_name)
        elif args.command == "enroll-device":
            register_company(args.company)
        elif args.command == "set-mode":
            set_mode(args.mode)
        elif args.command == "api-add-job":
            api_add_job(args.app, args.action)
        elif args.command == "api-list-jobs":
            api_list_jobs()
        elif args.command == "api-clear-jobs":
            api_clear_jobs(args.yes)
        elif args.command == "api-list-devices":
            api_list_devices()
        elif args.command == "api-show-device":
            api_show_device(args.device_id)
        elif args.command == "api-list-companies":
            api_list_companies()
        elif args.command == "api-approve-device":
            api_approve_device(args.device_id)
        elif args.command == "api-reject-device":
            api_reject_device(args.device_id)
        elif args.command == "api-create-tenant":
            api_create_tenant(args.company_name)
        elif args.command == "api-list-tenants":
            api_list_tenants()
        elif args.command == "api-show-tenant":
            api_show_tenant(args.tenant_id)
        elif args.command == "api-update-tenant":
            api_update_tenant(args.tenant_id, args.company_name, args.status)
        elif args.command == "detect":
            detect_app(args.app)
        elif args.command == "scan-inventory":
            scan_inventory()
        elif args.command == "inventory":
            print_inventory()
        elif args.command == "api-device-inventory":
            api_device_inventory(args.device_id)
        elif args.command == "status":
            print_status()
        elif args.command == "logs":
            print_logs()
        elif args.command == "info":
            print_info()
        elif args.command == "health":
            print_health()
        elif args.command == "list-jobs":
            list_jobs()
        elif args.command == "clear-completed":
            clear_completed()
        elif args.command == "clear-failed":
            clear_failed()
        elif args.command == "retry-job":
            retry_job(args.job_id)
        elif args.command == "show-job":
            show_job(args.job_id)
        else:
            parser.error(f"Unknown command: {args.command}")
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
