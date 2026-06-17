import argparse
import json
import sys
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
    save_json,
)


BASE_DIR = Path(__file__).resolve().parent
CATALOG_FILE = BASE_DIR / "app_catalog.json"
JOBS_FILE = BASE_DIR / "jobs.json"
AGENT_LOG_FILE = BASE_DIR / "logs" / "agent.log"
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
    "hostname",
    "username",
    "os",
    "agent_version",
    "status",
    "last_seen_at",
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
    response = requests.post(
        f"{get_api_base_url(config)}/api/agent/jobs",
        json={"device_id": "any", "app": app, "action": action},
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
        "hostname",
        "os",
        "username",
        "created_at",
        "updated_at",
    ]

    for field in fields:
        print(f"{field}: {config.get(field) or '-'}")


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


def build_parser():
    parser = argparse.ArgumentParser(description="Systemo Agent local test CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_job_parser = subparsers.add_parser("add-job", help="Append an approved job")
    add_job_parser.add_argument("app")
    add_job_parser.add_argument("action", nargs="?", default="install", choices=sorted(ALLOWED_ACTIONS))

    subparsers.add_parser("mode", help="Print current job source mode")

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

    detect_parser = subparsers.add_parser("detect", help="Run approved app detection")
    detect_parser.add_argument("app")

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
        elif args.command == "detect":
            detect_app(args.app)
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
