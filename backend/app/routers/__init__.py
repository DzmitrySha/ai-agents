"""API routers."""

from app.auth.oidc import router as auth_router
from app.routers.admin import router as admin_router
from app.routers.agents import router as agents_router
from app.routers.assist import router as assist_router
from app.routers.catalog import router as catalog_router
from app.routers.doctor import router as doctor_router
from app.routers.mcp_connections import router as mcp_connections_router
from app.routers.mcp_servers import router as mcp_servers_router
from app.routers.memory import router as memory_router
from app.routers.notifications import router as notifications_router
from app.routers.packs import router as packs_router
from app.routers.runs import router as runs_router
from app.routers.schedules import router as schedules_router
from app.routers.settings import router as settings_router
from app.routers.skills import router as skills_router
from app.routers.stats import router as stats_router
from app.routers.tools import router as tools_router

__all__ = [
    "admin_router",
    "agents_router",
    "assist_router",
    "auth_router",
    "catalog_router",
    "doctor_router",
    "mcp_connections_router",
    "mcp_servers_router",
    "memory_router",
    "notifications_router",
    "packs_router",
    "runs_router",
    "schedules_router",
    "settings_router",
    "skills_router",
    "stats_router",
    "tools_router",
]
