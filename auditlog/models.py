"""
Thamarayyath Employee Portal — AuditLog Model Reference.
Transparently re-exports AuditLog from audit app for compatibility.
"""

from audit.models import AuditLog

__all__ = ["AuditLog"]

