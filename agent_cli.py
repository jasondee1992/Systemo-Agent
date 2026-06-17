import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
CATALOG_FILE = BASE_DIR / "app_catalog.json"
JOBS_FILE = BASE_DIR / "jobs.json"
AGENT_LOG_FILE = BASE_DIR / "logs" / "agent.log"
ALLOWED_ACTION = "install"


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


def print_status():
    jobs = load_jobs()
    if not jobs:
        print("No jobs found.")
        return

    for job in jobs:
        if not isinstance(job, dict):
            print("- Invalid job entry")
            continue

        job_id = job.get("id", "<missing id>")
        app = job.get("app", "<missing app>")
        action = job.get("action", "<missing action>")
        status = job.get("status", "<missing status>")
        attempts = job.get("attempts", 0)
        message = job.get("message") or "-"
        last_error = job.get("last_error") or "-"

        print(f"- {job_id}")
        print(f"  app: {app}")
        print(f"  action: {action}")
        print(f"  status: {status}")
        print(f"  attempts: {attempts}")
        print(f"  message: {message}")
        print(f"  last_error: {last_error}")


def print_logs():
    if not AGENT_LOG_FILE.exists():
        print("logs/agent.log does not exist yet.")
        return

    with AGENT_LOG_FILE.open("r", encoding="utf-8", errors="replace") as file:
        lines = file.readlines()

    for line in lines[-50:]:
        print(line.rstrip())


def build_parser():
    parser = argparse.ArgumentParser(description="Systemo Agent local test CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_job_parser = subparsers.add_parser("add-job", help="Append an approved install job")
    add_job_parser.add_argument("app")

    subparsers.add_parser("status", help="Print current jobs")
    subparsers.add_parser("logs", help="Print the last 50 agent log lines")

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
        else:
            parser.error(f"Unknown command: {args.command}")
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
