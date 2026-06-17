import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR / "mock_backend"
JOBS_FILE = BACKEND_DIR / "jobs.json"
ALLOWED_APPS = {"vlc", "chrome"}
ALLOWED_ACTIONS = {"install"}

app = FastAPI(title="Systemo Agent Mock Backend")


class CreateJobRequest(BaseModel):
    device_id: str = "any"
    app: str
    action: str = "install"


class JobResultRequest(BaseModel):
    status: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    last_error: Optional[str] = None
    message: Optional[str] = None
    attempts: Optional[int] = None


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def load_jobs():
    BACKEND_DIR.mkdir(parents=True, exist_ok=True)
    if not JOBS_FILE.exists():
        save_jobs([])
        return []

    with JOBS_FILE.open("r", encoding="utf-8") as file:
        jobs = json.load(file)

    if not isinstance(jobs, list):
        raise HTTPException(status_code=500, detail="mock_backend/jobs.json must contain an array")

    return jobs


def save_jobs(jobs):
    BACKEND_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = JOBS_FILE.with_suffix(".json.tmp")
    with temp_file.open("w", encoding="utf-8") as file:
        json.dump(jobs, file, indent=2)
        file.write("\n")
    temp_file.replace(JOBS_FILE)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/agent/jobs")
def get_agent_jobs(device_id: str):
    jobs = load_jobs()
    return [
        job
        for job in jobs
        if isinstance(job, dict)
        and job.get("status") == "approved"
        and job.get("device_id") in {device_id, "any"}
    ]


@app.post("/api/agent/jobs")
def create_job(request: CreateJobRequest):
    if request.app not in ALLOWED_APPS:
        raise HTTPException(status_code=400, detail="Unsupported app")

    if request.action not in ALLOWED_ACTIONS:
        raise HTTPException(status_code=400, detail="Unsupported action")

    jobs = load_jobs()
    job = {
        "id": f"job-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}",
        "device_id": request.device_id,
        "app": request.app,
        "action": request.action,
        "status": "approved",
        "created_at": utc_now(),
        "started_at": None,
        "finished_at": None,
        "last_error": None,
        "message": None,
        "attempts": 0,
    }
    jobs.append(job)
    save_jobs(jobs)
    return job


@app.post("/api/agent/jobs/{job_id}/result")
def post_job_result(job_id: str, result: JobResultRequest):
    jobs = load_jobs()
    for job in jobs:
        if isinstance(job, dict) and job.get("id") == job_id:
            update = result.dict(exclude_unset=True)
            job.update(update)
            save_jobs(jobs)
            return job

    raise HTTPException(status_code=404, detail="Job not found")


@app.get("/api/agent/jobs/all")
def get_all_jobs():
    return load_jobs()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8008)
