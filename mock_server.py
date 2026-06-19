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
from pydantic import BaseModel, Field

from database import init_database, session_scope
from models import (
    AppCatalog,
    AppRequest,
    AuditLog,
    Company,
    Device,
    DeviceInstalledApp,
    InventoryScanRun,
    Job,
    User,
)


BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR / "mock_backend"
JOBS_FILE = BACKEND_DIR / "jobs.json"
DEVICES_FILE = BACKEND_DIR / "devices.json"
TENANTS_FILE = BACKEND_DIR / "tenants.json"
USERS_FILE = BACKEND_DIR / "users.json"
APP_REQUESTS_FILE = BACKEND_DIR / "app_requests.json"
AUDIT_LOGS_FILE = BACKEND_DIR / "audit_logs.json"
CATALOG_FILE = BASE_DIR / "app_catalog.json"
ALLOWED_APPS = {"vlc", "chrome", "7zip"}
ALLOWED_ACTIONS = {"install", "uninstall"}
TENANT_STATUSES = {"active", "inactive"}
USER_ROLES = {"system_admin", "company_admin", "viewer"}
APP_REQUEST_STATUSES = {"pending", "approved", "rejected", "converted_to_job"}
SESSION_COOKIE_NAME = "systemo_session"
SESSIONS = {}

init_database()
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


class CreateAppRequestRequest(BaseModel):
    device_id: str = "any"
    target_device_id: Optional[str] = None
    company_id: Optional[str] = None
    company_name: Optional[str] = None
    app: str
    action: str = "install"
    reason: Optional[str] = None


class AppRequestDecisionRequest(BaseModel):
    reason: Optional[str] = None


class CreateAppCatalogRequest(BaseModel):
    app_key: str
    display_name: str
    winget_id: str
    description: Optional[str] = None
    supported_actions: list[str] = Field(default_factory=lambda: ["install", "uninstall"])
    install_command_template: Optional[str] = None
    uninstall_command_template: Optional[str] = None
    detection_method: str = "winget"
    detection_id: Optional[str] = None
    silent_install_supported: bool = True
    silent_uninstall_supported: bool = True
    enabled: bool = True
    scope: str = "global"
    company_id: Optional[str] = None


class UpdateAppCatalogRequest(BaseModel):
    display_name: Optional[str] = None
    winget_id: Optional[str] = None
    description: Optional[str] = None
    supported_actions: Optional[list[str]] = None
    install_command_template: Optional[str] = None
    uninstall_command_template: Optional[str] = None
    detection_method: Optional[str] = None
    detection_id: Optional[str] = None
    silent_install_supported: Optional[bool] = None
    silent_uninstall_supported: Optional[bool] = None
    enabled: Optional[bool] = None
    scope: Optional[str] = None
    company_id: Optional[str] = None


class InventoryAppRequest(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    detected_name: Optional[str] = None
    id: Optional[str] = None
    detected_id: Optional[str] = None
    version: Optional[str] = None
    source: Optional[str] = None
    install_location: Optional[str] = None
    detection_method: str = "winget"


class InventoryReportRequest(BaseModel):
    device_id: str
    company_id: Optional[str] = None
    company_name: Optional[str] = None
    scan_id: Optional[str] = None
    status: str = "success"
    error_message: Optional[str] = None
    apps: list[InventoryAppRequest] = Field(default_factory=list)


AUDIT_JOB_RESULT_EVENTS = {
    "success": "JOB_SUCCESS",
    "failed": "JOB_FAILED",
    "requires_user_action": "JOB_FAILED",
    "skipped": "JOB_SKIPPED",
}
AUDIT_EVENT_ACTIONS = {
    "APP_REQUEST_APPROVED": "ticket_approved",
    "APP_REQUEST_CREATED": "ticket_created",
    "APP_REQUEST_REJECTED": "ticket_rejected",
    "DEVICE_APPROVED": "device_approved",
    "DEVICE_ENROLLED": "device_enrolled",
    "DEVICE_HEARTBEAT_FIRST_SEEN": "device_check_in",
    "DEVICE_REJECTED": "device_rejected",
    "JOB_CREATED": "job_created",
    "JOB_FAILED": "job_failed",
    "JOB_SKIPPED": "job_skipped",
    "JOB_STARTED": "job_started",
    "JOB_SUCCESS": "job_success",
    "TENANT_CREATED": "tenant_created",
    "TENANT_UPDATED": "tenant_updated",
    "USER_LOGIN_FAILED": "user_login_failed",
    "USER_LOGIN_SUCCESS": "user_login_success",
    "USER_LOGOUT": "user_logout",
}

DEFAULT_APP_CATALOG = [
    {
        "app_id": "global-7zip",
        "display_name": "7-Zip",
        "app_key": "7zip",
        "winget_id": "7zip.7zip",
        "description": "File archiver",
        "supported_actions": ["install", "uninstall"],
        "detection_method": "winget",
        "detection_id": "7zip.7zip",
        "silent_install_supported": True,
        "silent_uninstall_supported": True,
        "enabled": True,
        "scope": "global",
        "company_id": None,
    },
    {
        "app_id": "global-vlc",
        "display_name": "VLC Media Player",
        "app_key": "vlc",
        "winget_id": "VideoLAN.VLC",
        "description": "Media player",
        "supported_actions": ["install", "uninstall"],
        "detection_method": "winget",
        "detection_id": "VideoLAN.VLC",
        "silent_install_supported": True,
        "silent_uninstall_supported": False,
        "enabled": True,
        "scope": "global",
        "company_id": None,
    },
    {
        "app_id": "global-chrome",
        "display_name": "Google Chrome",
        "app_key": "chrome",
        "winget_id": "Google.Chrome",
        "description": "Web browser",
        "supported_actions": ["install", "uninstall"],
        "detection_method": "winget",
        "detection_id": "Google.Chrome",
        "silent_install_supported": True,
        "silent_uninstall_supported": True,
        "enabled": True,
        "scope": "global",
        "company_id": None,
    },
]


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


def normalize_app_key(app_key):
    normalized_key = (app_key or "").strip().lower()
    normalized_key = re.sub(r"[^a-z0-9]+", "-", normalized_key).strip("-")
    if not normalized_key:
        raise HTTPException(status_code=400, detail="app_key is required")
    return normalized_key


def validate_catalog_scope(scope):
    if scope not in {"global", "company"}:
        raise HTTPException(status_code=400, detail="scope must be global or company")
    return scope


def validate_supported_actions(supported_actions):
    if not isinstance(supported_actions, list) or not supported_actions:
        raise HTTPException(status_code=400, detail="supported_actions must include install and/or uninstall")
    normalized_actions = []
    for action in supported_actions:
        if action not in ALLOWED_ACTIONS:
            raise HTTPException(status_code=400, detail=f"Unsupported action: {action}")
        if action not in normalized_actions:
            normalized_actions.append(action)
    return normalized_actions


def app_catalog_to_agent_snapshot(app_catalog_entry):
    return {
        "app_key": app_catalog_entry.get("app_key"),
        "display_name": app_catalog_entry.get("display_name"),
        "winget_id": app_catalog_entry.get("winget_id"),
        "detection_id": app_catalog_entry.get("detection_id"),
        "detection_method": app_catalog_entry.get("detection_method") or "winget",
    }


def load_app_catalog_entries():
    with session_scope() as session:
        return [
            app_entry.to_dict()
            for app_entry in session.query(AppCatalog).order_by(AppCatalog.display_name.asc()).all()
        ]


def save_app_catalog_entries(entries):
    if not isinstance(entries, list):
        raise HTTPException(status_code=500, detail="app_catalog entries must contain an array")

    now = utc_now()
    incoming_ids = {
        entry.get("app_id")
        for entry in entries
        if isinstance(entry, dict) and entry.get("app_id")
    }
    with session_scope() as session:
        for existing_entry in session.query(AppCatalog).all():
            if existing_entry.app_id not in incoming_ids:
                session.delete(existing_entry)

        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("app_id"):
                continue
            row = session.get(AppCatalog, entry.get("app_id"))
            if row is None:
                row = AppCatalog(
                    app_id=entry.get("app_id"),
                    app_key=normalize_app_key(entry.get("app_key")),
                    display_name=entry.get("display_name"),
                    winget_id=entry.get("winget_id"),
                    supported_actions_json=json.dumps(validate_supported_actions(entry.get("supported_actions"))),
                    detection_id=entry.get("detection_id") or entry.get("winget_id"),
                    created_at=entry.get("created_at") or now,
                    updated_at=entry.get("updated_at") or now,
                )
                session.add(row)

            row.app_key = normalize_app_key(entry.get("app_key"))
            row.display_name = entry.get("display_name")
            row.winget_id = entry.get("winget_id")
            row.description = entry.get("description")
            row.supported_actions_json = json.dumps(validate_supported_actions(entry.get("supported_actions")))
            row.install_command_template = entry.get("install_command_template")
            row.uninstall_command_template = entry.get("uninstall_command_template")
            row.detection_method = entry.get("detection_method") or "winget"
            row.detection_id = entry.get("detection_id") or entry.get("winget_id")
            row.silent_install_supported = bool(entry.get("silent_install_supported", True))
            row.silent_uninstall_supported = bool(entry.get("silent_uninstall_supported", True))
            row.enabled = bool(entry.get("enabled", True))
            row.scope = validate_catalog_scope(entry.get("scope") or "global")
            row.company_id = entry.get("company_id") if row.scope == "company" else None
            row.created_by_user_id = entry.get("created_by_user_id")
            row.created_by_username = entry.get("created_by_username")
            row.created_at = entry.get("created_at") or row.created_at or now
            row.updated_at = entry.get("updated_at") or now


def seed_default_app_catalog():
    with session_scope() as session:
        existing_count = session.query(AppCatalog).count()
    if existing_count:
        return

    now = utc_now()
    entries = []
    for entry in DEFAULT_APP_CATALOG:
        entries.append(
            {
                **entry,
                "created_at": now,
                "updated_at": now,
                "created_by_user_id": None,
                "created_by_username": None,
            }
        )
    save_app_catalog_entries(entries)


def catalog_entry_visible_to_user(entry, user):
    if entry.get("scope") == "global":
        return True
    if user.get("role") == "system_admin":
        return True
    return entry.get("company_id") == user.get("company_id")


def filter_catalog_for_user(entries, user, enabled_only=False):
    return [
        entry
        for entry in entries
        if isinstance(entry, dict)
        and catalog_entry_visible_to_user(entry, user)
        and (not enabled_only or entry.get("enabled"))
    ]


def find_catalog_entry(app_id):
    for entry in load_app_catalog_entries():
        if isinstance(entry, dict) and entry.get("app_id") == app_id:
            return entry
    raise HTTPException(status_code=404, detail="App catalog entry not found")


def get_available_catalog_entry(app_key, action, company_id=None, user=None):
    normalized_key = normalize_app_key(app_key)
    entries = load_app_catalog_entries()
    if user is not None:
        entries = filter_catalog_for_user(entries, user, enabled_only=True)
    else:
        entries = [
            entry
            for entry in entries
            if isinstance(entry, dict)
            and entry.get("enabled")
            and (entry.get("scope") == "global" or entry.get("company_id") == company_id)
        ]

    matching_entries = [
        entry
        for entry in entries
        if entry.get("app_key") == normalized_key
        and action in (entry.get("supported_actions") or [])
    ]
    matching_entries.sort(key=lambda entry: 0 if entry.get("company_id") == company_id else 1)
    if not matching_entries:
        log_audit(
            "APP_CATALOG_VALIDATION_FAILED",
            f"App catalog validation failed for {normalized_key} {action}",
            company_id=company_id,
            actor=user,
            target_type="app_catalog",
            target_label=normalized_key,
            metadata={"app": normalized_key, "action": action},
        )
        raise HTTPException(status_code=400, detail="App is not enabled or action is not allowed")
    return matching_entries[0]


def assert_can_manage_app_catalog(user, entry=None):
    require_role(user, {"system_admin"})


def build_catalog_entry_from_payload(payload, user):
    scope = validate_catalog_scope(payload.scope or "global")
    company_id = payload.company_id if scope == "company" else None
    if scope == "company":
        if not company_id:
            raise HTTPException(status_code=400, detail="company_id is required for company-scoped apps")
        get_company(company_id)

    app_key = normalize_app_key(payload.app_key)
    app_id = f"global-{app_key}" if scope == "global" else f"company-{company_id}-{app_key}"
    return {
        "app_id": app_id,
        "display_name": payload.display_name,
        "app_key": app_key,
        "winget_id": payload.winget_id,
        "description": payload.description,
        "supported_actions": validate_supported_actions(payload.supported_actions),
        "install_command_template": payload.install_command_template,
        "uninstall_command_template": payload.uninstall_command_template,
        "detection_method": payload.detection_method or "winget",
        "detection_id": payload.detection_id or payload.winget_id,
        "silent_install_supported": payload.silent_install_supported,
        "silent_uninstall_supported": payload.silent_uninstall_supported,
        "enabled": payload.enabled,
        "scope": scope,
        "company_id": company_id,
        "created_by_user_id": user.get("user_id"),
        "created_by_username": user.get("username"),
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }


def create_app_catalog_entry(payload, user):
    assert_can_manage_app_catalog(user)
    entry = build_catalog_entry_from_payload(payload, user)
    entries = load_app_catalog_entries()
    if any(existing.get("app_key") == entry.get("app_key") for existing in entries):
        raise HTTPException(status_code=400, detail="app_key already exists")
    entries.append(entry)
    save_app_catalog_entries(entries)
    log_audit(
        "APP_CATALOG_CREATED",
        f"App catalog entry created for {entry.get('display_name')}",
        company_id=entry.get("company_id"),
        actor=user,
        target_type="app_catalog",
        target_label=entry.get("app_key"),
        metadata={"app_id": entry.get("app_id"), "scope": entry.get("scope")},
    )
    return entry


def update_app_catalog_entry(app_id, payload, user):
    entries = load_app_catalog_entries()
    entry = None
    for candidate in entries:
        if candidate.get("app_id") == app_id:
            entry = candidate
            break
    if entry is None:
        raise HTTPException(status_code=404, detail="App catalog entry not found")
    assert_can_manage_app_catalog(user, entry)

    update = payload.dict(exclude_unset=True)
    if "app_key" in update:
        raise HTTPException(status_code=400, detail="app_key cannot be changed")
    if "scope" in update:
        entry["scope"] = validate_catalog_scope(update["scope"])
    if entry.get("scope") == "company":
        company_id = update.get("company_id", entry.get("company_id"))
        if not company_id:
            raise HTTPException(status_code=400, detail="company_id is required for company-scoped apps")
        get_company(company_id)
        entry["company_id"] = company_id
    else:
        entry["company_id"] = None

    for field in [
        "display_name",
        "winget_id",
        "description",
        "install_command_template",
        "uninstall_command_template",
        "detection_method",
        "detection_id",
        "silent_install_supported",
        "silent_uninstall_supported",
        "enabled",
    ]:
        if field in update:
            entry[field] = update[field]
    if "supported_actions" in update:
        entry["supported_actions"] = validate_supported_actions(update["supported_actions"])
    if not entry.get("detection_id"):
        entry["detection_id"] = entry.get("winget_id")
    entry["updated_at"] = utc_now()
    save_app_catalog_entries(entries)
    log_audit(
        "APP_CATALOG_UPDATED",
        f"App catalog entry updated for {entry.get('display_name')}",
        company_id=entry.get("company_id"),
        actor=user,
        target_type="app_catalog",
        target_label=entry.get("app_key"),
        metadata={"app_id": entry.get("app_id")},
    )
    return entry


def set_app_catalog_enabled(app_id, enabled, user):
    entries = load_app_catalog_entries()
    for entry in entries:
        if entry.get("app_id") == app_id:
            assert_can_manage_app_catalog(user, entry)
            entry["enabled"] = enabled
            entry["updated_at"] = utc_now()
            save_app_catalog_entries(entries)
            event_type = "APP_CATALOG_ENABLED" if enabled else "APP_CATALOG_DISABLED"
            log_audit(
                event_type,
                f"App catalog entry {'enabled' if enabled else 'disabled'} for {entry.get('display_name')}",
                company_id=entry.get("company_id"),
                actor=user,
                target_type="app_catalog",
                target_label=entry.get("app_key"),
                metadata={"app_id": entry.get("app_id")},
            )
            return entry
    raise HTTPException(status_code=404, detail="App catalog entry not found")


def normalize_inventory_identifier(value):
    return (value or "").strip().lower()


def match_inventory_app_to_catalog(installed_app, catalog_entries):
    detected_id = normalize_inventory_identifier(installed_app.get("detected_id") or installed_app.get("id"))
    detected_name = normalize_inventory_identifier(installed_app.get("detected_name") or installed_app.get("name"))

    for entry in catalog_entries:
        candidate_ids = {
            normalize_inventory_identifier(entry.get("detection_id")),
            normalize_inventory_identifier(entry.get("winget_id")),
            normalize_inventory_identifier(entry.get("app_key")),
        }
        if detected_id and detected_id in candidate_ids:
            return entry

    for entry in catalog_entries:
        app_key = normalize_inventory_identifier(entry.get("app_key"))
        display_name = normalize_inventory_identifier(entry.get("display_name"))
        if detected_name and (detected_name == app_key or detected_name == display_name):
            return entry

    return None


def get_inventory_rows(company_id=None, device_id=None):
    with session_scope() as session:
        query = session.query(DeviceInstalledApp)
        if company_id:
            query = query.filter(DeviceInstalledApp.company_id == company_id)
        if device_id:
            query = query.filter(DeviceInstalledApp.device_id == device_id)
        return [row.to_dict() for row in query.order_by(DeviceInstalledApp.display_name.asc()).all()]


def get_inventory_scan_rows(company_id=None, device_id=None):
    with session_scope() as session:
        query = session.query(InventoryScanRun)
        if company_id:
            query = query.filter(InventoryScanRun.company_id == company_id)
        if device_id:
            query = query.filter(InventoryScanRun.device_id == device_id)
        return [row.to_dict() for row in query.order_by(InventoryScanRun.started_at.desc()).all()]


def get_latest_inventory_scan(device_id):
    scans = get_inventory_scan_rows(device_id=device_id)
    return scans[0] if scans else None


def enrich_devices_with_inventory(devices):
    with session_scope() as session:
        for device in devices:
            if not isinstance(device, dict):
                continue
            device_id = device.get("device_id")
            if not device_id:
                continue
            device["installed_apps_count"] = session.query(DeviceInstalledApp).filter(
                DeviceInstalledApp.device_id == device_id
            ).count()
            latest_scan = session.query(InventoryScanRun).filter(
                InventoryScanRun.device_id == device_id
            ).order_by(InventoryScanRun.started_at.desc()).first()
            device["last_inventory_scan_at"] = latest_scan.finished_at if latest_scan else None
            device["last_inventory_status"] = latest_scan.status if latest_scan else None
    return devices


def submit_device_inventory(payload):
    device = get_device(payload.device_id)
    if payload.company_id and payload.company_id != device.get("company_id"):
        raise HTTPException(status_code=403, detail="Device company does not match inventory payload")
    if payload.company_name and slugify_company_name(payload.company_name) != device.get("company_id"):
        raise HTTPException(status_code=403, detail="Device company does not match inventory payload")

    company_id = device.get("company_id")
    company_name = device.get("company_name")
    scan_id = payload.scan_id or f"scan-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    started_at = utc_now()
    log_audit(
        "INVENTORY_SCAN_STARTED",
        f"Inventory scan started for device {payload.device_id}",
        company_id=company_id,
        company_name=company_name,
        device_id=payload.device_id,
        target_type="device",
        target_label=device.get("hostname") or payload.device_id,
        metadata={"scan_id": scan_id},
    )

    catalog_entries = load_app_catalog_entries()
    now = utc_now()
    installed_rows = []
    catalog_matches_count = 0
    for app in payload.apps:
        app_data = app.dict()
        detected_name = app_data.get("detected_name") or app_data.get("name") or app_data.get("display_name") or "-"
        detected_id = app_data.get("detected_id") or app_data.get("id")
        match = match_inventory_app_to_catalog(
            {"detected_id": detected_id, "detected_name": detected_name},
            catalog_entries,
        )
        if match:
            catalog_matches_count += 1
        installed_rows.append(
            {
                "company_id": company_id,
                "device_id": payload.device_id,
                "app_key": match.get("app_key") if match else None,
                "catalog_app_id": match.get("app_id") if match else None,
                "display_name": match.get("display_name") if match else detected_name,
                "detected_name": detected_name,
                "detected_id": detected_id,
                "version": app_data.get("version"),
                "source": app_data.get("source"),
                "install_location": app_data.get("install_location"),
                "detection_method": app_data.get("detection_method") or "winget",
                "is_catalog_match": bool(match),
                "last_seen_at": now,
                "created_at": now,
                "updated_at": now,
            }
        )

    status = payload.status if payload.status in {"started", "success", "failed"} else "success"
    error_message = payload.error_message
    with session_scope() as session:
        if status != "failed":
            session.query(DeviceInstalledApp).filter(
                DeviceInstalledApp.device_id == payload.device_id
            ).delete()
            for row_data in installed_rows:
                session.add(DeviceInstalledApp(**row_data))

        existing_scan = session.get(InventoryScanRun, scan_id)
        if existing_scan is None:
            existing_scan = InventoryScanRun(
                scan_id=scan_id,
                company_id=company_id,
                device_id=payload.device_id,
                status=status,
                started_at=started_at,
            )
            session.add(existing_scan)
        existing_scan.status = status
        existing_scan.apps_found_count = len(installed_rows)
        existing_scan.catalog_matches_count = catalog_matches_count
        existing_scan.finished_at = now
        existing_scan.error_message = error_message

        device_row = session.get(Device, payload.device_id)
        if device_row is not None:
            device_row.last_seen_at = now
            device_row.updated_at = now

    if status == "failed":
        log_audit(
            "INVENTORY_SCAN_FAILED",
            f"Inventory scan failed for device {payload.device_id}",
            company_id=company_id,
            company_name=company_name,
            device_id=payload.device_id,
            target_type="device",
            target_label=device.get("hostname") or payload.device_id,
            metadata={"scan_id": scan_id, "error_message": error_message},
        )
    else:
        log_audit(
            "INVENTORY_SCAN_SUCCESS",
            f"Inventory scan found {len(installed_rows)} app(s)",
            company_id=company_id,
            company_name=company_name,
            device_id=payload.device_id,
            target_type="device",
            target_label=device.get("hostname") or payload.device_id,
            metadata={"scan_id": scan_id, "catalog_matches_count": catalog_matches_count},
        )
        log_audit(
            "INVENTORY_UPDATED",
            f"Inventory updated for device {payload.device_id}",
            company_id=company_id,
            company_name=company_name,
            device_id=payload.device_id,
            target_type="device",
            target_label=device.get("hostname") or payload.device_id,
            metadata={"scan_id": scan_id, "apps_found_count": len(installed_rows)},
        )

    return {
        "scan_id": scan_id,
        "status": status,
        "apps_found_count": len(installed_rows),
        "catalog_matches_count": catalog_matches_count,
        "device_id": payload.device_id,
        "company_id": company_id,
    }


def get_default_company_for_legacy_data():
    with session_scope() as session:
        company = session.query(Company).order_by(Company.created_at.asc()).first()
        if company is None:
            return None, None
        return company.company_id, company.company_name


def load_jobs():
    with session_scope() as session:
        return [
            job.to_dict()
            for job in session.query(Job).order_by(Job.created_at.asc()).all()
        ]


def save_jobs(jobs):
    if not isinstance(jobs, list):
        raise HTTPException(status_code=500, detail="jobs must contain an array")

    now = utc_now()
    incoming_ids = {
        job.get("id") or job.get("job_id")
        for job in jobs
        if isinstance(job, dict) and (job.get("id") or job.get("job_id"))
    }
    fallback_company_id, fallback_company_name = get_default_company_for_legacy_data()
    with session_scope() as session:
        for existing_job in session.query(Job).all():
            if existing_job.job_id not in incoming_ids:
                session.delete(existing_job)

        for job in jobs:
            if not isinstance(job, dict):
                continue
            job_id = job.get("id") or job.get("job_id")
            if not job_id:
                continue
            company_id = job.get("company_id") or fallback_company_id
            company_name = job.get("company_name") or fallback_company_name
            if not company_id or not company_name:
                continue
            row = session.get(Job, job_id)
            if row is None:
                row = Job(
                    job_id=job_id,
                    company_id=company_id,
                    company_name=company_name,
                    device_id=job.get("device_id") or "any",
                    app=job.get("app"),
                    action=job.get("action"),
                    status=job.get("status") or "approved",
                    created_at=job.get("created_at") or now,
                    updated_at=job.get("updated_at") or now,
                )
                session.add(row)

            row.company_id = company_id
            row.company_name = company_name
            row.device_id = job.get("device_id") or "any"
            row.app = job.get("app")
            row.app_key = job.get("app_key") or job.get("app")
            row.display_name = job.get("display_name")
            row.winget_id = job.get("winget_id")
            row.detection_id = job.get("detection_id")
            row.action = job.get("action")
            row.status = job.get("status") or row.status
            row.attempts = int(job.get("attempts") or 0)
            row.message = job.get("message")
            row.last_error = job.get("last_error")
            row.created_by_user_id = job.get("created_by_user_id")
            row.created_by_username = job.get("created_by_username")
            row.approved_by_user_id = job.get("approved_by_user_id")
            row.approved_by_username = job.get("approved_by_username")
            row.request_id = job.get("request_id") or job.get("source_request_id")
            row.started_at = job.get("started_at")
            row.finished_at = job.get("finished_at")
            row.audit_started_at = job.get("audit_started_at")
            row.audit_result_status = job.get("audit_result_status")
            row.created_at = job.get("created_at") or row.created_at or now
            row.updated_at = now


def load_app_requests():
    with session_scope() as session:
        return [
            app_request.to_dict()
            for app_request in session.query(AppRequest).order_by(AppRequest.created_at.asc()).all()
        ]


def save_app_requests(app_requests):
    if not isinstance(app_requests, list):
        raise HTTPException(status_code=500, detail="app_requests must contain an array")

    now = utc_now()
    incoming_ids = {
        app_request.get("request_id")
        for app_request in app_requests
        if isinstance(app_request, dict) and app_request.get("request_id")
    }
    with session_scope() as session:
        for existing_request in session.query(AppRequest).all():
            if existing_request.request_id not in incoming_ids:
                session.delete(existing_request)

        for app_request in app_requests:
            if not isinstance(app_request, dict) or not app_request.get("request_id"):
                continue
            row = session.get(AppRequest, app_request.get("request_id"))
            if row is None:
                row = AppRequest(
                    request_id=app_request.get("request_id"),
                    company_id=app_request.get("company_id"),
                    company_name=app_request.get("company_name"),
                    target_type=app_request.get("target_type"),
                    app=app_request.get("app"),
                    action=app_request.get("action"),
                    status=app_request.get("status"),
                    created_at=app_request.get("created_at") or now,
                    updated_at=app_request.get("updated_at") or now,
                )
                session.add(row)

            row.company_id = app_request.get("company_id")
            row.company_name = app_request.get("company_name")
            row.device_id = app_request.get("device_id")
            row.target_device_id = app_request.get("target_device_id") or "any"
            row.target_type = app_request.get("target_type")
            row.app = app_request.get("app")
            row.action = app_request.get("action")
            row.requested_by_user_id = app_request.get("requested_by_user_id")
            row.requested_by_username = app_request.get("requested_by_username")
            row.status = app_request.get("status")
            row.approved_by_user_id = app_request.get("approved_by_user_id")
            row.approved_by_username = app_request.get("approved_by_username")
            row.rejected_by_user_id = app_request.get("rejected_by_user_id")
            row.rejected_by_username = app_request.get("rejected_by_username")
            row.linked_job_id = app_request.get("linked_job_id")
            row.reason = app_request.get("reason")
            row.created_at = app_request.get("created_at") or row.created_at or now
            row.updated_at = app_request.get("updated_at") or now


def load_audit_logs():
    with session_scope() as session:
        return [
            audit_log.to_dict()
            for audit_log in session.query(AuditLog).order_by(AuditLog.created_at.asc()).all()
        ]


def save_audit_logs(audit_logs):
    if not isinstance(audit_logs, list):
        raise HTTPException(status_code=500, detail="audit_logs must contain an array")

    incoming_ids = {
        audit_log.get("audit_id")
        for audit_log in audit_logs
        if isinstance(audit_log, dict) and audit_log.get("audit_id")
    }
    with session_scope() as session:
        for existing_log in session.query(AuditLog).all():
            if existing_log.audit_id not in incoming_ids:
                session.delete(existing_log)

        for audit_log in audit_logs:
            if not isinstance(audit_log, dict) or not audit_log.get("audit_id"):
                continue
            row = session.get(AuditLog, audit_log.get("audit_id"))
            if row is None:
                row = AuditLog(
                    audit_id=audit_log.get("audit_id"),
                    event_type=audit_log.get("event_type"),
                    message=audit_log.get("message") or "",
                    created_at=audit_log.get("created_at") or utc_now(),
                )
                session.add(row)

            row.event_type = audit_log.get("event_type")
            row.company_id = audit_log.get("company_id")
            row.company_name = audit_log.get("company_name")
            row.actor_user_id = audit_log.get("actor_user_id")
            row.actor_username = audit_log.get("actor_username")
            row.actor_role = audit_log.get("actor_role")
            row.device_id = audit_log.get("device_id")
            row.request_id = audit_log.get("request_id")
            row.job_id = audit_log.get("job_id")
            row.target_type = audit_log.get("target_type")
            row.target_label = audit_log.get("target_label")
            row.message = audit_log.get("message") or ""
            row.metadata_json = json.dumps(audit_log.get("metadata") or {})
            row.created_at = audit_log.get("created_at") or row.created_at or utc_now()
    write_audit_logs_json(audit_logs)


def safe_actor_type(actor_type):
    if actor_type in {"system_admin", "company_admin", "user", "agent", "system"}:
        return actor_type
    if actor_type == "viewer":
        return "user"
    return "system"


def action_from_event_type(event_type):
    return AUDIT_EVENT_ACTIONS.get(event_type, (event_type or "activity").lower())


def infer_actor_type(event_type, actor, device_id=None):
    if isinstance(actor, dict) and actor.get("role"):
        return safe_actor_type(actor.get("role"))
    if event_type in {
        "INVENTORY_SCAN_STARTED",
        "INVENTORY_SCAN_SUCCESS",
        "INVENTORY_SCAN_FAILED",
        "INVENTORY_UPDATED",
        "JOB_STARTED",
        "JOB_SUCCESS",
        "JOB_FAILED",
        "JOB_SKIPPED",
    }:
        return "agent"
    if event_type in {"DEVICE_ENROLLED", "DEVICE_HEARTBEAT_FIRST_SEEN"}:
        return "agent" if device_id else "system"
    return "system"


def normalize_audit_record(audit_entry):
    if not isinstance(audit_entry, dict):
        return {}

    metadata = audit_entry.get("details")
    if metadata is None:
        metadata = audit_entry.get("metadata")
    if metadata is None and audit_entry.get("metadata_json"):
        try:
            metadata = json.loads(audit_entry.get("metadata_json") or "{}")
        except json.JSONDecodeError:
            metadata = {}

    tenant_id = audit_entry.get("tenant_id") or audit_entry.get("company_id")
    actor_type = safe_actor_type(
        audit_entry.get("actor_type")
        or audit_entry.get("actor_role")
        or infer_actor_type(audit_entry.get("event_type"), {}, audit_entry.get("device_id"))
    )
    target_id = (
        audit_entry.get("target_id")
        or audit_entry.get("job_id")
        or audit_entry.get("request_id")
        or audit_entry.get("device_id")
        or audit_entry.get("target_label")
    )
    actor_id = audit_entry.get("actor_id") or audit_entry.get("actor_user_id")
    actor_name = audit_entry.get("actor_name") or audit_entry.get("actor_username")
    if actor_type == "agent":
        actor_id = actor_id or audit_entry.get("device_id")
        actor_name = actor_name or audit_entry.get("target_label") or audit_entry.get("device_id") or "Systemo Agent"
    elif actor_type == "system":
        actor_id = actor_id or "system"
        actor_name = actor_name or "System"

    return {
        "audit_id": audit_entry.get("audit_id"),
        "tenant_id": tenant_id,
        "company_id": tenant_id,
        "company_name": audit_entry.get("company_name"),
        "actor_type": actor_type,
        "actor_id": actor_id,
        "actor_name": actor_name,
        "actor_role": audit_entry.get("actor_role") or actor_type,
        "actor_username": audit_entry.get("actor_username") or actor_name,
        "action": audit_entry.get("action") or action_from_event_type(audit_entry.get("event_type")),
        "event_type": audit_entry.get("event_type"),
        "target_type": audit_entry.get("target_type"),
        "target_id": target_id,
        "target_label": audit_entry.get("target_label") or target_id,
        "message": audit_entry.get("message") or "",
        "details": metadata or {},
        "metadata": metadata or {},
        "created_at": audit_entry.get("created_at"),
    }


def write_audit_logs_json(audit_logs=None):
    try:
        BACKEND_DIR.mkdir(parents=True, exist_ok=True)
        entries = audit_logs if audit_logs is not None else load_audit_logs()
        normalized_entries = [normalize_audit_record(entry) for entry in entries if isinstance(entry, dict)]
        with AUDIT_LOGS_FILE.open("w", encoding="utf-8") as file:
            json.dump(normalized_entries, file, indent=2)
            file.write("\n")
    except Exception:
        # The SQLite audit log is authoritative; JSON mirror failures should not break backend flows.
        pass


def record_audit_log(
    tenant_id,
    actor_type,
    actor_id,
    actor_name,
    action,
    target_type,
    target_id,
    message,
    details=None,
    company_name=None,
    event_type=None,
    actor_role=None,
    device_id=None,
    request_id=None,
    job_id=None,
    target_label=None,
):
    event_type = event_type or str(action or "activity").upper()
    resolved_target_id = target_id or job_id or request_id or device_id or target_label
    audit_entry = {
        "audit_id": f"audit-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}",
        "event_type": event_type,
        "company_id": tenant_id,
        "company_name": company_name,
        "actor_user_id": actor_id if actor_type in {"system_admin", "company_admin", "user"} else None,
        "actor_username": actor_name if actor_type in {"system_admin", "company_admin", "user"} else None,
        "actor_role": actor_role or actor_type,
        "device_id": device_id or (resolved_target_id if target_type == "device" else None),
        "request_id": request_id or (resolved_target_id if target_type in {"ticket", "app_request", "request"} else None),
        "job_id": job_id or (resolved_target_id if target_type == "job" else None),
        "target_type": target_type,
        "target_label": target_label or resolved_target_id,
        "message": message,
        "metadata": details or {},
        "tenant_id": tenant_id,
        "actor_type": safe_actor_type(actor_type),
        "actor_id": actor_id,
        "actor_name": actor_name,
        "action": action,
        "target_id": resolved_target_id,
        "details": details or {},
        "created_at": utc_now(),
    }
    audit_logs = load_audit_logs()
    audit_logs.append(audit_entry)
    save_audit_logs(audit_logs)
    return normalize_audit_record(audit_entry)


def log_audit(
    event_type,
    message,
    company_id=None,
    company_name=None,
    actor=None,
    device_id=None,
    request_id=None,
    job_id=None,
    target_type=None,
    target_label=None,
    metadata=None,
):
    actor = actor if isinstance(actor, dict) else {}
    actor_type = infer_actor_type(event_type, actor, device_id=device_id)
    actor_id = actor.get("user_id")
    actor_name = actor.get("username")
    if actor_type == "agent":
        actor_id = actor_id or device_id
        actor_name = actor_name or device_id or "Systemo Agent"
    elif actor_type == "system":
        actor_id = actor_id or "system"
        actor_name = actor_name or "System"
    target_id = job_id or request_id or device_id or target_label
    return record_audit_log(
        tenant_id=company_id,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_name=actor_name,
        action=action_from_event_type(event_type),
        target_type=target_type,
        target_id=target_id,
        message=message,
        details=metadata or {},
        company_name=company_name,
        event_type=event_type,
        actor_role=actor.get("role") or actor_type,
        device_id=device_id,
        request_id=request_id,
        job_id=job_id,
        target_label=target_label,
    )


def load_devices():
    with session_scope() as session:
        return [
            device.to_dict()
            for device in session.query(Device).order_by(Device.last_seen_at.desc()).all()
        ]


def save_devices(devices):
    if not isinstance(devices, list):
        raise HTTPException(status_code=500, detail="devices must contain an array")

    now = utc_now()
    incoming_ids = {
        device.get("device_id")
        for device in devices
        if isinstance(device, dict) and device.get("device_id")
    }
    fallback_company_id, fallback_company_name = get_default_company_for_legacy_data()
    with session_scope() as session:
        for existing_device in session.query(Device).all():
            if existing_device.device_id not in incoming_ids:
                session.delete(existing_device)

        for device in devices:
            if not isinstance(device, dict) or not device.get("device_id"):
                continue
            company_id = device.get("company_id") or fallback_company_id
            company_name = device.get("company_name") or fallback_company_name
            if not company_id or not company_name:
                continue
            row = session.get(Device, device.get("device_id"))
            if row is None:
                row = Device(
                    device_id=device.get("device_id"),
                    company_id=company_id,
                    company_name=company_name,
                    created_at=device.get("created_at") or now,
                    updated_at=device.get("updated_at") or now,
                )
                session.add(row)

            row.company_id = company_id
            row.company_name = company_name
            row.hostname = device.get("hostname")
            row.username = device.get("username")
            row.os = device.get("os")
            row.agent_name = device.get("agent_name")
            row.agent_version = device.get("agent_version")
            row.approval_status = device.get("approval_status") or "pending_approval"
            row.connection_status = device.get("connection_status") or device.get("status") or "online"
            row.status = device.get("status") or row.connection_status
            row.last_seen_at = device.get("last_seen_at")
            row.created_at = device.get("created_at") or row.created_at or now
            row.updated_at = now


def load_tenants():
    with session_scope() as session:
        tenants = [
            company.to_dict()
            for company in session.query(Company).order_by(Company.created_at.asc()).all()
        ]

    for tenant in tenants:
        ensure_company_fields(tenant)

    return tenants


def save_tenants(tenants):
    if not isinstance(tenants, list):
        raise HTTPException(status_code=500, detail="tenants must contain an array")

    now = utc_now()
    incoming_ids = {
        (tenant.get("company_id") or tenant.get("tenant_id"))
        for tenant in tenants
        if isinstance(tenant, dict) and (tenant.get("company_id") or tenant.get("tenant_id"))
    }
    with session_scope() as session:
        for existing_company in session.query(Company).all():
            if existing_company.company_id not in incoming_ids:
                session.delete(existing_company)

        for tenant in tenants:
            if not isinstance(tenant, dict):
                continue
            ensure_company_fields(tenant)
            company_id = tenant.get("company_id") or tenant.get("tenant_id")
            if not company_id:
                continue
            row = session.get(Company, company_id)
            if row is None:
                row = Company(
                    company_id=company_id,
                    company_name=tenant.get("company_name"),
                    slug=tenant.get("slug") or company_id,
                    created_at=tenant.get("created_at") or now,
                    updated_at=tenant.get("updated_at") or now,
                )
                session.add(row)

            row.company_name = tenant.get("company_name")
            row.slug = tenant.get("slug") or company_id
            row.status = tenant.get("status") or "active"
            row.created_at = tenant.get("created_at") or row.created_at or now
            row.updated_at = tenant.get("updated_at") or now


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


def get_or_create_company(company_name, actor=None):
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
    log_audit(
        "TENANT_CREATED",
        f"Company {company.get('company_name')} was created.",
        company_id=company.get("company_id"),
        company_name=company.get("company_name"),
        actor=actor,
        target_type="tenant",
        target_label=company.get("company_id"),
        metadata={"company_name": company.get("company_name")},
    )
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
    if not isinstance(users, list):
        raise HTTPException(status_code=500, detail="users must contain an array")

    now = utc_now()
    incoming_ids = {
        user.get("user_id")
        for user in users
        if isinstance(user, dict) and user.get("user_id")
    }
    with session_scope() as session:
        for existing_user in session.query(User).all():
            if existing_user.user_id not in incoming_ids:
                session.delete(existing_user)

        for user in users:
            if not isinstance(user, dict) or not user.get("user_id"):
                continue
            row = session.get(User, user.get("user_id"))
            if row is None:
                row = User(
                    user_id=user.get("user_id"),
                    username=user.get("username"),
                    password_hash=user.get("password_hash"),
                    role=user.get("role"),
                    created_at=user.get("created_at") or now,
                    updated_at=user.get("updated_at") or now,
                )
                session.add(row)

            row.username = user.get("username")
            row.password_hash = user.get("password_hash")
            row.role = user.get("role")
            row.company_id = user.get("company_id")
            row.created_at = user.get("created_at") or row.created_at or now
            row.updated_at = user.get("updated_at") or now


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
    with session_scope() as session:
        users = [user.to_dict() for user in session.query(User).order_by(User.created_at.asc()).all()]

    if not users:
        return seed_default_users()

    return users


def safe_load_json_array(path):
    if not path.exists():
        return None

    try:
        with path.open("r", encoding="utf-8") as file:
            value = json.load(file)
    except (OSError, json.JSONDecodeError):
        return None

    return value if isinstance(value, list) else None


def table_has_records(model):
    with session_scope() as session:
        return session.query(model).first() is not None


def migrate_existing_json_data():
    migrations = [
        (TENANTS_FILE, Company, save_tenants),
        (USERS_FILE, User, save_users),
        (DEVICES_FILE, Device, save_devices),
        (APP_REQUESTS_FILE, AppRequest, save_app_requests),
        (JOBS_FILE, Job, save_jobs),
        (AUDIT_LOGS_FILE, AuditLog, save_audit_logs),
    ]
    for path, model, save_function in migrations:
        if table_has_records(model):
            continue
        records = safe_load_json_array(path)
        if records:
            save_function(records)


def initialize_persistent_data():
    migrate_existing_json_data()
    load_users()
    seed_default_app_catalog()


initialize_persistent_data()


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
        log_audit(
            "UNAUTHORIZED_ACCESS_ATTEMPT",
            "User attempted an action without the required role",
            company_id=user.get("company_id"),
            actor=user,
            target_type="role",
            target_label=user.get("role"),
            metadata={"allowed_roles": sorted(allowed_roles)},
        )
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


def filter_app_requests_for_user(app_requests, user):
    if user.get("role") == "system_admin":
        return app_requests
    return [
        app_request
        for app_request in app_requests
        if isinstance(app_request, dict) and app_request.get("company_id") == user.get("company_id")
    ]


def filter_audit_logs_for_user(audit_logs, user):
    if user.get("role") == "system_admin":
        return audit_logs
    return [
        audit_entry
        for audit_entry in audit_logs
        if isinstance(audit_entry, dict) and audit_entry.get("company_id") == user.get("company_id")
    ]


def assert_company_access(user, company_id):
    if user.get("role") == "system_admin":
        return
    if user.get("company_id") != company_id:
        log_audit(
            "UNAUTHORIZED_ACCESS_ATTEMPT",
            "User attempted to access another company",
            company_id=company_id,
            actor=user,
            target_type="company",
            target_label=company_id,
            metadata={"user_company_id": user.get("company_id")},
        )
        raise HTTPException(status_code=403, detail="Forbidden")


def assert_can_manage_device(user, device):
    require_role(user, {"system_admin", "company_admin"})
    assert_company_access(user, device.get("company_id"))


def assert_can_create_job(user, company_id):
    require_role(user, {"system_admin", "company_admin"})
    assert_company_access(user, company_id)


def assert_can_create_app_request(user, company_id):
    require_role(user, {"system_admin", "company_admin", "viewer"})
    assert_company_access(user, company_id)


def assert_can_decide_app_request(user, app_request):
    require_role(user, {"system_admin", "company_admin"})
    assert_company_access(user, app_request.get("company_id"))


def resolve_target_from_payload(payload):
    target_device_id = payload.target_device_id or payload.device_id or "any"
    if target_device_id == "any":
        return "any", "any_approved_device"
    return target_device_id, "specific_device"


def resolve_company_for_target(company_id=None, company_name=None, target_device_id="any"):
    if target_device_id != "any":
        target_device = get_device(target_device_id)
        device_company_id = target_device.get("company_id")
        if company_id and company_id != device_company_id:
            raise HTTPException(status_code=400, detail="Target device does not belong to selected company")
        return target_device.get("company_id"), target_device.get("company_name"), target_device

    company = get_company_from_request(
        company_id=company_id,
        company_name=company_name,
        create_if_missing=False,
    )
    return company.get("company_id"), company.get("company_name"), None


def validate_app_request_target(company_id, target_device_id, require_approved_device=False):
    if target_device_id == "any":
        return

    target_device = get_device(target_device_id)
    if target_device.get("company_id") != company_id:
        raise HTTPException(status_code=400, detail="Target device does not belong to request company")
    if require_approved_device and target_device.get("approval_status") != "approved":
        raise HTTPException(status_code=400, detail="Target device must be approved before a job can be created")


def company_has_approved_device(company_id):
    return any(
        isinstance(device, dict)
        and device.get("company_id") == company_id
        and device.get("approval_status") == "approved"
        for device in load_devices()
    )


def find_app_request(app_requests, request_id):
    for app_request in app_requests:
        if isinstance(app_request, dict) and app_request.get("request_id") == request_id:
            return app_request
    return None


def create_app_request_record(payload, user):
    if payload.action not in ALLOWED_ACTIONS:
        raise HTTPException(status_code=400, detail="Unsupported action")

    target_device_id, target_type = resolve_target_from_payload(payload)
    requested_company_id = payload.company_id
    requested_company_name = payload.company_name
    if user.get("role") != "system_admin":
        requested_company_id = user.get("company_id")
        requested_company_name = None

    if target_device_id != "any":
        target_device = get_device(target_device_id)
        company_id = target_device.get("company_id")
        company_name = target_device.get("company_name")
    else:
        company_id, company_name, _ = resolve_company_for_target(
            company_id=requested_company_id,
            company_name=requested_company_name,
            target_device_id=target_device_id,
        )
    assert_can_create_app_request(user, company_id)
    validate_app_request_target(company_id, target_device_id, require_approved_device=False)
    app_catalog_entry = get_available_catalog_entry(payload.app, payload.action, company_id=company_id, user=user)

    now = utc_now()
    app_request = {
        "request_id": f"req-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}",
        "company_id": company_id,
        "company_name": company_name,
        "device_id": None if target_device_id == "any" else target_device_id,
        "target_device_id": target_device_id,
        "target_type": target_type,
        "app": app_catalog_entry.get("app_key"),
        "action": payload.action,
        "requested_by_user_id": user.get("user_id"),
        "requested_by_username": user.get("username"),
        "status": "pending",
        "approved_by_user_id": None,
        "approved_by_username": None,
        "rejected_by_user_id": None,
        "rejected_by_username": None,
        "linked_job_id": None,
        "reason": payload.reason,
        "created_at": now,
        "updated_at": now,
    }
    app_requests = load_app_requests()
    app_requests.append(app_request)
    save_app_requests(app_requests)
    log_audit(
        "APP_REQUEST_CREATED",
        f"App request created for {payload.app} {payload.action}",
        company_id=company_id,
        company_name=company_name,
        actor=user,
        device_id=None if target_device_id == "any" else target_device_id,
        request_id=app_request.get("request_id"),
        target_type=target_type,
        target_label=target_device_id,
        metadata={"app": app_catalog_entry.get("app_key"), "action": payload.action, "reason": payload.reason},
    )
    return app_request


def approve_app_request_record(request_id, user, decision):
    app_requests = load_app_requests()
    app_request = find_app_request(app_requests, request_id)
    if app_request is None:
        raise HTTPException(status_code=404, detail="App request not found")

    assert_can_decide_app_request(user, app_request)
    if app_request.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Only pending app requests can be approved")

    company_id = app_request.get("company_id")
    target_device_id = app_request.get("target_device_id") or "any"
    validate_app_request_target(company_id, target_device_id, require_approved_device=True)
    if target_device_id == "any" and not company_has_approved_device(company_id):
        raise HTTPException(status_code=400, detail="Company must have at least one approved device")
    app_catalog_entry = get_available_catalog_entry(
        app_request.get("app"),
        app_request.get("action"),
        company_id=company_id,
        user=user,
    )

    job = create_executable_job(
        app=app_catalog_entry.get("app_key"),
        action=app_request.get("action"),
        device_id="any" if target_device_id == "any" else target_device_id,
        company_id=company_id,
        company_name=app_request.get("company_name"),
        created_by_user_id=app_request.get("requested_by_user_id"),
        created_by_username=app_request.get("requested_by_username"),
        approved_by_user_id=user.get("user_id"),
        approved_by_username=user.get("username"),
        source_request_id=app_request.get("request_id"),
        actor=user,
        app_catalog_entry=app_catalog_entry,
    )

    app_request["status"] = "converted_to_job"
    app_request["approved_by_user_id"] = user.get("user_id")
    app_request["approved_by_username"] = user.get("username")
    app_request["linked_job_id"] = job.get("id")
    if decision.reason:
        app_request["reason"] = decision.reason
    app_request["updated_at"] = utc_now()
    save_app_requests(app_requests)
    log_audit(
        "APP_REQUEST_APPROVED",
        f"App request approved and converted to job {job.get('id')}",
        company_id=app_request.get("company_id"),
        company_name=app_request.get("company_name"),
        actor=user,
        device_id=None if target_device_id == "any" else target_device_id,
        request_id=app_request.get("request_id"),
        job_id=job.get("id"),
        target_type=app_request.get("target_type"),
        target_label=target_device_id,
        metadata={"app": app_request.get("app"), "action": app_request.get("action")},
    )
    return app_request


def reject_app_request_record(request_id, user, decision):
    app_requests = load_app_requests()
    app_request = find_app_request(app_requests, request_id)
    if app_request is None:
        raise HTTPException(status_code=404, detail="App request not found")

    assert_can_decide_app_request(user, app_request)
    if app_request.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Only pending app requests can be rejected")

    app_request["status"] = "rejected"
    app_request["rejected_by_user_id"] = user.get("user_id")
    app_request["rejected_by_username"] = user.get("username")
    if decision.reason:
        app_request["reason"] = decision.reason
    app_request["updated_at"] = utc_now()
    save_app_requests(app_requests)
    log_audit(
        "APP_REQUEST_REJECTED",
        "App request rejected",
        company_id=app_request.get("company_id"),
        company_name=app_request.get("company_name"),
        actor=user,
        device_id=app_request.get("device_id"),
        request_id=app_request.get("request_id"),
        target_type=app_request.get("target_type"),
        target_label=app_request.get("target_device_id"),
        metadata={"app": app_request.get("app"), "action": app_request.get("action"), "reason": decision.reason},
    )
    return app_request


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
    .status.requires_user_action,
    .status.rejected {
      background: #fff0ed;
      color: var(--danger);
    }

    .status.approved,
    .status.installing,
    .status.uninstalling,
    .status.pending {
      background: #fff7e8;
      color: var(--warn);
    }

    .status.converted_to_job {
      background: #e8f5ee;
      color: var(--ok);
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

    <section>
      <div class="section-header">
        <h2>App Catalog</h2>
      </div>
      <form id="catalogForm" class="actions">
        <label>
          App key
          <input id="catalogAppKeyInput" name="app_key" type="text" required placeholder="7zip">
        </label>
        <label>
          Display name
          <input id="catalogDisplayNameInput" name="display_name" type="text" required placeholder="7-Zip">
        </label>
        <label>
          Winget ID
          <input id="catalogWingetIdInput" name="winget_id" type="text" required placeholder="7zip.7zip">
        </label>
        <label>
          Actions
          <select id="catalogActionsSelect" name="supported_actions">
            <option value="install,uninstall">install, uninstall</option>
            <option value="install">install</option>
            <option value="uninstall">uninstall</option>
          </select>
        </label>
        <label>
          Scope
          <select id="catalogScopeSelect" name="scope">
            <option value="global">global</option>
            <option value="company">company</option>
          </select>
        </label>
        <button type="submit">Create App</button>
      </form>
      <div id="catalogMessage" class="message"></div>
      <div id="catalogTable" class="table-wrap"></div>
    </section>

    <section id="requestSection">
      <div class="section-header">
        <h2>Create App Request</h2>
      </div>
      <form id="requestForm" class="actions">
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
        <button type="submit">Create Request</button>
      </form>
      <div id="inventoryHint" class="message"></div>
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
        <h2>Device Inventory</h2>
      </div>
      <div id="inventoryTable" class="table-wrap"></div>
    </section>

    <section>
      <div class="section-header">
        <h2>App Requests</h2>
      </div>
      <div id="requestsTable" class="table-wrap"></div>
    </section>

    <section>
      <div class="section-header">
        <h2>Executable Jobs</h2>
      </div>
      <div id="jobsTable" class="table-wrap"></div>
    </section>

    <section>
      <div class="section-header">
        <h2>Audit Logs</h2>
      </div>
      <form id="auditFilterForm" class="actions">
        <label id="auditCompanyLabel">
          Company
          <select id="auditCompanySelect" name="company_id"></select>
        </label>
        <label>
          Action
          <select id="auditActionSelect" name="action"></select>
        </label>
        <label>
          Actor type
          <select id="auditActorTypeSelect" name="actor_type"></select>
        </label>
        <button type="submit" class="secondary">Apply</button>
      </form>
      <div id="auditTable" class="table-wrap"></div>
    </section>
  </main>

  <script>
    const companyFields = ["company_id", "company_name", "created_at", "updated_at"];
    const catalogFields = ["app_id", "display_name", "app_key", "winget_id", "supported_actions", "enabled", "scope", "company_id", "updated_at"];
    const deviceFields = ["company_name", "hostname", "username", "os", "agent_version", "connection_status", "approval_status", "installed_apps_count", "last_inventory_scan_at", "last_seen_at"];
    const inventoryFields = ["device_id", "display_name", "detected_name", "detected_id", "version", "source", "is_catalog_match", "last_seen_at"];
    const requestFields = ["request_id", "company_name", "target_device_id", "app", "action", "requested_by_username", "status", "linked_job_id", "created_at"];
    const jobFields = ["id", "company_name", "device_id", "app", "action", "status", "attempts", "message", "started_at", "finished_at"];
    const auditFields = ["created_at", "tenant_id", "company_name", "actor_name", "actor_type", "action", "target_type", "target_id", "message"];
    const auditActions = [
      "ALL",
      "tenant_created",
      "tenant_updated",
      "device_enrolled",
      "device_approved",
      "device_rejected",
      "device_check_in",
      "ticket_created",
      "ticket_approved",
      "ticket_rejected",
      "job_created",
      "job_started",
      "job_success",
      "job_failed",
      "job_skipped",
      "user_login_success",
      "user_login_failed",
      "user_logout",
    ];
    const auditActorTypes = ["ALL", "system_admin", "company_admin", "user", "agent", "system"];
    let currentUser = null;
    let lastCompanies = [];
    let lastDevices = [];
    let lastCatalog = { apps: [], actions: ["install", "uninstall"], entries: [] };
    let lastAppCatalog = [];
    let lastInventory = [];

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

    function renderRequests(rows) {
      const target = document.getElementById("requestsTable");
      if (!rows.length) {
        target.innerHTML = '<div class="empty">No records found.</div>';
        return;
      }

      const showActions = currentUser && currentUser.role !== "viewer";
      const columns = showActions ? [...requestFields, "actions"] : requestFields;
      const header = columns.map((field) => `<th>${escapeHtml(field)}</th>`).join("");
      const body = rows.map((row) => {
        const cells = requestFields.map((field) => {
          const value = row[field];
          return `<td>${field === "status" ? statusCell(value) : escapeHtml(value)}</td>`;
        }).join("");
        const isPending = row.status === "pending";
        const actions = isPending
          ? `<button class="small" type="button" data-request-approve="${escapeHtml(row.request_id)}">Approve</button> <button class="small secondary" type="button" data-request-reject="${escapeHtml(row.request_id)}">Reject</button>`
          : "-";
        return showActions ? `<tr>${cells}<td>${actions}</td></tr>` : `<tr>${cells}</tr>`;
      }).join("");
      target.innerHTML = `<table><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table>`;
    }

    function renderCatalog(rows) {
      const target = document.getElementById("catalogTable");
      if (!rows.length) {
        target.innerHTML = '<div class="empty">No records found.</div>';
        return;
      }

      const showActions = currentUser && currentUser.role === "system_admin";
      const columns = showActions ? [...catalogFields, "actions"] : catalogFields;
      const header = columns.map((field) => `<th>${escapeHtml(field)}</th>`).join("");
      const body = rows.map((row) => {
        const cells = catalogFields.map((field) => {
          const value = Array.isArray(row[field]) ? row[field].join(", ") : row[field];
          return `<td>${field === "enabled" ? statusCell(value ? "enabled" : "disabled") : escapeHtml(value)}</td>`;
        }).join("");
        const toggleAction = row.enabled ? "disable" : "enable";
        const actions = `<button class="small secondary" type="button" data-catalog-edit="${escapeHtml(row.app_id)}">Edit</button> <button class="small" type="button" data-catalog-toggle="${escapeHtml(row.app_id)}" data-catalog-action="${toggleAction}">${toggleAction}</button>`;
        return showActions ? `<tr>${cells}<td>${actions}</td></tr>` : `<tr>${cells}</tr>`;
      }).join("");
      target.innerHTML = `<table><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table>`;
    }

    function renderInventory(rows) {
      const target = document.getElementById("inventoryTable");
      if (!rows.length) {
        target.innerHTML = '<div class="empty">No inventory records found.</div>';
        return;
      }

      const header = inventoryFields.map((field) => `<th>${escapeHtml(field)}</th>`).join("");
      const body = rows.map((row) => {
        const cells = inventoryFields.map((field) => {
          const value = field === "is_catalog_match" ? (row[field] ? "yes" : "no") : row[field];
          return `<td>${field === "is_catalog_match" ? statusCell(value) : escapeHtml(value)}</td>`;
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

    function populateAppSelect(entries) {
      const select = document.getElementById("appSelect");
      const currentValue = select.value;
      select.innerHTML = entries.map((entry) => {
        return `<option value="${escapeHtml(entry.app_key)}">${escapeHtml(entry.display_name || entry.app_key)}</option>`;
      }).join("");
      if (entries.some((entry) => entry.app_key === currentValue)) {
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
      const catalogEntries = (lastCatalog.entries || []).filter((entry) => {
        return entry.enabled && (entry.scope === "global" || entry.company_id === selectedCompanyId);
      });
      populateSelect("companySelect", companyOptions);
      if (selectedCompanyId && companyOptions.includes(selectedCompanyId)) {
        companySelect.value = selectedCompanyId;
      }
      populateSelect("deviceSelect", [...deviceIds]);
      populateAppSelect(catalogEntries);
      const selectedApp = document.getElementById("appSelect").value;
      const selectedEntry = catalogEntries.find((entry) => entry.app_key === selectedApp);
      populateSelect("actionSelect", selectedEntry ? selectedEntry.supported_actions : lastCatalog.actions);
      updateInventoryHint();
    }

    function updateInventoryHint() {
      const hint = document.getElementById("inventoryHint");
      const deviceId = document.getElementById("deviceSelect").value;
      const appKey = document.getElementById("appSelect").value;
      const action = document.getElementById("actionSelect").value;
      hint.className = "message";
      hint.textContent = "";
      if (!deviceId || deviceId === "any" || !appKey) {
        return;
      }

      const deviceInventory = lastInventory.filter((item) => item.device_id === deviceId);
      if (!deviceInventory.length) {
        hint.textContent = "Inventory warning: no inventory scan is available for this device yet.";
        return;
      }
      const installed = deviceInventory.some((item) => item.app_key === appKey);
      if (action === "install" && installed) {
        hint.textContent = "Inventory warning: this app appears to already be installed on the selected device.";
      }
      if (action === "uninstall" && !installed) {
        hint.textContent = "Inventory warning: this app does not appear in the selected device inventory.";
      }
    }

    function refreshAuditFilters() {
      const auditCompanySelect = document.getElementById("auditCompanySelect");
      const currentCompany = auditCompanySelect.value;
      const companyOptions = ["ALL", ...lastCompanies.map((company) => company.company_id)];
      populateSelect("auditCompanySelect", companyOptions);
      if (companyOptions.includes(currentCompany)) {
        auditCompanySelect.value = currentCompany;
      }
      populateSelect("auditActionSelect", auditActions);
      populateSelect("auditActorTypeSelect", auditActorTypes);
    }

    function getAuditPath() {
      const params = new URLSearchParams({ limit: "100" });
      const companyId = document.getElementById("auditCompanySelect").value;
      const action = document.getElementById("auditActionSelect").value;
      const actorType = document.getElementById("auditActorTypeSelect").value;
      if (companyId && companyId !== "ALL") {
        params.set("tenant_id", companyId);
      }
      if (action && action !== "ALL") {
        params.set("action", action);
      }
      if (actorType && actorType !== "ALL") {
        params.set("actor_type", actorType);
      }
      return `/api/admin/audit-logs?${params.toString()}`;
    }

    function applyRoleUi() {
      if (!currentUser) {
        return;
      }
      document.getElementById("userInfo").textContent = `${currentUser.username} (${currentUser.role})`;
      document.getElementById("companyForm").style.display = currentUser.role === "system_admin" ? "" : "none";
      document.getElementById("catalogForm").style.display = currentUser.role === "system_admin" ? "" : "none";
      document.getElementById("requestSection").style.display = "";
      document.getElementById("companySelect").disabled = currentUser.role !== "system_admin";
      document.getElementById("auditCompanyLabel").style.display = currentUser.role === "system_admin" ? "" : "none";
    }

    async function refreshAll() {
      try {
        const [session, health, companies, devices, inventory, requests, jobs, auditLogs, catalog, appCatalog] = await Promise.all([
          fetchJson("/dashboard/api/session"),
          fetchJson("/health"),
          fetchJson("/dashboard/api/companies"),
          fetchJson("/dashboard/api/devices"),
          fetchJson("/api/inventory"),
          fetchJson("/api/app-requests"),
          fetchJson("/dashboard/api/jobs"),
          fetchJson(getAuditPath()),
          fetchJson("/dashboard/api/catalog"),
          fetchJson("/api/app-catalog"),
        ]);

        currentUser = session.user;
        applyRoleUi();
        setHealth(health.status === "ok", `Backend ${health.status}`);
        lastCompanies = Array.isArray(companies) ? companies : [];
        lastDevices = Array.isArray(devices) ? devices : [];
        lastInventory = Array.isArray(inventory) ? inventory : [];
        lastCatalog = catalog;
        lastAppCatalog = Array.isArray(appCatalog) ? appCatalog : [];
        refreshFormOptions();
        refreshAuditFilters();
        renderTable("companiesTable", companyFields, lastCompanies);
        renderCatalog(lastAppCatalog);
        renderDevices(lastDevices);
        renderInventory(lastInventory);
        renderRequests(Array.isArray(requests) ? [...requests].reverse() : []);
        renderTable("jobsTable", jobFields, Array.isArray(jobs) ? [...jobs].reverse() : []);
        renderTable("auditTable", auditFields, Array.isArray(auditLogs) ? auditLogs : []);
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

    async function createCatalogEntry(event) {
      event.preventDefault();
      const message = document.getElementById("catalogMessage");
      message.textContent = "";
      message.className = "message";
      const selectedCompanyId = document.getElementById("companySelect").value || (lastCompanies[0] && lastCompanies[0].company_id) || "";
      const scope = document.getElementById("catalogScopeSelect").value;
      const payload = {
        app_key: document.getElementById("catalogAppKeyInput").value,
        display_name: document.getElementById("catalogDisplayNameInput").value,
        winget_id: document.getElementById("catalogWingetIdInput").value,
        detection_id: document.getElementById("catalogWingetIdInput").value,
        supported_actions: document.getElementById("catalogActionsSelect").value.split(",").map((value) => value.trim()),
        scope,
      };
      if (scope === "company") {
        payload.company_id = selectedCompanyId;
      }

      try {
        const entry = await fetchJson("/api/app-catalog", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        message.textContent = `Created app ${entry.app_key}`;
        document.getElementById("catalogAppKeyInput").value = "";
        document.getElementById("catalogDisplayNameInput").value = "";
        document.getElementById("catalogWingetIdInput").value = "";
        await refreshAll();
      } catch (error) {
        message.textContent = error.message;
        message.className = "message error";
      }
    }

    async function editCatalogEntry(appId) {
      const entries = lastAppCatalog;
      const entry = entries.find((candidate) => candidate.app_id === appId);
      if (!entry) {
        return;
      }
      const displayName = prompt("Display name", entry.display_name || "");
      if (displayName === null) {
        return;
      }
      const wingetId = prompt("Winget ID", entry.winget_id || "");
      if (wingetId === null) {
        return;
      }
      const supportedActions = prompt("Supported actions", (entry.supported_actions || []).join(","));
      if (supportedActions === null) {
        return;
      }
      try {
        await fetchJson(`/api/app-catalog/${encodeURIComponent(appId)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            display_name: displayName,
            winget_id: wingetId,
            detection_id: wingetId,
            supported_actions: supportedActions.split(",").map((value) => value.trim()).filter(Boolean),
          }),
        });
        await refreshAll();
      } catch (error) {
        document.getElementById("catalogMessage").textContent = error.message;
        document.getElementById("catalogMessage").className = "message error";
      }
    }

    async function toggleCatalogEntry(appId, action) {
      try {
        await fetchJson(`/api/app-catalog/${encodeURIComponent(appId)}/${action}`, { method: "POST" });
        await refreshAll();
      } catch (error) {
        document.getElementById("catalogMessage").textContent = error.message;
        document.getElementById("catalogMessage").className = "message error";
      }
    }

    async function createAppRequest(event) {
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
        const appRequest = await fetchJson("/api/app-requests", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        message.textContent = `Created app request ${appRequest.request_id}`;
        await refreshAll();
      } catch (error) {
        message.textContent = error.message;
        message.className = "message error";
      }
    }

    async function updateRequestApproval(requestId, decision) {
      try {
        await fetchJson(`/api/app-requests/${encodeURIComponent(requestId)}/${decision}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
        });
        await refreshAll();
      } catch (error) {
        document.getElementById("formMessage").textContent = error.message;
        document.getElementById("formMessage").className = "message error";
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
    document.getElementById("appSelect").addEventListener("change", refreshFormOptions);
    document.getElementById("deviceSelect").addEventListener("change", updateInventoryHint);
    document.getElementById("actionSelect").addEventListener("change", updateInventoryHint);
    document.getElementById("companyForm").addEventListener("submit", createCompany);
    document.getElementById("catalogForm").addEventListener("submit", createCatalogEntry);
    document.getElementById("requestForm").addEventListener("submit", createAppRequest);
    document.getElementById("auditFilterForm").addEventListener("submit", (event) => {
      event.preventDefault();
      refreshAll();
    });
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
    document.getElementById("requestsTable").addEventListener("click", (event) => {
      const approveId = event.target.getAttribute("data-request-approve");
      const rejectId = event.target.getAttribute("data-request-reject");
      if (approveId) {
        updateRequestApproval(approveId, "approve");
      }
      if (rejectId) {
        updateRequestApproval(rejectId, "reject");
      }
    });
    document.getElementById("catalogTable").addEventListener("click", (event) => {
      const editId = event.target.getAttribute("data-catalog-edit");
      const toggleId = event.target.getAttribute("data-catalog-toggle");
      const action = event.target.getAttribute("data-catalog-action");
      if (editId) {
        editCatalogEntry(editId);
      }
      if (toggleId && action) {
        toggleCatalogEntry(toggleId, action);
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
        log_audit(
            "USER_LOGIN_FAILED",
            f"Login failed for username {request.username}",
            target_type="user",
            target_label=request.username,
            metadata={"username": request.username},
        )
        raise HTTPException(status_code=401, detail="Invalid username or password")
    log_audit(
        "USER_LOGIN_SUCCESS",
        f"User {user.get('username')} logged in",
        company_id=user.get("company_id"),
        actor=user,
        target_type="user",
        target_label=user.get("username"),
    )
    response = JSONResponse({"user": public_user(user)})
    set_session_cookie(response, user)
    return response


@app.post("/logout")
def logout(request: Request):
    user = get_optional_user(request)
    if user is not None:
        log_audit(
            "USER_LOGOUT",
            f"User {user.get('username')} logged out",
            company_id=user.get("company_id"),
            actor=user,
            target_type="user",
            target_label=user.get("username"),
        )
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
    user = get_current_user(request)
    return build_catalog_response(user, enabled_only=True)


@app.get("/dashboard/api/companies")
def dashboard_companies(request: Request):
    user = get_current_user(request)
    return filter_companies_for_user(get_companies(), user)


@app.post("/dashboard/api/companies")
def dashboard_create_company(request: Request, payload: CreateTenantRequest):
    user = get_current_user(request)
    require_role(user, {"system_admin"})
    return create_company(payload, actor=user)


@app.get("/dashboard/api/devices")
def dashboard_devices(request: Request):
    user = get_current_user(request)
    return filter_devices_for_user(get_devices(), user)


@app.post("/dashboard/api/devices/{device_id}/approve")
def dashboard_approve_device(request: Request, device_id: str):
    user = get_current_user(request)
    device = get_device(device_id)
    assert_can_manage_device(user, device)
    return approve_device(device_id, actor=user)


@app.post("/dashboard/api/devices/{device_id}/reject")
def dashboard_reject_device(request: Request, device_id: str):
    user = get_current_user(request)
    device = get_device(device_id)
    assert_can_manage_device(user, device)
    return reject_device(device_id, actor=user)


@app.get("/dashboard/api/jobs")
def dashboard_jobs(request: Request):
    user = get_current_user(request)
    return filter_jobs_for_user(get_all_jobs(), user)


@app.post("/dashboard/api/jobs")
def dashboard_create_job(request: Request, payload: CreateJobRequest):
    user = get_current_user(request)
    require_role(user, {"system_admin"})
    if payload.device_id != "any":
        target_device = get_device(payload.device_id)
        company_id = target_device.get("company_id")
    else:
        company_id = payload.company_id or user.get("company_id")
    if not company_id:
        raise HTTPException(status_code=400, detail="company_id is required")
    assert_can_create_job(user, company_id)
    return create_job(payload, actor=user)


@app.post("/api/app-requests")
def create_app_request(request: Request, payload: CreateAppRequestRequest):
    user = get_current_user(request)
    return create_app_request_record(payload, user)


@app.get("/api/app-requests")
def get_app_requests(request: Request):
    user = get_current_user(request)
    return filter_app_requests_for_user(load_app_requests(), user)


@app.post("/api/app-requests/{request_id}/approve")
def approve_app_request(
    request: Request,
    request_id: str,
    decision: Optional[AppRequestDecisionRequest] = None,
):
    user = get_current_user(request)
    if decision is None:
        decision = AppRequestDecisionRequest()
    return approve_app_request_record(request_id, user, decision)


@app.post("/api/app-requests/{request_id}/reject")
def reject_app_request(
    request: Request,
    request_id: str,
    decision: Optional[AppRequestDecisionRequest] = None,
):
    user = get_current_user(request)
    if decision is None:
        decision = AppRequestDecisionRequest()
    return reject_app_request_record(request_id, user, decision)


@app.get("/api/audit-logs")
def get_audit_logs(
    request: Request,
    company_id: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 100,
):
    user = get_current_user(request)
    audit_logs = load_audit_logs()
    if company_id:
        assert_company_access(user, company_id)
        audit_logs = [
            audit_entry
            for audit_entry in audit_logs
            if isinstance(audit_entry, dict) and audit_entry.get("company_id") == company_id
        ]
    else:
        audit_logs = filter_audit_logs_for_user(audit_logs, user)

    if event_type:
        audit_logs = [
            audit_entry
            for audit_entry in audit_logs
            if isinstance(audit_entry, dict) and audit_entry.get("event_type") == event_type
        ]

    sorted_logs = sorted(
        audit_logs,
        key=lambda audit_entry: audit_entry.get("created_at", "") if isinstance(audit_entry, dict) else "",
        reverse=True,
    )
    safe_limit = max(1, min(int(limit or 100), 500))
    return sorted_logs[:safe_limit]


def get_activity_history(
    user=None,
    tenant_id: Optional[str] = None,
    actor_type: Optional[str] = None,
    action: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    limit: int = 100,
):
    audit_logs = [normalize_audit_record(entry) for entry in load_audit_logs()]
    if user is not None and user.get("role") != "system_admin":
        audit_logs = [
            entry
            for entry in audit_logs
            if isinstance(entry, dict) and entry.get("tenant_id") == user.get("company_id")
        ]
    if tenant_id:
        if user is not None:
            assert_company_access(user, tenant_id)
        audit_logs = [
            entry
            for entry in audit_logs
            if isinstance(entry, dict) and entry.get("tenant_id") == tenant_id
        ]
    if actor_type:
        audit_logs = [
            entry
            for entry in audit_logs
            if isinstance(entry, dict) and entry.get("actor_type") == actor_type
        ]
    if action:
        audit_logs = [
            entry
            for entry in audit_logs
            if isinstance(entry, dict) and entry.get("action") == action
        ]
    if target_type:
        audit_logs = [
            entry
            for entry in audit_logs
            if isinstance(entry, dict) and entry.get("target_type") == target_type
        ]
    if target_id:
        audit_logs = [
            entry
            for entry in audit_logs
            if isinstance(entry, dict) and entry.get("target_id") == target_id
        ]
    sorted_logs = sorted(
        audit_logs,
        key=lambda entry: entry.get("created_at", "") if isinstance(entry, dict) else "",
        reverse=True,
    )
    safe_limit = max(1, min(int(limit or 100), 500))
    return sorted_logs[:safe_limit]


@app.get("/api/admin/audit-logs")
def get_admin_audit_logs(
    request: Request,
    tenant_id: Optional[str] = None,
    actor_type: Optional[str] = None,
    action: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    limit: int = 100,
):
    user = get_optional_user(request)
    return get_activity_history(
        user=user,
        tenant_id=tenant_id,
        actor_type=actor_type,
        action=action,
        target_type=target_type,
        target_id=target_id,
        limit=limit,
    )


@app.get("/api/admin/tenants/{tenant_id}/audit-logs")
def get_tenant_audit_logs(request: Request, tenant_id: str, limit: int = 100):
    user = get_optional_user(request)
    return get_activity_history(user=user, tenant_id=tenant_id, limit=limit)


@app.post("/api/agent/inventory")
def post_agent_inventory(payload: InventoryReportRequest):
    return submit_device_inventory(payload)


@app.get("/api/devices/{device_id}/inventory")
def get_device_inventory(request: Request, device_id: str):
    device = get_device(device_id)
    user = get_optional_user(request)
    if user is not None:
        assert_company_access(user, device.get("company_id"))
    return {
        "device": device,
        "apps": get_inventory_rows(device_id=device_id),
        "latest_scan": get_latest_inventory_scan(device_id),
    }


@app.get("/api/inventory")
def get_inventory(request: Request, company_id: Optional[str] = None):
    user = get_optional_user(request)
    if user is None:
        target_company_id = company_id
    elif company_id:
        assert_company_access(user, company_id)
        target_company_id = company_id
    elif user.get("role") == "system_admin":
        target_company_id = None
    else:
        target_company_id = user.get("company_id")
    return get_inventory_rows(company_id=target_company_id)


@app.get("/api/devices/{device_id}/catalog-status")
def get_device_catalog_status(request: Request, device_id: str):
    device = get_device(device_id)
    user = get_optional_user(request)
    if user is not None:
        assert_company_access(user, device.get("company_id"))
    installed_apps = get_inventory_rows(device_id=device_id)
    installed_keys = {app.get("app_key") for app in installed_apps if app.get("app_key")}
    installed_ids = {
        normalize_inventory_identifier(app.get("detected_id"))
        for app in installed_apps
        if app.get("detected_id")
    }
    catalog_entries = load_app_catalog_entries()
    if user is not None:
        catalog_entries = filter_catalog_for_user(catalog_entries, user, enabled_only=True)
    else:
        catalog_entries = [entry for entry in catalog_entries if entry.get("enabled")]
    statuses = []
    for entry in catalog_entries:
        installed = (
            entry.get("app_key") in installed_keys
            or normalize_inventory_identifier(entry.get("detection_id")) in installed_ids
            or normalize_inventory_identifier(entry.get("winget_id")) in installed_ids
        )
        statuses.append({**entry, "installed": installed})
    return statuses


@app.get("/health")
def health():
    return {"status": "ok"}


def build_catalog_response(user=None, enabled_only=True):
    entries = load_app_catalog_entries()
    if user is not None:
        entries = filter_catalog_for_user(entries, user, enabled_only=enabled_only)
    elif enabled_only:
        entries = [entry for entry in entries if entry.get("enabled")]

    apps = [entry.get("app_key") for entry in entries if entry.get("app_key")]
    actions = sorted(
        {
            action
            for entry in entries
            for action in (entry.get("supported_actions") or [])
            if action in ALLOWED_ACTIONS
        }
    )
    return {"apps": apps, "actions": actions, "entries": entries}


@app.get("/api/catalog")
def get_catalog(request: Request, enabled_only: bool = True):
    user = get_current_user(request)
    return build_catalog_response(user, enabled_only=enabled_only)


@app.get("/api/app-catalog")
def list_app_catalog(request: Request, enabled_only: bool = False):
    user = get_current_user(request)
    if user.get("role") == "viewer":
        enabled_only = True
    return filter_catalog_for_user(load_app_catalog_entries(), user, enabled_only=enabled_only)


@app.post("/api/app-catalog")
def create_app_catalog(request: Request, payload: CreateAppCatalogRequest):
    user = get_current_user(request)
    return create_app_catalog_entry(payload, user)


@app.patch("/api/app-catalog/{app_id}")
def update_app_catalog(request: Request, app_id: str, payload: UpdateAppCatalogRequest):
    user = get_current_user(request)
    return update_app_catalog_entry(app_id, payload, user)


@app.put("/api/app-catalog/{app_id}")
def put_app_catalog(request: Request, app_id: str, payload: UpdateAppCatalogRequest):
    user = get_current_user(request)
    return update_app_catalog_entry(app_id, payload, user)


@app.post("/api/app-catalog/{app_id}/enable")
def enable_app_catalog(request: Request, app_id: str):
    user = get_current_user(request)
    return set_app_catalog_enabled(app_id, True, user)


@app.post("/api/app-catalog/{app_id}/disable")
def disable_app_catalog(request: Request, app_id: str):
    user = get_current_user(request)
    return set_app_catalog_enabled(app_id, False, user)


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
def update_tenant(tenant_id: str, request: UpdateTenantRequest, actor=None):
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
            log_audit(
                "TENANT_UPDATED",
                f"Company {tenant.get('company_name')} was updated.",
                company_id=tenant.get("company_id"),
                company_name=tenant.get("company_name"),
                actor=actor,
                target_type="tenant",
                target_label=tenant.get("company_id"),
                metadata={"company_name": tenant.get("company_name"), "status": tenant.get("status")},
            )
            return tenant

    raise HTTPException(status_code=404, detail="Tenant not found")


@app.post("/api/admin/companies")
def create_company(request: CreateTenantRequest, actor=None):
    return get_or_create_company(request.company_name, actor=actor)


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
    matching_jobs = [
        job
        for job in jobs
        if isinstance(job, dict)
        and job.get("status") == "approved"
        and job.get("company_id") == company_id
        and job.get("device_id") in {device_id, "any"}
    ]
    audit_updated = False
    for job in matching_jobs:
        if not job.get("audit_started_at"):
            job["audit_started_at"] = utc_now()
            audit_updated = True
            log_audit(
                "JOB_STARTED",
                f"Agent fetched job {job.get('id')} for processing",
                company_id=job.get("company_id"),
                company_name=job.get("company_name"),
                device_id=device_id,
                request_id=job.get("source_request_id"),
                job_id=job.get("id"),
                target_type="job",
                target_label=job.get("id"),
                metadata={"app": job.get("app"), "action": job.get("action"), "status": job.get("status")},
            )
    if audit_updated:
        save_jobs(jobs)
    return matching_jobs


@app.post("/api/agent/jobs")
def create_job(request: CreateJobRequest, actor=None):
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
    app_catalog_entry = get_available_catalog_entry(
        request.app,
        request.action,
        company_id=company_id,
        user=actor,
    )

    return create_executable_job(
        app=app_catalog_entry.get("app_key"),
        action=request.action,
        device_id=request.device_id,
        company_id=company_id,
        company_name=company_name,
        actor=actor,
        app_catalog_entry=app_catalog_entry,
    )


def create_executable_job(
    app,
    action,
    device_id,
    company_id,
    company_name,
    created_by_user_id=None,
    created_by_username=None,
    approved_by_user_id=None,
    approved_by_username=None,
    source_request_id=None,
    actor=None,
    app_catalog_entry=None,
):
    if app_catalog_entry is None:
        app_catalog_entry = get_available_catalog_entry(app, action, company_id=company_id, user=actor)
    snapshot = app_catalog_to_agent_snapshot(app_catalog_entry)
    jobs = load_jobs()
    job = {
        "id": f"job-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}",
        "company_id": company_id,
        "company_name": company_name,
        "device_id": device_id,
        "app": app,
        "app_key": snapshot.get("app_key"),
        "display_name": snapshot.get("display_name"),
        "winget_id": snapshot.get("winget_id"),
        "detection_id": snapshot.get("detection_id"),
        "action": action,
        "status": "approved",
        "created_by_user_id": created_by_user_id,
        "created_by_username": created_by_username,
        "approved_by_user_id": approved_by_user_id,
        "approved_by_username": approved_by_username,
        "source_request_id": source_request_id,
        "created_at": utc_now(),
        "started_at": None,
        "finished_at": None,
        "last_error": None,
        "message": None,
        "attempts": 0,
    }
    jobs.append(job)
    save_jobs(jobs)
    log_audit(
        "JOB_CREATED",
        f"Executable job created for {app} {action}",
        company_id=company_id,
        company_name=company_name,
        actor=actor,
        device_id=None if device_id == "any" else device_id,
        request_id=source_request_id,
        job_id=job.get("id"),
        target_type="any_approved_device" if device_id == "any" else "specific_device",
        target_label=device_id,
        metadata={"app": app, "action": action},
    )
    return job


@app.post("/api/agent/jobs/{job_id}/result")
def post_job_result(job_id: str, result: JobResultRequest):
    jobs = load_jobs()
    for job in jobs:
        if isinstance(job, dict) and job.get("id") == job_id:
            previous_audit_status = job.get("audit_result_status")
            update = result.dict(exclude_unset=True)
            job.update(update)
            result_status = job.get("status")
            event_type = AUDIT_JOB_RESULT_EVENTS.get(result_status)
            if event_type and previous_audit_status != result_status:
                job["audit_result_status"] = result_status
                log_audit(
                    event_type,
                    f"Job {job_id} finished with status {result_status}",
                    company_id=job.get("company_id"),
                    company_name=job.get("company_name"),
                    device_id=job.get("device_id") if job.get("device_id") != "any" else None,
                    request_id=job.get("source_request_id"),
                    job_id=job_id,
                    target_type="job",
                    target_label=job_id,
                    metadata={
                        "app": job.get("app"),
                        "action": job.get("action"),
                        "status": result_status,
                        "message": job.get("message"),
                        "last_error": job.get("last_error"),
                    },
                )
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
    log_audit(
        "DEVICE_ENROLLED",
        f"Device {request.device_id} enrolled for {company.get('company_name')}",
        company_id=company.get("company_id"),
        company_name=company.get("company_name"),
        device_id=request.device_id,
        target_type="device",
        target_label=request.hostname or request.device_id,
        metadata={"hostname": request.hostname, "username": request.username, "os": request.os},
    )
    log_audit(
        "DEVICE_HEARTBEAT_FIRST_SEEN",
        f"First heartbeat received from device {request.device_id}",
        company_id=company.get("company_id"),
        company_name=company.get("company_name"),
        device_id=request.device_id,
        target_type="device",
        target_label=request.hostname or request.device_id,
        metadata={"agent_version": request.agent_version, "status": request.status},
    )
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
    sorted_devices = sorted(
        devices,
        key=lambda device: device.get("last_seen_at", "") if isinstance(device, dict) else "",
        reverse=True,
    )
    return enrich_devices_with_inventory(sorted_devices)


@app.get("/api/devices/{device_id}")
def get_device(device_id: str):
    devices = load_devices()
    for device in devices:
        if isinstance(device, dict) and device.get("device_id") == device_id:
            return device

    raise HTTPException(status_code=404, detail="Device not found")


@app.post("/api/admin/devices/{device_id}/approve")
def approve_device(device_id: str, actor=None):
    devices = load_devices()
    for device in devices:
        if isinstance(device, dict) and device.get("device_id") == device_id:
            device["approval_status"] = "approved"
            save_devices(devices)
            log_audit(
                "DEVICE_APPROVED",
                f"Device {device_id} approved",
                company_id=device.get("company_id"),
                company_name=device.get("company_name"),
                actor=actor,
                device_id=device_id,
                target_type="device",
                target_label=device.get("hostname") or device_id,
            )
            return device

    raise HTTPException(status_code=404, detail="Device not found")


@app.post("/api/admin/devices/{device_id}/reject")
def reject_device(device_id: str, actor=None):
    devices = load_devices()
    for device in devices:
        if isinstance(device, dict) and device.get("device_id") == device_id:
            device["approval_status"] = "rejected"
            save_devices(devices)
            log_audit(
                "DEVICE_REJECTED",
                f"Device {device_id} rejected",
                company_id=device.get("company_id"),
                company_name=device.get("company_name"),
                actor=actor,
                device_id=device_id,
                target_type="device",
                target_label=device.get("hostname") or device_id,
            )
            return device

    raise HTTPException(status_code=404, detail="Device not found")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8008)
