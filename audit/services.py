"""
Thamarayyath Employee Portal — Audit Logging Service.

Provides a single `audit_log()` function used throughout the codebase.
All writes are append-only. Never call .update() or .delete() on AuditLog.
"""

import logging
from typing import Optional, Any

logger = logging.getLogger("portal")


def audit_log(
    *,
    actor,
    action: str,
    target_model: str = "",
    target_id: str = "",
    ip_address: Optional[str] = None,
    status: str = "SUCCESS",
    extra: Optional[dict] = None,
):
    """
    Create an immutable audit log entry.

    Parameters
    ----------
    actor       : CustomUser instance or None (for anonymous/system events)
    action      : One of AuditLog.Action choices
    target_model: Model class name affected by the event
    target_id   : PK or identifier of the affected record
    ip_address  : Client IP address (from middleware context or request)
    status      : "SUCCESS" or "FAILURE"
    extra       : Additional metadata dict (do NOT include passwords or full PII)
    """
    from .models import AuditLog
    from accounts.middleware import get_current_ip, clean_ip

    if ip_address is None:
        ip_address = get_current_ip()
    ip_address = clean_ip(ip_address)

    actor_username = ""
    if actor is not None:
        actor_username = getattr(actor, "username", str(actor))

    safe_extra = {}
    if extra:
        # Sanitise: strip any accidentally included sensitive keys
        BLOCKED_KEYS = {"password", "new_password", "token", "secret", "session"}
        safe_extra = {
            k: v for k, v in extra.items()
            if k.lower() not in BLOCKED_KEYS
        }

    try:
        AuditLog.objects.create(
            actor=actor if actor and actor.pk else None,
            actor_username=actor_username,
            action=action,
            target_model=target_model,
            target_id=str(target_id),
            ip_address=ip_address,
            status=status,
            extra=safe_extra,
        )
    except Exception as exc:
        # Audit failures must not crash the main application
        logger.error("AuditLog write failed: %s action=%s", exc, action)
