"""Application roles and permission helpers."""

ALL_PERMISSIONS: list[str] = [
    "servers.read",
    "servers.manage",
    "servers.sync",
    "knowledge.read",
    "knowledge.manage",
    "migrator.manage",
    "users.manage",
    "roles.manage",
    "settings.manage",
]

PERMISSION_LABELS: dict[str, str] = {
    "servers.read": "View Jamf server connections",
    "servers.manage": "Create, edit, and delete Jamf servers",
    "servers.sync": "Run manual sync jobs",
    "knowledge.read": "View knowledge sources and scrape jobs",
    "knowledge.manage": "Start, control, and delete scrape jobs and sources",
    "migrator.manage": "Run Jamf object migrations",
    "users.manage": "Create, update, and delete users",
    "roles.manage": "Create, update, and delete custom roles",
    "settings.manage": "Access the settings area",
}

DEFAULT_ADMIN_ROLE = {
    "name": "Administrator",
    "description": "Full access to all application management features.",
    "permissions": ALL_PERMISSIONS,
}

DEFAULT_VIEWER_ROLE = {
    "name": "Viewer",
    "description": "Read-only application access.",
    "permissions": [
        "servers.read",
        "knowledge.read",
        "settings.manage",
    ],
}
