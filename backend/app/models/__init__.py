"""ORM models package — imports all models so Alembic can discover them."""

from app.models.ai import AiToolAuditLog, ChatMessage, ChatSession, PendingAction
from app.models.compliance import ComplianceResult, SecurityStatus
from app.models.dashboard_log import DashboardLog
from app.models.device import Device, DeviceApplication, DevicePolicy
from app.models.knowledge import KnowledgeDocument
from app.models.patch import PatchTitle
from app.models.policy import Policy
from app.models.role import Role
from app.models.scrape_job import ScrapeJob
from app.models.scrape_job_log import ScrapeJobLog
from app.models.server import JamfServer
from app.models.smart_group import SmartGroup
from app.models.user import User

__all__ = [
    "AiToolAuditLog",
    "ChatMessage",
    "ChatSession",
    "ComplianceResult",
    "DashboardLog",
    "Device",
    "DeviceApplication",
    "DevicePolicy",
    "JamfServer",
    "KnowledgeDocument",
    "PatchTitle",
    "PendingAction",
    "Policy",
    "Role",
    "SecurityStatus",
    "ScrapeJob",
    "ScrapeJobLog",
    "SmartGroup",
    "User",
]
