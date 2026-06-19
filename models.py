import json

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Company(Base):
    __tablename__ = "companies"

    company_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    def to_dict(self):
        return {
            "tenant_id": self.company_id,
            "company_id": self.company_id,
            "company_name": self.company_name,
            "slug": self.slug,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    company_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
    last_login_at: Mapped[str | None] = mapped_column(String, nullable=True)

    def to_dict(self):
        email = self.email or self.username
        return {
            "user_id": self.user_id,
            "username": self.username,
            "email": email,
            "password_hash": self.password_hash,
            "full_name": self.full_name or self.username,
            "role": self.role,
            "company_id": self.company_id,
            "tenant_id": self.company_id,
            "status": self.status or "active",
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_login_at": self.last_login_at,
        }


class Device(Base):
    __tablename__ = "devices"

    device_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(String, nullable=False)
    company_name: Mapped[str] = mapped_column(String, nullable=False)
    hostname: Mapped[str | None] = mapped_column(String, nullable=True)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    os: Mapped[str | None] = mapped_column(String, nullable=True)
    agent_name: Mapped[str | None] = mapped_column(String, nullable=True)
    agent_version: Mapped[str | None] = mapped_column(String, nullable=True)
    approval_status: Mapped[str] = mapped_column(String, nullable=False, default="pending_approval")
    connection_status: Mapped[str] = mapped_column(String, nullable=False, default="online")
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    last_seen_at: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    def to_dict(self):
        return {
            "device_id": self.device_id,
            "company_id": self.company_id,
            "company_name": self.company_name,
            "hostname": self.hostname,
            "username": self.username,
            "os": self.os,
            "agent_name": self.agent_name,
            "agent_version": self.agent_version,
            "approval_status": self.approval_status,
            "connection_status": self.connection_status,
            "status": self.status or self.connection_status,
            "last_seen_at": self.last_seen_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class AppRequest(Base):
    __tablename__ = "app_requests"

    request_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(String, nullable=False)
    company_name: Mapped[str] = mapped_column(String, nullable=False)
    device_id: Mapped[str | None] = mapped_column(String, nullable=True)
    target_device_id: Mapped[str] = mapped_column(String, nullable=False, default="any")
    target_type: Mapped[str] = mapped_column(String, nullable=False)
    app: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    requested_by_user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    requested_by_username: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    approved_by_user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    approved_by_username: Mapped[str | None] = mapped_column(String, nullable=True)
    rejected_by_user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    rejected_by_username: Mapped[str | None] = mapped_column(String, nullable=True)
    linked_job_id: Mapped[str | None] = mapped_column(String, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    def to_dict(self):
        return {
            "request_id": self.request_id,
            "company_id": self.company_id,
            "company_name": self.company_name,
            "device_id": self.device_id,
            "target_device_id": self.target_device_id,
            "target_type": self.target_type,
            "app": self.app,
            "action": self.action,
            "requested_by_user_id": self.requested_by_user_id,
            "requested_by_username": self.requested_by_username,
            "status": self.status,
            "approved_by_user_id": self.approved_by_user_id,
            "approved_by_username": self.approved_by_username,
            "rejected_by_user_id": self.rejected_by_user_id,
            "rejected_by_username": self.rejected_by_username,
            "linked_job_id": self.linked_job_id,
            "reason": self.reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class Job(Base):
    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(String, nullable=False)
    company_name: Mapped[str] = mapped_column(String, nullable=False)
    device_id: Mapped[str] = mapped_column(String, nullable=False, default="any")
    app: Mapped[str] = mapped_column(String, nullable=False)
    app_key: Mapped[str | None] = mapped_column(String, nullable=True)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    winget_id: Mapped[str | None] = mapped_column(String, nullable=True)
    detection_id: Mapped[str | None] = mapped_column(String, nullable=True)
    action: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by_username: Mapped[str | None] = mapped_column(String, nullable=True)
    approved_by_user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    approved_by_username: Mapped[str | None] = mapped_column(String, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[str | None] = mapped_column(String, nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String, nullable=True)
    audit_started_at: Mapped[str | None] = mapped_column(String, nullable=True)
    audit_result_status: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    def to_dict(self):
        return {
            "id": self.job_id,
            "job_id": self.job_id,
            "company_id": self.company_id,
            "company_name": self.company_name,
            "device_id": self.device_id,
            "app": self.app,
            "app_key": self.app_key or self.app,
            "display_name": self.display_name,
            "winget_id": self.winget_id,
            "detection_id": self.detection_id,
            "action": self.action,
            "status": self.status,
            "attempts": self.attempts,
            "message": self.message,
            "last_error": self.last_error,
            "created_by_user_id": self.created_by_user_id,
            "created_by_username": self.created_by_username,
            "approved_by_user_id": self.approved_by_user_id,
            "approved_by_username": self.approved_by_username,
            "source_request_id": self.request_id,
            "request_id": self.request_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "audit_started_at": self.audit_started_at,
            "audit_result_status": self.audit_result_status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class AppCatalog(Base):
    __tablename__ = "app_catalog"

    app_id: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    app_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    winget_id: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    supported_actions_json: Mapped[str] = mapped_column(Text, nullable=False)
    install_command_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    uninstall_command_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    detection_method: Mapped[str] = mapped_column(String, nullable=False, default="winget")
    detection_id: Mapped[str] = mapped_column(String, nullable=False)
    silent_install_supported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    silent_uninstall_supported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    scope: Mapped[str] = mapped_column(String, nullable=False, default="global")
    company_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by_username: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    def to_dict(self):
        try:
            supported_actions = json.loads(self.supported_actions_json)
        except json.JSONDecodeError:
            supported_actions = []
        if not isinstance(supported_actions, list):
            supported_actions = []

        return {
            "app_id": self.app_id,
            "display_name": self.display_name,
            "app_key": self.app_key,
            "winget_id": self.winget_id,
            "description": self.description,
            "supported_actions": supported_actions,
            "install_command_template": self.install_command_template,
            "uninstall_command_template": self.uninstall_command_template,
            "detection_method": self.detection_method,
            "detection_id": self.detection_id,
            "silent_install_supported": self.silent_install_supported,
            "silent_uninstall_supported": self.silent_uninstall_supported,
            "enabled": self.enabled,
            "scope": self.scope,
            "company_id": self.company_id,
            "created_by_user_id": self.created_by_user_id,
            "created_by_username": self.created_by_username,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class DeviceInstalledApp(Base):
    __tablename__ = "device_installed_apps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(String, nullable=False)
    device_id: Mapped[str] = mapped_column(String, nullable=False)
    app_key: Mapped[str | None] = mapped_column(String, nullable=True)
    catalog_app_id: Mapped[str | None] = mapped_column(String, nullable=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    detected_name: Mapped[str] = mapped_column(String, nullable=False)
    detected_id: Mapped[str | None] = mapped_column(String, nullable=True)
    version: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    install_location: Mapped[str | None] = mapped_column(String, nullable=True)
    detection_method: Mapped[str] = mapped_column(String, nullable=False, default="winget")
    is_catalog_match: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_seen_at: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "company_id": self.company_id,
            "device_id": self.device_id,
            "app_key": self.app_key,
            "catalog_app_id": self.catalog_app_id,
            "display_name": self.display_name,
            "detected_name": self.detected_name,
            "detected_id": self.detected_id,
            "version": self.version,
            "source": self.source,
            "install_location": self.install_location,
            "detection_method": self.detection_method,
            "is_catalog_match": self.is_catalog_match,
            "last_seen_at": self.last_seen_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class InventoryScanRun(Base):
    __tablename__ = "inventory_scan_runs"

    scan_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(String, nullable=False)
    device_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    apps_found_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    catalog_matches_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[str] = mapped_column(String, nullable=False)
    finished_at: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    def to_dict(self):
        return {
            "scan_id": self.scan_id,
            "company_id": self.company_id,
            "device_id": self.device_id,
            "status": self.status,
            "apps_found_count": self.apps_found_count,
            "catalog_matches_count": self.catalog_matches_count,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error_message": self.error_message,
        }


class AuditLog(Base):
    __tablename__ = "audit_logs"

    audit_id: Mapped[str] = mapped_column(String, primary_key=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    company_id: Mapped[str | None] = mapped_column(String, nullable=True)
    company_name: Mapped[str | None] = mapped_column(String, nullable=True)
    actor_user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    actor_username: Mapped[str | None] = mapped_column(String, nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String, nullable=True)
    device_id: Mapped[str | None] = mapped_column(String, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String, nullable=True)
    job_id: Mapped[str | None] = mapped_column(String, nullable=True)
    target_type: Mapped[str | None] = mapped_column(String, nullable=True)
    target_label: Mapped[str | None] = mapped_column(String, nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    def to_dict(self):
        try:
            metadata = json.loads(self.metadata_json) if self.metadata_json else {}
        except json.JSONDecodeError:
            metadata = {}

        return {
            "audit_id": self.audit_id,
            "event_type": self.event_type,
            "company_id": self.company_id,
            "company_name": self.company_name,
            "actor_user_id": self.actor_user_id,
            "actor_username": self.actor_username,
            "actor_role": self.actor_role,
            "device_id": self.device_id,
            "request_id": self.request_id,
            "job_id": self.job_id,
            "target_type": self.target_type,
            "target_label": self.target_label,
            "message": self.message,
            "metadata": metadata,
            "metadata_json": self.metadata_json,
            "created_at": self.created_at,
        }
