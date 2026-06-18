import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel


BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR / "mock_backend"
JOBS_FILE = BACKEND_DIR / "jobs.json"
DEVICES_FILE = BACKEND_DIR / "devices.json"
TENANTS_FILE = BACKEND_DIR / "tenants.json"
CATALOG_FILE = BASE_DIR / "app_catalog.json"
ALLOWED_APPS = {"vlc", "chrome", "7zip"}
ALLOWED_ACTIONS = {"install", "uninstall"}
TENANT_STATUSES = {"active", "inactive"}

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


class DeviceCheckInRequest(BaseModel):
    device_id: str
    hostname: Optional[str] = None
    username: Optional[str] = None
    os: Optional[str] = None
    agent_name: str = "Systemo Agent"
    agent_version: str = "0.3.0"
    status: str = "online"


class CreateTenantRequest(BaseModel):
    company_name: str


class UpdateTenantRequest(BaseModel):
    company_name: Optional[str] = None
    status: Optional[str] = None


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def load_catalog():
    if not CATALOG_FILE.exists():
        raise HTTPException(status_code=500, detail="app_catalog.json not found")

    with CATALOG_FILE.open("r", encoding="utf-8") as file:
        catalog = json.load(file)

    if not isinstance(catalog, dict):
        raise HTTPException(status_code=500, detail="app_catalog.json must contain an object")

    return catalog


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


def load_devices():
    BACKEND_DIR.mkdir(parents=True, exist_ok=True)
    if not DEVICES_FILE.exists():
        save_devices([])
        return []

    with DEVICES_FILE.open("r", encoding="utf-8") as file:
        devices = json.load(file)

    if not isinstance(devices, list):
        raise HTTPException(status_code=500, detail="mock_backend/devices.json must contain an array")

    return devices


def save_devices(devices):
    BACKEND_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = DEVICES_FILE.with_suffix(".json.tmp")
    with temp_file.open("w", encoding="utf-8") as file:
        json.dump(devices, file, indent=2)
        file.write("\n")
    temp_file.replace(DEVICES_FILE)


def load_tenants():
    BACKEND_DIR.mkdir(parents=True, exist_ok=True)
    if not TENANTS_FILE.exists():
        save_tenants([])
        return []

    with TENANTS_FILE.open("r", encoding="utf-8") as file:
        tenants = json.load(file)

    if not isinstance(tenants, list):
        raise HTTPException(status_code=500, detail="mock_backend/tenants.json must contain an array")

    return tenants


def save_tenants(tenants):
    BACKEND_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = TENANTS_FILE.with_suffix(".json.tmp")
    with temp_file.open("w", encoding="utf-8") as file:
        json.dump(tenants, file, indent=2)
        file.write("\n")
    temp_file.replace(TENANTS_FILE)


def normalize_company_name(company_name):
    normalized_name = (company_name or "").strip()
    if not normalized_name:
        raise HTTPException(status_code=400, detail="company_name is required")
    return normalized_name


def validate_tenant_status(status):
    if status not in TENANT_STATUSES:
        raise HTTPException(status_code=400, detail="status must be active or inactive")
    return status


def get_dashboard_html():
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Systemo Agent Console</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --line: #d9dee7;
      --text: #17202a;
      --muted: #5f6b7a;
      --accent: #0f766e;
      --accent-dark: #115e59;
      --danger: #b42318;
      --ok: #16703c;
      --warn: #a15c07;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: "Segoe UI", Arial, sans-serif;
      font-size: 14px;
    }

    header {
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }

    .topbar {
      max-width: 1280px;
      margin: 0 auto;
      padding: 18px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      flex-wrap: wrap;
    }

    h1 {
      margin: 0;
      font-size: 24px;
      font-weight: 650;
      letter-spacing: 0;
    }

    main {
      max-width: 1280px;
      margin: 0 auto;
      padding: 24px;
      display: grid;
      gap: 20px;
    }

    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 6px;
      overflow: hidden;
    }

    .section-header {
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }

    h2 {
      margin: 0;
      font-size: 16px;
      font-weight: 650;
      letter-spacing: 0;
    }

    .health {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      white-space: nowrap;
    }

    .dot {
      width: 9px;
      height: 9px;
      border-radius: 50%;
      background: var(--warn);
    }

    .dot.ok {
      background: var(--ok);
    }

    .dot.error {
      background: var(--danger);
    }

    .actions {
      display: flex;
      align-items: end;
      gap: 10px;
      flex-wrap: wrap;
      padding: 16px;
    }

    label {
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 600;
    }

    input,
    select,
    button {
      min-height: 36px;
      border-radius: 6px;
      border: 1px solid var(--line);
      font: inherit;
    }

    input,
    select {
      min-width: 150px;
      background: #ffffff;
      color: var(--text);
      padding: 0 10px;
    }

    button {
      background: var(--accent);
      color: #ffffff;
      border-color: var(--accent);
      padding: 0 14px;
      font-weight: 650;
      cursor: pointer;
    }

    button:hover {
      background: var(--accent-dark);
      border-color: var(--accent-dark);
    }

    .secondary {
      background: #ffffff;
      color: var(--text);
      border-color: var(--line);
    }

    .secondary:hover {
      background: #eef2f6;
      border-color: #c8d0dc;
    }

    .message {
      padding: 0 16px 16px;
      color: var(--muted);
      min-height: 18px;
    }

    .message.error {
      color: var(--danger);
    }

    .table-wrap {
      width: 100%;
      overflow-x: auto;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 920px;
    }

    th,
    td {
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }

    th {
      font-size: 12px;
      color: var(--muted);
      background: #fbfcfd;
      font-weight: 700;
      white-space: nowrap;
    }

    td {
      max-width: 260px;
      overflow-wrap: anywhere;
    }

    tr:last-child td {
      border-bottom: 0;
    }

    .status {
      display: inline-block;
      border-radius: 999px;
      padding: 3px 8px;
      background: #edf2f7;
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
    }

    .status.online,
    .status.success {
      background: #e8f5ee;
      color: var(--ok);
    }

    .status.failed,
    .status.requires_user_action {
      background: #fff0ed;
      color: var(--danger);
    }

    .status.approved,
    .status.installing,
    .status.uninstalling {
      background: #fff7e8;
      color: var(--warn);
    }

    .empty {
      padding: 18px 16px;
      color: var(--muted);
    }

    @media (max-width: 720px) {
      .topbar,
      main {
        padding-left: 14px;
        padding-right: 14px;
      }

      .actions {
        display: grid;
        grid-template-columns: 1fr;
      }

      input,
      select,
      button {
        width: 100%;
      }
    }
  </style>
</head>
<body>
  <header>
    <div class="topbar">
      <h1>Systemo Agent Console</h1>
      <div class="health"><span id="healthDot" class="dot"></span><span id="healthText">Checking backend</span></div>
      <button id="refreshButton" class="secondary" type="button">Refresh</button>
    </div>
  </header>

  <main>
    <section>
      <div class="section-header">
        <h2>Tenants / Companies</h2>
      </div>
      <form id="tenantForm" class="actions">
        <label>
          Company name
          <input id="companyNameInput" name="company_name" type="text" required placeholder="Ybalai Builders">
        </label>
        <button type="submit">Create Tenant</button>
      </form>
      <div id="tenantMessage" class="message"></div>
      <div id="tenantsTable" class="table-wrap"></div>
    </section>

    <section>
      <div class="section-header">
        <h2>Create Job</h2>
      </div>
      <form id="jobForm" class="actions">
        <label>
          Device target
          <select id="deviceSelect" name="device_id"></select>
        </label>
        <label>
          App
          <select id="appSelect" name="app"></select>
        </label>
        <label>
          Action
          <select id="actionSelect" name="action"></select>
        </label>
        <button type="submit">Create Job</button>
      </form>
      <div id="formMessage" class="message"></div>
    </section>

    <section>
      <div class="section-header">
        <h2>Devices</h2>
      </div>
      <div id="devicesTable" class="table-wrap"></div>
    </section>

    <section>
      <div class="section-header">
        <h2>Jobs</h2>
      </div>
      <div id="jobsTable" class="table-wrap"></div>
    </section>
  </main>

  <script>
    const tenantFields = ["tenant_id", "company_name", "status", "created_at", "updated_at"];
    const deviceFields = ["device_id", "hostname", "username", "os", "agent_version", "status", "last_seen_at"];
    const jobFields = ["id", "device_id", "app", "action", "status", "attempts", "message", "started_at", "finished_at"];
    const preferredApps = ["7zip", "vlc", "chrome"];
    let lastDevices = [];
    let lastCatalog = { apps: preferredApps, actions: ["install", "uninstall"] };

    function escapeHtml(value) {
      return String(value ?? "-")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    async function fetchJson(path, options) {
      const response = await fetch(path, options);
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `${response.status} ${response.statusText}`);
      }
      return response.json();
    }

    function setHealth(ok, text) {
      const dot = document.getElementById("healthDot");
      const healthText = document.getElementById("healthText");
      dot.className = ok ? "dot ok" : "dot error";
      healthText.textContent = text;
    }

    function statusCell(value) {
      const safe = escapeHtml(value);
      const className = String(value ?? "").replaceAll(" ", "_");
      return `<span class="status ${escapeHtml(className)}">${safe}</span>`;
    }

    function renderTable(targetId, fields, rows) {
      const target = document.getElementById(targetId);
      if (!rows.length) {
        target.innerHTML = '<div class="empty">No records found.</div>';
        return;
      }

      const header = fields.map((field) => `<th>${escapeHtml(field)}</th>`).join("");
      const body = rows.map((row) => {
        const cells = fields.map((field) => {
          const value = row[field];
          return `<td>${field === "status" ? statusCell(value) : escapeHtml(value)}</td>`;
        }).join("");
        return `<tr>${cells}</tr>`;
      }).join("");
      target.innerHTML = `<table><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table>`;
    }

    function populateSelect(selectId, values) {
      const select = document.getElementById(selectId);
      const currentValue = select.value;
      select.innerHTML = values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join("");
      if (values.includes(currentValue)) {
        select.value = currentValue;
      }
    }

    function refreshFormOptions() {
      const deviceIds = ["any", ...lastDevices.map((device) => device.device_id).filter(Boolean)];
      const apps = preferredApps.filter((app) => lastCatalog.apps.includes(app));
      const extraApps = lastCatalog.apps.filter((app) => !apps.includes(app));
      populateSelect("deviceSelect", [...deviceIds]);
      populateSelect("appSelect", [...apps, ...extraApps]);
      populateSelect("actionSelect", lastCatalog.actions);
    }

    async function refreshAll() {
      try {
        const [health, tenants, devices, jobs, catalog] = await Promise.all([
          fetchJson("/health"),
          fetchJson("/api/admin/tenants"),
          fetchJson("/api/devices"),
          fetchJson("/api/agent/jobs/all"),
          fetchJson("/api/catalog"),
        ]);

        setHealth(health.status === "ok", `Backend ${health.status}`);
        lastDevices = Array.isArray(devices) ? devices : [];
        lastCatalog = catalog;
        refreshFormOptions();
        renderTable("tenantsTable", tenantFields, Array.isArray(tenants) ? tenants : []);
        renderTable("devicesTable", deviceFields, lastDevices);
        renderTable("jobsTable", jobFields, Array.isArray(jobs) ? [...jobs].reverse() : []);
      } catch (error) {
        setHealth(false, "Backend unavailable");
        document.getElementById("formMessage").textContent = error.message;
        document.getElementById("formMessage").className = "message error";
      }
    }

    async function createTenant(event) {
      event.preventDefault();
      const message = document.getElementById("tenantMessage");
      const input = document.getElementById("companyNameInput");
      message.textContent = "";
      message.className = "message";

      try {
        const tenant = await fetchJson("/api/admin/tenants", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ company_name: input.value }),
        });
        message.textContent = `Created tenant ${tenant.tenant_id}`;
        input.value = "";
        await refreshAll();
      } catch (error) {
        message.textContent = error.message;
        message.className = "message error";
      }
    }

    async function createJob(event) {
      event.preventDefault();
      const message = document.getElementById("formMessage");
      message.textContent = "";
      message.className = "message";

      const payload = {
        device_id: document.getElementById("deviceSelect").value,
        app: document.getElementById("appSelect").value,
        action: document.getElementById("actionSelect").value,
      };

      try {
        const job = await fetchJson("/api/agent/jobs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        message.textContent = `Created job ${job.id}`;
        await refreshAll();
      } catch (error) {
        message.textContent = error.message;
        message.className = "message error";
      }
    }

    document.getElementById("refreshButton").addEventListener("click", refreshAll);
    document.getElementById("tenantForm").addEventListener("submit", createTenant);
    document.getElementById("jobForm").addEventListener("submit", createJob);
    refreshAll();
    setInterval(refreshAll, 5000);
  </script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(get_dashboard_html())


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/catalog")
def get_catalog():
    catalog = load_catalog()
    apps = [app_key for app_key in catalog.keys() if app_key in ALLOWED_APPS]
    return {"apps": apps, "actions": sorted(ALLOWED_ACTIONS)}


@app.post("/api/admin/tenants")
def create_tenant(request: CreateTenantRequest):
    tenants = load_tenants()
    now = utc_now()
    tenant = {
        "tenant_id": f"tenant-{uuid.uuid4().hex[:12]}",
        "company_name": normalize_company_name(request.company_name),
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    tenants.append(tenant)
    save_tenants(tenants)
    return tenant


@app.get("/api/admin/tenants")
def get_tenants():
    tenants = load_tenants()
    return sorted(
        tenants,
        key=lambda tenant: tenant.get("created_at", "") if isinstance(tenant, dict) else "",
        reverse=True,
    )


@app.get("/api/admin/tenants/{tenant_id}")
def get_tenant(tenant_id: str):
    tenants = load_tenants()
    for tenant in tenants:
        if isinstance(tenant, dict) and tenant.get("tenant_id") == tenant_id:
            return tenant

    raise HTTPException(status_code=404, detail="Tenant not found")


@app.patch("/api/admin/tenants/{tenant_id}")
def update_tenant(tenant_id: str, request: UpdateTenantRequest):
    tenants = load_tenants()
    for tenant in tenants:
        if isinstance(tenant, dict) and tenant.get("tenant_id") == tenant_id:
            if request.company_name is not None:
                tenant["company_name"] = normalize_company_name(request.company_name)

            if request.status is not None:
                tenant["status"] = validate_tenant_status(request.status)

            tenant["updated_at"] = utc_now()
            save_tenants(tenants)
            return tenant

    raise HTTPException(status_code=404, detail="Tenant not found")


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


@app.delete("/api/agent/jobs/all")
def delete_all_jobs():
    jobs = load_jobs()
    removed_count = len(jobs)
    save_jobs([])
    return {"removed": removed_count}


@app.post("/api/agent/check-in")
def check_in_device(request: DeviceCheckInRequest):
    devices = load_devices()
    now = utc_now()
    device_update = request.dict()
    device_update["last_seen_at"] = now

    for device in devices:
        if isinstance(device, dict) and device.get("device_id") == request.device_id:
            device.update(device_update)
            save_devices(devices)
            return device

    devices.append(device_update)
    save_devices(devices)
    return device_update


@app.get("/api/devices")
def get_devices():
    devices = load_devices()
    return sorted(
        devices,
        key=lambda device: device.get("last_seen_at", "") if isinstance(device, dict) else "",
        reverse=True,
    )


@app.get("/api/devices/{device_id}")
def get_device(device_id: str):
    devices = load_devices()
    for device in devices:
        if isinstance(device, dict) and device.get("device_id") == device_id:
            return device

    raise HTTPException(status_code=404, detail="Device not found")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8008)
