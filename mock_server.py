import json
import re
import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel


BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR / "mock_backend"
JOBS_FILE = BACKEND_DIR / "jobs.json"
DEVICES_FILE = BACKEND_DIR / "devices.json"
TENANTS_FILE = BACKEND_DIR / "tenants.json"
USERS_FILE = BACKEND_DIR / "users.json"
CATALOG_FILE = BASE_DIR / "app_catalog.json"
ALLOWED_APPS = {"vlc", "chrome", "7zip"}
ALLOWED_ACTIONS = {"install", "uninstall"}
TENANT_STATUSES = {"active", "inactive"}
USER_ROLES = {"system_admin", "company_admin", "viewer"}
SESSION_COOKIE_NAME = "systemo_session"
SESSIONS = {}

app = FastAPI(title="Systemo Agent Mock Backend")


class CreateJobRequest(BaseModel):
    device_id: str = "any"
    company_id: Optional[str] = None
    company_name: Optional[str] = None
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
    company_id: Optional[str] = None
    company_name: Optional[str] = None
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


class LoginRequest(BaseModel):
    username: str
    password: str


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

    for tenant in tenants:
        ensure_company_fields(tenant)

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


def slugify_company_name(company_name):
    normalized_name = normalize_company_name(company_name).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized_name).strip("-")
    if not slug:
        raise HTTPException(status_code=400, detail="company_name must contain letters or numbers")
    return slug


def ensure_company_fields(company):
    if not isinstance(company, dict):
        return company

    company_name = company.get("company_name")
    if company_name and not company.get("company_id"):
        company["company_id"] = slugify_company_name(company_name)
    if company.get("company_id") and not company.get("tenant_id"):
        company["tenant_id"] = company.get("company_id")
    if company.get("tenant_id") and not company.get("company_id"):
        company["company_id"] = company.get("tenant_id")
    return company


def find_company_by_id(companies, company_id):
    for company in companies:
        ensure_company_fields(company)
        if isinstance(company, dict) and company.get("company_id") == company_id:
            return company
    return None


def find_company_by_name(companies, company_name):
    company_id = slugify_company_name(company_name)
    return find_company_by_id(companies, company_id)


def get_or_create_company(company_name):
    companies = load_tenants()
    company_id = slugify_company_name(company_name)
    existing_company = find_company_by_id(companies, company_id)
    if existing_company is not None:
        return existing_company

    now = utc_now()
    company = {
        "tenant_id": company_id,
        "company_id": company_id,
        "company_name": normalize_company_name(company_name),
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    companies.append(company)
    save_tenants(companies)
    return company


def get_company_from_request(company_id=None, company_name=None, create_if_missing=False):
    companies = load_tenants()
    if company_id:
        company = find_company_by_id(companies, company_id)
        if company is not None:
            return company

    if company_name:
        if create_if_missing:
            return get_or_create_company(company_name)

        company = find_company_by_name(companies, company_name)
        if company is not None:
            return company

    raise HTTPException(status_code=400, detail="company_id or company_name is required")


def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def save_users(users):
    BACKEND_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = USERS_FILE.with_suffix(".json.tmp")
    with temp_file.open("w", encoding="utf-8") as file:
        json.dump(users, file, indent=2)
        file.write("\n")
    temp_file.replace(USERS_FILE)


def seed_default_users():
    ybalai_company = get_or_create_company("Ybalai Builders")
    now = utc_now()
    users = [
        {
            "user_id": "user-admin",
            "username": "admin",
            "password_hash": hash_password("admin123"),
            "role": "system_admin",
            "company_id": None,
            "created_at": now,
            "updated_at": now,
        },
        {
            "user_id": "user-ybalai-admin",
            "username": "ybalai_admin",
            "password_hash": hash_password("admin123"),
            "role": "company_admin",
            "company_id": ybalai_company.get("company_id"),
            "created_at": now,
            "updated_at": now,
        },
        {
            "user_id": "user-ybalai-viewer",
            "username": "ybalai_viewer",
            "password_hash": hash_password("admin123"),
            "role": "viewer",
            "company_id": ybalai_company.get("company_id"),
            "created_at": now,
            "updated_at": now,
        },
    ]
    save_users(users)
    return users


def load_users():
    BACKEND_DIR.mkdir(parents=True, exist_ok=True)
    if not USERS_FILE.exists():
        return seed_default_users()

    with USERS_FILE.open("r", encoding="utf-8") as file:
        users = json.load(file)

    if not isinstance(users, list):
        raise HTTPException(status_code=500, detail="mock_backend/users.json must contain an array")

    return users


def public_user(user):
    return {
        "user_id": user.get("user_id"),
        "username": user.get("username"),
        "role": user.get("role"),
        "company_id": user.get("company_id"),
    }


def authenticate_user(username, password):
    for user in load_users():
        if user.get("username") == username and user.get("password_hash") == hash_password(password):
            if user.get("role") not in USER_ROLES:
                raise HTTPException(status_code=403, detail="Invalid user role")
            return user
    return None


def get_current_user(request: Request):
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    user_id = SESSIONS.get(session_id)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid session")

    for user in load_users():
        if user.get("user_id") == user_id:
            return user

    raise HTTPException(status_code=401, detail="User not found")


def get_optional_user(request: Request):
    try:
        return get_current_user(request)
    except HTTPException:
        return None


def set_session_cookie(response: Response, user):
    session_id = secrets.token_urlsafe(32)
    SESSIONS[session_id] = user.get("user_id")
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_id,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(request: Request, response: Response):
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        SESSIONS.pop(session_id, None)
    response.delete_cookie(SESSION_COOKIE_NAME)


def require_role(user, allowed_roles):
    if user.get("role") not in allowed_roles:
        raise HTTPException(status_code=403, detail="Forbidden")


def filter_companies_for_user(companies, user):
    if user.get("role") == "system_admin":
        return companies
    return [
        company
        for company in companies
        if isinstance(company, dict) and company.get("company_id") == user.get("company_id")
    ]


def filter_devices_for_user(devices, user):
    if user.get("role") == "system_admin":
        return devices
    return [
        device
        for device in devices
        if isinstance(device, dict) and device.get("company_id") == user.get("company_id")
    ]


def filter_jobs_for_user(jobs, user):
    if user.get("role") == "system_admin":
        return jobs
    return [
        job
        for job in jobs
        if isinstance(job, dict) and job.get("company_id") == user.get("company_id")
    ]


def assert_company_access(user, company_id):
    if user.get("role") == "system_admin":
        return
    if user.get("company_id") != company_id:
        raise HTTPException(status_code=403, detail="Forbidden")


def assert_can_manage_device(user, device):
    require_role(user, {"system_admin", "company_admin"})
    assert_company_access(user, device.get("company_id"))


def assert_can_create_job(user, company_id):
    require_role(user, {"system_admin", "company_admin"})
    assert_company_access(user, company_id)


def validate_tenant_status(status):
    if status not in TENANT_STATUSES:
        raise HTTPException(status_code=400, detail="status must be active or inactive")
    return status


def get_login_html():
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Systemo Agent Login</title>
  <style>
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: #f6f7f9;
      color: #17202a;
      font-family: "Segoe UI", Arial, sans-serif;
    }

    main {
      width: min(420px, calc(100vw - 32px));
      background: #ffffff;
      border: 1px solid #d9dee7;
      border-radius: 6px;
      padding: 24px;
    }

    h1 {
      margin: 0 0 18px;
      font-size: 22px;
      letter-spacing: 0;
    }

    form {
      display: grid;
      gap: 14px;
    }

    label {
      display: grid;
      gap: 6px;
      color: #5f6b7a;
      font-size: 12px;
      font-weight: 650;
    }

    input,
    button {
      min-height: 38px;
      border-radius: 6px;
      border: 1px solid #d9dee7;
      font: inherit;
    }

    input {
      padding: 0 10px;
    }

    button {
      background: #0f766e;
      color: #ffffff;
      border-color: #0f766e;
      font-weight: 700;
      cursor: pointer;
    }

    .error {
      min-height: 18px;
      color: #b42318;
    }
  </style>
</head>
<body>
  <main>
    <h1>Systemo Agent Console</h1>
    <form id="loginForm">
      <label>
        Username
        <input id="username" autocomplete="username" required>
      </label>
      <label>
        Password
        <input id="password" type="password" autocomplete="current-password" required>
      </label>
      <button type="submit">Login</button>
      <div id="message" class="error"></div>
    </form>
  </main>
  <script>
    document.getElementById("loginForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const message = document.getElementById("message");
      message.textContent = "";
      const response = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: document.getElementById("username").value,
          password: document.getElementById("password").value,
        }),
      });
      if (response.ok) {
        window.location.href = "/";
        return;
      }
      message.textContent = "Invalid username or password.";
    });
  </script>
</body>
</html>"""


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

    .userbar {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      color: var(--muted);
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

    .small {
      min-height: 28px;
      padding: 0 8px;
      font-size: 12px;
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
      <div class="userbar">
        <span id="userInfo"></span>
        <button id="refreshButton" class="secondary" type="button">Refresh</button>
        <button id="logoutButton" class="secondary" type="button">Logout</button>
      </div>
    </div>
  </header>

  <main>
    <section>
      <div class="section-header">
        <h2>Companies</h2>
      </div>
      <form id="companyForm" class="actions">
        <label>
          Company name
          <input id="companyNameInput" name="company_name" type="text" required placeholder="Ybalai Builders">
        </label>
        <button type="submit">Create Company</button>
      </form>
      <div id="companyMessage" class="message"></div>
      <div id="companiesTable" class="table-wrap"></div>
    </section>

    <section id="jobSection">
      <div class="section-header">
        <h2>Create Job</h2>
      </div>
      <form id="jobForm" class="actions">
        <label>
          Company
          <select id="companySelect" name="company_id"></select>
        </label>
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
    const companyFields = ["company_id", "company_name", "created_at", "updated_at"];
    const deviceFields = ["company_name", "hostname", "username", "os", "agent_version", "connection_status", "approval_status", "last_seen_at"];
    const jobFields = ["id", "company_name", "device_id", "app", "action", "status", "attempts", "message", "started_at", "finished_at"];
    const preferredApps = ["7zip", "vlc", "chrome"];
    let currentUser = null;
    let lastCompanies = [];
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

    function renderDevices(rows) {
      const target = document.getElementById("devicesTable");
      if (!rows.length) {
        target.innerHTML = '<div class="empty">No records found.</div>';
        return;
      }

      const showActions = currentUser && currentUser.role !== "viewer";
      const columns = showActions ? [...deviceFields, "actions"] : deviceFields;
      const header = columns.map((field) => `<th>${escapeHtml(field)}</th>`).join("");
      const body = rows.map((row) => {
        const cells = deviceFields.map((field) => {
          const value = row[field];
          return `<td>${field.includes("status") ? statusCell(value) : escapeHtml(value)}</td>`;
        }).join("");
        const actions = `<button class="small" type="button" data-approve="${escapeHtml(row.device_id)}">Approve</button> <button class="small secondary" type="button" data-reject="${escapeHtml(row.device_id)}">Reject</button>`;
        return showActions ? `<tr>${cells}<td>${actions}</td></tr>` : `<tr>${cells}</tr>`;
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
      const companySelect = document.getElementById("companySelect");
      const selectedCompanyId = companySelect.value || (lastCompanies[0] && lastCompanies[0].company_id) || "";
      const companyOptions = lastCompanies.map((company) => company.company_id);
      const approvedDevices = lastDevices.filter((device) => {
        return device.company_id === selectedCompanyId && device.approval_status === "approved";
      });
      const deviceIds = ["any", ...approvedDevices.map((device) => device.device_id).filter(Boolean)];
      const apps = preferredApps.filter((app) => lastCatalog.apps.includes(app));
      const extraApps = lastCatalog.apps.filter((app) => !apps.includes(app));
      populateSelect("companySelect", companyOptions);
      if (selectedCompanyId && companyOptions.includes(selectedCompanyId)) {
        companySelect.value = selectedCompanyId;
      }
      populateSelect("deviceSelect", [...deviceIds]);
      populateSelect("appSelect", [...apps, ...extraApps]);
      populateSelect("actionSelect", lastCatalog.actions);
    }

    function applyRoleUi() {
      if (!currentUser) {
        return;
      }
      document.getElementById("userInfo").textContent = `${currentUser.username} (${currentUser.role})`;
      document.getElementById("companyForm").style.display = currentUser.role === "system_admin" ? "" : "none";
      document.getElementById("jobSection").style.display = currentUser.role === "viewer" ? "none" : "";
      document.getElementById("companySelect").disabled = currentUser.role !== "system_admin";
    }

    async function refreshAll() {
      try {
        const [session, health, companies, devices, jobs, catalog] = await Promise.all([
          fetchJson("/dashboard/api/session"),
          fetchJson("/health"),
          fetchJson("/dashboard/api/companies"),
          fetchJson("/dashboard/api/devices"),
          fetchJson("/dashboard/api/jobs"),
          fetchJson("/dashboard/api/catalog"),
        ]);

        currentUser = session.user;
        applyRoleUi();
        setHealth(health.status === "ok", `Backend ${health.status}`);
        lastCompanies = Array.isArray(companies) ? companies : [];
        lastDevices = Array.isArray(devices) ? devices : [];
        lastCatalog = catalog;
        refreshFormOptions();
        renderTable("companiesTable", companyFields, lastCompanies);
        renderDevices(lastDevices);
        renderTable("jobsTable", jobFields, Array.isArray(jobs) ? [...jobs].reverse() : []);
      } catch (error) {
        setHealth(false, "Backend unavailable");
        document.getElementById("formMessage").textContent = error.message;
        document.getElementById("formMessage").className = "message error";
      }
    }

    async function createCompany(event) {
      event.preventDefault();
      const message = document.getElementById("companyMessage");
      const input = document.getElementById("companyNameInput");
      message.textContent = "";
      message.className = "message";

      try {
        const company = await fetchJson("/dashboard/api/companies", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ company_name: input.value }),
        });
        message.textContent = `Created company ${company.company_id}`;
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
        company_id: document.getElementById("companySelect").value,
        device_id: document.getElementById("deviceSelect").value,
        app: document.getElementById("appSelect").value,
        action: document.getElementById("actionSelect").value,
      };

      try {
        const job = await fetchJson("/dashboard/api/jobs", {
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

    async function updateDeviceApproval(deviceId, decision) {
      try {
        await fetchJson(`/dashboard/api/devices/${encodeURIComponent(deviceId)}/${decision}`, { method: "POST" });
        await refreshAll();
      } catch (error) {
        document.getElementById("formMessage").textContent = error.message;
        document.getElementById("formMessage").className = "message error";
      }
    }

    document.getElementById("refreshButton").addEventListener("click", refreshAll);
    document.getElementById("logoutButton").addEventListener("click", async () => {
      await fetch("/logout", { method: "POST" });
      window.location.href = "/login";
    });
    document.getElementById("companySelect").addEventListener("change", refreshFormOptions);
    document.getElementById("companyForm").addEventListener("submit", createCompany);
    document.getElementById("jobForm").addEventListener("submit", createJob);
    document.getElementById("devicesTable").addEventListener("click", (event) => {
      const approveId = event.target.getAttribute("data-approve");
      const rejectId = event.target.getAttribute("data-reject");
      if (approveId) {
        updateDeviceApproval(approveId, "approve");
      }
      if (rejectId) {
        updateDeviceApproval(rejectId, "reject");
      }
    });
    refreshAll();
    setInterval(refreshAll, 5000);
  </script>
</body>
</html>"""


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if get_optional_user(request) is not None:
        return RedirectResponse("/")
    return HTMLResponse(get_login_html())


@app.post("/api/login")
def login(request: LoginRequest):
    user = authenticate_user(request.username, request.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    response = JSONResponse({"user": public_user(user)})
    set_session_cookie(response, user)
    return response


@app.post("/logout")
def logout(request: Request):
    response = JSONResponse({"status": "ok"})
    clear_session_cookie(request, response)
    return response


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    if get_optional_user(request) is None:
        return RedirectResponse("/login")
    return HTMLResponse(get_dashboard_html())


@app.get("/dashboard/api/session")
def dashboard_session(request: Request):
    user = get_current_user(request)
    return {"user": public_user(user)}


@app.get("/dashboard/api/catalog")
def dashboard_catalog(request: Request):
    get_current_user(request)
    return get_catalog()


@app.get("/dashboard/api/companies")
def dashboard_companies(request: Request):
    user = get_current_user(request)
    return filter_companies_for_user(get_companies(), user)


@app.post("/dashboard/api/companies")
def dashboard_create_company(request: Request, payload: CreateTenantRequest):
    user = get_current_user(request)
    require_role(user, {"system_admin"})
    return create_company(payload)


@app.get("/dashboard/api/devices")
def dashboard_devices(request: Request):
    user = get_current_user(request)
    return filter_devices_for_user(get_devices(), user)


@app.post("/dashboard/api/devices/{device_id}/approve")
def dashboard_approve_device(request: Request, device_id: str):
    user = get_current_user(request)
    device = get_device(device_id)
    assert_can_manage_device(user, device)
    return approve_device(device_id)


@app.post("/dashboard/api/devices/{device_id}/reject")
def dashboard_reject_device(request: Request, device_id: str):
    user = get_current_user(request)
    device = get_device(device_id)
    assert_can_manage_device(user, device)
    return reject_device(device_id)


@app.get("/dashboard/api/jobs")
def dashboard_jobs(request: Request):
    user = get_current_user(request)
    return filter_jobs_for_user(get_all_jobs(), user)


@app.post("/dashboard/api/jobs")
def dashboard_create_job(request: Request, payload: CreateJobRequest):
    user = get_current_user(request)
    if payload.device_id != "any":
        target_device = get_device(payload.device_id)
        company_id = target_device.get("company_id")
    else:
        company_id = payload.company_id or user.get("company_id")
    if user.get("role") != "system_admin":
        payload.company_id = user.get("company_id")
        payload.company_name = None
    if not company_id:
        raise HTTPException(status_code=400, detail="company_id is required")
    assert_can_create_job(user, company_id)
    return create_job(payload)


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
    return get_or_create_company(request.company_name)


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
        if isinstance(tenant, dict) and tenant.get("company_id") == tenant_id:
            return tenant

    raise HTTPException(status_code=404, detail="Tenant not found")


@app.patch("/api/admin/tenants/{tenant_id}")
def update_tenant(tenant_id: str, request: UpdateTenantRequest):
    tenants = load_tenants()
    for tenant in tenants:
        if isinstance(tenant, dict) and (
            tenant.get("tenant_id") == tenant_id
            or tenant.get("company_id") == tenant_id
        ):
            if request.company_name is not None:
                tenant["company_name"] = normalize_company_name(request.company_name)

            if request.status is not None:
                tenant["status"] = validate_tenant_status(request.status)

            tenant["updated_at"] = utc_now()
            save_tenants(tenants)
            return tenant

    raise HTTPException(status_code=404, detail="Tenant not found")


@app.post("/api/admin/companies")
def create_company(request: CreateTenantRequest):
    return get_or_create_company(request.company_name)


@app.get("/api/admin/companies")
def get_companies():
    return get_tenants()


@app.get("/api/admin/companies/{company_id}")
def get_company(company_id: str):
    tenants = load_tenants()
    company = find_company_by_id(tenants, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@app.get("/api/agent/jobs")
def get_agent_jobs(device_id: str):
    devices = load_devices()
    device = None
    for candidate in devices:
        if isinstance(candidate, dict) and candidate.get("device_id") == device_id:
            device = candidate
            break

    if device is None or device.get("approval_status") != "approved":
        return []

    company_id = device.get("company_id")
    if not company_id:
        return []

    jobs = load_jobs()
    return [
        job
        for job in jobs
        if isinstance(job, dict)
        and job.get("status") == "approved"
        and job.get("company_id") == company_id
        and job.get("device_id") in {device_id, "any"}
    ]


@app.post("/api/agent/jobs")
def create_job(request: CreateJobRequest):
    if request.app not in ALLOWED_APPS:
        raise HTTPException(status_code=400, detail="Unsupported app")

    if request.action not in ALLOWED_ACTIONS:
        raise HTTPException(status_code=400, detail="Unsupported action")

    devices = load_devices()
    target_device = None
    if request.device_id != "any":
        for device in devices:
            if isinstance(device, dict) and device.get("device_id") == request.device_id:
                target_device = device
                break
        if target_device is None:
            raise HTTPException(status_code=404, detail="Target device not found")
        company_id = target_device.get("company_id")
        company_name = target_device.get("company_name")
    else:
        company = get_company_from_request(
            company_id=request.company_id,
            company_name=request.company_name,
            create_if_missing=False,
        )
        company_id = company.get("company_id")
        company_name = company.get("company_name")

    if not company_id:
        raise HTTPException(status_code=400, detail="Job company could not be resolved")

    jobs = load_jobs()
    job = {
        "id": f"job-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}",
        "company_id": company_id,
        "company_name": company_name,
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
    company = get_company_from_request(
        company_id=request.company_id,
        company_name=request.company_name,
        create_if_missing=True,
    )
    device_update = request.dict()
    device_update["company_id"] = company.get("company_id")
    device_update["company_name"] = company.get("company_name")
    device_update["connection_status"] = request.status
    device_update["last_seen_at"] = now

    for device in devices:
        if isinstance(device, dict) and device.get("device_id") == request.device_id:
            approval_status = device.get("approval_status") or "pending_approval"
            device.update(device_update)
            device["approval_status"] = approval_status
            save_devices(devices)
            return device

    device_update["approval_status"] = "pending_approval"
    devices.append(device_update)
    save_devices(devices)
    return device_update


@app.get("/api/devices")
def get_devices(company_id: Optional[str] = None, company_name: Optional[str] = None):
    devices = load_devices()
    if company_name and not company_id:
        company_id = slugify_company_name(company_name)
    if company_id:
        devices = [
            device
            for device in devices
            if isinstance(device, dict) and device.get("company_id") == company_id
        ]
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


@app.post("/api/admin/devices/{device_id}/approve")
def approve_device(device_id: str):
    devices = load_devices()
    for device in devices:
        if isinstance(device, dict) and device.get("device_id") == device_id:
            device["approval_status"] = "approved"
            save_devices(devices)
            return device

    raise HTTPException(status_code=404, detail="Device not found")


@app.post("/api/admin/devices/{device_id}/reject")
def reject_device(device_id: str):
    devices = load_devices()
    for device in devices:
        if isinstance(device, dict) and device.get("device_id") == device_id:
            device["approval_status"] = "rejected"
            save_devices(devices)
            return device

    raise HTTPException(status_code=404, detail="Device not found")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8008)
