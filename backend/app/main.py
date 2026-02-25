# backend/app/main.py
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy import text
import uvicorn
from app.core.config import BACKEND_HOST, BACKEND_PORT
from app.db.session import engine

from app.api.routers.health import router as health_router
from app.api.routers.users import router as users_router
from app.api.routers.timesheets import router as timesheets_router
from app.api.routers.projects import router as projects_router
from app.api.routers.approvals import router as approvals_router
from app.api.routers.invoices import router as invoices_router
from app.api.routers.reports import router as reports_router
from app.api.routers.ai import router as ai_router
from app.api.routers.copilot import router as copilot_router
from app.api.routers.audit import router as audit_router
from app.api.routers.search import router as search_router


app = FastAPI(title="ERP PM Module API")
logger = logging.getLogger("app.exceptions")


def _log_exception(request: Request, exc: Exception) -> None:
    logger.error(
        "Request failed: %s %s",
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    _log_exception(request, exc)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    _log_exception(request, exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(health_router)
app.include_router(users_router)
app.include_router(timesheets_router)
app.include_router(projects_router)
app.include_router(approvals_router)
app.include_router(invoices_router)
app.include_router(reports_router)
app.include_router(ai_router)
app.include_router(copilot_router)
app.include_router(audit_router)
app.include_router(search_router)

@app.on_event("startup")
def _ensure_schema_compatibility() -> None:
    # Lightweight safeguard for environments without Alembic migrations.
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE timesheets ADD COLUMN IF NOT EXISTS employee_name VARCHAR(200)"
            )
        )

def run():
    uvicorn.run("app.main:app", host=BACKEND_HOST, port=BACKEND_PORT, reload=True)

if __name__ == "__main__":
    run()
