"""HTTP routes. All business logic lives in the packages these import."""

from backend.api import (
    admin_routes,
    auth_routes,
    classroom_routes,
    dashboard_routes,
    diagnostic_routes,
    health,
    qa_routes,
    socratic_routes,
)

ROUTERS = [
    health.router,
    auth_routes.router,
    admin_routes.router,
    classroom_routes.router,
    qa_routes.router,
    socratic_routes.router,
    diagnostic_routes.router,
    dashboard_routes.router,
]

__all__ = ["ROUTERS"]
