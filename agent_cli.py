import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from agent import load_or_create_agent_config


BASE_DIR = Path(__file__).resolve().parent
CATALOG_FILE = BASE_DIR / "app_catalog.json"
JOBS_FILE = BASE_DIR / "jobs.json"
AGENT_LOG_FILE = BASE_DIR / "logs" / "agent.log"
ALLOWED_ACTION = "install"
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


def add_job(app):
    catalog = load_catalog()
    if app not in catalog:
        approved_apps = ", ".join(sorted(catalog.keys())) or "<none>"
        raise ValueError(f"Unsupported app '{app}'. Approved apps: {approved_apps}")

    jobs = load_jobs()
    job = {
        "id": f"job-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}",
        "app": app,
        "action": ALLOWED_ACTION,
        "status": "pending",
        "attempts": 0,
        "message": None,
    }
    jobs.append(job)
    save_jobs(jobs)
    print(f"Added job {job['id']} for {app} install")


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

    if action != ALLOWED_ACTION:
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


def build_parser():
    parser = argparse.ArgumentParser(description="Systemo Agent local test CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_job_parser = subparsers.add_parser("add-job", help="Append an approved install job")
    add_job_parser.add_argument("app")

    subparsers.add_parser("status", help="Print current jobs")
    subparsers.add_parser("logs", help="Print the last 50 agent log lines")
    subparsers.add_parser("info", help="Print local agent identity and config")
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
            add_job(args.app)
        elif args.command == "status":
            print_status()
        elif args.command == "logs":
            print_logs()
        elif args.command == "info":
            print_info()
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
