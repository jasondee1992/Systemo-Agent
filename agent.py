import getpass
import json
import logging
import os
import platform
import socket
import subprocess
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
CONFIG_FILE = CONFIG_DIR / "agent_config.json"
RUNTIME_DIR = BASE_DIR / "runtime"
AGENT_STATE_FILE = RUNTIME_DIR / "agent_state.json"
JOBS_FILE = BASE_DIR / "jobs.json"
CATALOG_FILE = BASE_DIR / "app_catalog.json"
LOG_FILE = BASE_DIR / "logs" / "agent.log"
POLL_SECONDS = 5
ALLOWED_ACTIONS = {"install"}
AGENT_NAME = "Systemo Agent"
AGENT_VERSION = "0.3.0"
DEFAULT_JOB_SOURCE = "local"
DEFAULT_API_BASE_URL = "http://127.0.0.1:8008"
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

    LOGGER.setLevel(logging.DEBUG if is_debug_enabled() else logging.INFO)
    LOGGER.propagate = False


def is_debug_enabled():
    return os.environ.get("SYSTEMO_AGENT_DEBUG", "").lower() in {"1", "true", "yes", "on"}


def write_log(message):
    setup_logging()
    LOGGER.info(message)


def load_json(path, default):
    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = path.with_suffix(f"{path.suffix}.tmp")
    with temp_file.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)
        file.write("\n")
    temp_file.replace(path)


def save_jobs(jobs=None):
    if jobs is None:
        jobs = load_jobs()

    save_json(JOBS_FILE, jobs)


def get_username():
    try:
        return getpass.getuser()
    except Exception:
        return None


def get_os_info():
    return platform.platform()


def load_or_create_agent_config():
    now = utc_now()
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    config = load_json(CONFIG_FILE, {})
    if not isinstance(config, dict):
        config = {}

    if not config.get("device_id"):
        config["device_id"] = str(uuid.uuid4())

    if not config.get("created_at"):
        config["created_at"] = now

    config.update(
        {
            "updated_at": now,
            "hostname": socket.gethostname(),
            "os": get_os_info(),
            "username": get_username(),
            "agent_name": AGENT_NAME,
            "agent_version": AGENT_VERSION,
            "job_source": config.get("job_source") or DEFAULT_JOB_SOURCE,
            "api_base_url": config.get("api_base_url") or DEFAULT_API_BASE_URL,
        }
    )

    save_json(CONFIG_FILE, config)
    return config


def build_agent_state(
    config,
    status="running",
    last_loop_started_at=None,
    last_loop_finished_at=None,
    last_error=None,
):
    return {
        "status": status,
        "last_heartbeat_at": utc_now(),
        "device_id": config.get("device_id"),
        "hostname": config.get("hostname"),
        "agent_version": config.get("agent_version"),
        "current_pid": os.getpid(),
        "last_loop_started_at": last_loop_started_at,
        "last_loop_finished_at": last_loop_finished_at,
        "last_error": last_error,
    }


def write_agent_state(
    config,
    status="running",
    last_loop_started_at=None,
    last_loop_finished_at=None,
    last_error=None,
):
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    state = build_agent_state(
        config,
        status=status,
        last_loop_started_at=last_loop_started_at,
        last_loop_finished_at=last_loop_finished_at,
        last_error=last_error,
    )
    save_json(AGENT_STATE_FILE, state)

    if is_debug_enabled():
        LOGGER.debug("Heartbeat updated: %s", state["last_heartbeat_at"])


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


def get_next_attempt_count(job):
    try:
        return int(job.get("attempts") or 0) + 1
    except (TypeError, ValueError):
        return 1


def get_catalog_command(catalog, app, action):
    if action != "install":
        return None

    app_entry = catalog.get(app)
    if not isinstance(app_entry, dict):
        return None

    winget_id = app_entry.get("winget_id")
    install_args = app_entry.get("install_args", [])
    if not isinstance(winget_id, str) or not winget_id:
        return None

    if not isinstance(install_args, list) or not all(
        isinstance(arg, str) for arg in install_args
    ):
        return None

    return ["winget", "install", "--id", winget_id, *install_args]


def get_detection_command(catalog, app):
    app_entry = catalog.get(app)
    if not isinstance(app_entry, dict):
        return None

    detection_method = app_entry.get("detection_method")
    detection_id = app_entry.get("detection_id")
    if detection_method != "winget":
        return None

    if not isinstance(detection_id, str) or not detection_id:
        return None

    return [
        "winget",
        "list",
        "--id",
        detection_id,
        "--accept-source-agreements",
    ]


def is_app_installed(app_key):
    setup_logging()
    catalog = load_catalog()
    command = get_detection_command(catalog, app_key)
    if command is None:
        LOGGER.warning("Detection failed for %s: no approved detection command", app_key)
        return False

    detection_id = catalog[app_key]["detection_id"]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            shell=False,
            check=False,
        )
    except Exception:
        LOGGER.exception("Detection failed for %s", app_key)
        return False

    output = "\n".join(
        part.strip()
        for part in [completed.stdout, completed.stderr]
        if part and part.strip()
    )
    installed = detection_id.lower() in output.lower()

    if installed:
        LOGGER.info("Detection result for %s: installed", app_key)
    else:
        LOGGER.info("Detection result for %s: not installed", app_key)

    return installed


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

    detection_command = get_detection_command(catalog, app)
    if detection_command is None:
        return f"No approved detection command found for app '{app}'"

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


def save_local_job_state(jobs):
    def save():
        save_jobs(jobs)

    return save


def process_job_record(job, catalog, expected_status, save_state=None):
    if not isinstance(job, dict):
        write_log("Invalid job skipped: job must be a JSON object")
        return None

    job_id = get_job_label(job)
    if job.get("status") != expected_status:
        LOGGER.info("Job %s skipped: status is not %s", job_id, expected_status)
        return job

    def persist():
        if save_state is not None:
            save_state()

    app = job.get("app")
    action = job.get("action")
    job["attempts"] = get_next_attempt_count(job)
    job["started_at"] = utc_now()
    job["finished_at"] = None
    job["last_error"] = None
    job["message"] = "Processing job"
    persist()

    validation_error = validate_job(job, catalog)
    if validation_error:
        job["status"] = "failed"
        job["finished_at"] = utc_now()
        job["last_error"] = validation_error
        job["message"] = validation_error
        persist()
        LOGGER.warning("Job %s failed validation: %s", job_id, validation_error)
        return job

    command = get_catalog_command(catalog, app, action)

    if is_app_installed(app):
        job["status"] = "skipped"
        job["message"] = "Application is already installed"
        job["last_error"] = None
        job["finished_at"] = utc_now()
        persist()
        LOGGER.info("Job %s skipped: %s is already installed", job_id, app)
        return job

    job["status"] = "installing"
    job["finished_at"] = None
    job["last_error"] = None
    job["message"] = "Installing application"
    persist()
    LOGGER.info("Job %s started: %s %s", job_id, action, app)

    try:
        run_install(command)
        job["status"] = "success"
        job["last_error"] = None
        job["message"] = "Application installed successfully"
        LOGGER.info("Job %s succeeded", job_id)
    except Exception as error:
        job["status"] = "failed"
        job["last_error"] = str(error)
        job["message"] = "Application installation failed"
        LOGGER.exception("Job %s failed", job_id)
    finally:
        job["finished_at"] = utc_now()
        persist()

    return job


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
    process_job_record(job, catalog, "pending", save_state=save_local_job_state(jobs))


def process_pending_jobs():
    catalog = load_catalog()
    jobs = load_jobs()

    for job in jobs:
        if isinstance(job, dict) and job.get("status") == "pending":
            _process_job(job, jobs, catalog)


def get_requests_module():
    import requests

    return requests


def get_api_base_url(config):
    return str(config.get("api_base_url") or DEFAULT_API_BASE_URL).rstrip("/")


def fetch_api_jobs(config):
    requests = get_requests_module()
    api_base_url = get_api_base_url(config)
    response = requests.get(
        f"{api_base_url}/api/agent/jobs",
        params={"device_id": config.get("device_id")},
        timeout=10,
    )
    response.raise_for_status()
    jobs = response.json()
    if not isinstance(jobs, list):
        raise ValueError("API jobs response must be a JSON array")
    return jobs


def report_api_job_result(config, job):
    requests = get_requests_module()
    api_base_url = get_api_base_url(config)
    job_id = job.get("id")
    if not job_id:
        raise ValueError("API job missing id")

    payload = {
        "status": job.get("status"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "last_error": job.get("last_error"),
        "message": job.get("message"),
        "attempts": job.get("attempts"),
    }
    response = requests.post(
        f"{api_base_url}/api/agent/jobs/{job_id}/result",
        json=payload,
        timeout=10,
    )
    response.raise_for_status()


def process_api_jobs(config):
    catalog = load_catalog()
    jobs = fetch_api_jobs(config)

    for api_job in jobs:
        if not isinstance(api_job, dict):
            LOGGER.warning("Invalid API job skipped: job must be an object")
            continue

        if api_job.get("status") != "approved":
            LOGGER.info("API job %s skipped: status is not approved", get_job_label(api_job))
            continue

        processed_job = process_job_record(api_job, catalog, "approved")
        if processed_job is not None:
            report_api_job_result(config, processed_job)


def process_configured_job_source(config):
    job_source = config.get("job_source") or DEFAULT_JOB_SOURCE
    if job_source == "api":
        process_api_jobs(config)
    else:
        process_pending_jobs()


def run_agent_loop(stop_event=None):
    setup_logging()
    config = load_or_create_agent_config()
    LOGGER.info(
        "Agent identity loaded: device_id=%s hostname=%s agent_version=%s",
        config.get("device_id"),
        config.get("hostname"),
        config.get("agent_version"),
    )
    write_log("Systemo Agent started")
    write_log("Heartbeat enabled")

    while stop_event is None or not stop_event.is_set():
        loop_started_at = utc_now()
        write_agent_state(
            config,
            status="running",
            last_loop_started_at=loop_started_at,
            last_loop_finished_at=None,
            last_error=None,
        )

        try:
            process_configured_job_source(config)
        except Exception:
            error_traceback = traceback.format_exc()
            LOGGER.exception("Agent loop failed")
            write_agent_state(
                config,
                status="running",
                last_loop_started_at=loop_started_at,
                last_loop_finished_at=utc_now(),
                last_error=error_traceback,
            )
        else:
            write_agent_state(
                config,
                status="running",
                last_loop_started_at=loop_started_at,
                last_loop_finished_at=utc_now(),
                last_error=None,
            )

        if stop_event is None:
            time.sleep(POLL_SECONDS)
        else:
            stop_event.wait(POLL_SECONDS)

    write_log("Systemo Agent stopped")


def main():
    run_agent_loop()


if __name__ == "__main__":
    main()
