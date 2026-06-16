import json
import logging
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
JOBS_FILE = BASE_DIR / "jobs.json"
CATALOG_FILE = BASE_DIR / "app_catalog.json"
LOG_FILE = BASE_DIR / "logs" / "agent.log"
POLL_SECONDS = 5
ALLOWED_ACTIONS = {"install"}
LOGGER = logging.getLogger("systemo_agent")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def setup_logging():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    if not any(
        isinstance(handler, logging.FileHandler)
        and Path(handler.baseFilename) == LOG_FILE
        for handler in LOGGER.handlers
    ):
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
        LOGGER.addHandler(file_handler)

    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False


def write_log(message):
    setup_logging()
    LOGGER.info(message)


def load_json(path, default):
    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_jobs(jobs=None):
    if jobs is None:
        jobs = load_jobs()

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


def get_job_label(job):
    return job.get("id", "<missing id>")


def get_catalog_command(catalog, app, action):
    app_entry = catalog.get(app)
    if not isinstance(app_entry, dict):
        return None

    actions = app_entry.get("actions", {})
    if not isinstance(actions, dict):
        return None

    command = actions.get(action)
    if not isinstance(command, list) or not all(isinstance(arg, str) for arg in command):
        return None

    if not command or Path(command[0]).name.lower() not in {"winget", "winget.exe"}:
        return None

    return command


def validate_job(job, catalog):
    if not isinstance(job, dict):
        return "Job must be a JSON object"

    action = job.get("action")
    if action not in ALLOWED_ACTIONS:
        return f"Unsupported action: {action}"

    app = job.get("app")
    if app not in catalog:
        return f"Unsupported app: {app}"

    command = get_catalog_command(catalog, app, action)
    if command is None:
        return f"No approved command found for app '{app}' and action '{action}'"

    return None


def run_install(command):
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )

    if completed.returncode != 0:
        output = "\n".join(
            part.strip()
            for part in [completed.stdout, completed.stderr]
            if part and part.strip()
        )
        raise RuntimeError(output or f"Command failed with exit code {completed.returncode}")


def process_job(job):
    catalog = load_catalog()
    jobs = load_jobs()

    target_job = job
    job_id = job.get("id") if isinstance(job, dict) else None
    if job_id:
        for existing_job in jobs:
            if isinstance(existing_job, dict) and existing_job.get("id") == job_id:
                target_job = existing_job
                break
        else:
            jobs.append(target_job)
    else:
        jobs = [target_job]

    _process_job(target_job, jobs, catalog)


def _process_job(job, jobs, catalog):
    if not isinstance(job, dict):
        write_log("Invalid job skipped: job must be a JSON object")
        return

    job_id = get_job_label(job)
    if job.get("status") != "pending":
        LOGGER.info("Job %s skipped: status is not pending", job_id)
        return

    app = job.get("app")
    action = job.get("action")

    validation_error = validate_job(job, catalog)
    if validation_error:
        job["status"] = "failed"
        job["started_at"] = job.get("started_at") or utc_now()
        job["finished_at"] = utc_now()
        job["last_error"] = validation_error
        save_jobs(jobs)
        LOGGER.warning("Job %s failed validation: %s", job_id, validation_error)
        return

    command = get_catalog_command(catalog, app, action)
    job["status"] = "installing"
    job["started_at"] = utc_now()
    job["finished_at"] = None
    job["last_error"] = None
    save_jobs(jobs)
    LOGGER.info("Job %s started: %s %s", job_id, action, app)

    try:
        run_install(command)
        job["status"] = "success"
        job["last_error"] = None
        LOGGER.info("Job %s succeeded", job_id)
    except Exception as error:
        job["status"] = "failed"
        job["last_error"] = str(error)
        LOGGER.exception("Job %s failed", job_id)
    finally:
        job["finished_at"] = utc_now()
        save_jobs(jobs)


def process_pending_jobs():
    catalog = load_catalog()
    jobs = load_jobs()

    for job in jobs:
        if isinstance(job, dict) and job.get("status") == "pending":
            _process_job(job, jobs, catalog)


def run_agent_loop(stop_event=None):
    setup_logging()
    write_log("Systemo Agent started")

    while stop_event is None or not stop_event.is_set():
        try:
            process_pending_jobs()
        except Exception:
            LOGGER.exception("Agent loop failed")

        if stop_event is None:
            time.sleep(POLL_SECONDS)
        else:
            stop_event.wait(POLL_SECONDS)

    write_log("Systemo Agent stopped")


def main():
    run_agent_loop()


if __name__ == "__main__":
    main()
