"""CardCue backend application."""

import copy
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from cardcue_api.api.billing import router as billing_router
from cardcue_api.api.devices import router as devices_router
from cardcue_api.api.sync import router as sync_router
from cardcue_api.api.mail import router as mail_router
from cardcue_api.api.drafts import router as drafts_router

from cardcue_api.admin.auth_api import router as admin_auth_router
from cardcue_api.admin.config_api import router as admin_config_router
from cardcue_api.admin.jobs import router as admin_jobs_router
from cardcue_api.admin.business_api import router as admin_business_router

from cardcue_api.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings.validate_production()
    yield


app = FastAPI(
    title="CardCue",
    version="0.5.0",
    lifespan=lifespan,
)

# CORS configuration for Web Admin
origins = [settings.public_origin.rstrip("/")]
if settings.environment != "production":
    origins.extend([
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["x-csrf-token"],
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next) -> Response:
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Avoid caching sensitive administration endpoints
    if request.url.path.startswith("/v1/admin/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"

    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Sanitize sensitive fields from validation error details
    sensitive_keys = {"password", "new_password", "current_password", "auth_code", "api_key", "token"}
    errors = copy.deepcopy(exc.errors())
    for err in errors:
        loc = err.get("loc", ())
        if any(str(k).lower() in sensitive_keys for k in loc):
            if "input" in err:
                err["input"] = "[REDACTED]"
            if "msg" in err and any(str(k) in err["msg"] for k in sensitive_keys):
                err["msg"] = "Value is invalid"
    return JSONResponse(status_code=422, content={"detail": errors})


# Core API Routers
app.include_router(billing_router)
app.include_router(devices_router)
app.include_router(sync_router)
app.include_router(mail_router)
app.include_router(drafts_router)

# Admin API Routers
app.include_router(admin_auth_router)
app.include_router(admin_config_router)
app.include_router(admin_jobs_router)
app.include_router(admin_business_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "cardcue", "version": "0.5.0"}


@app.get("/v1/capabilities")
def capabilities() -> dict[str, bool | str]:
    return {
        "stage": "r1-delivery",
        "accounts": True,
        "statements": True,
        "payments": True,
        "device_auth": True,
        "sync": True,
        "email_sync": True,
        "statement_parsing": True,
        "backup_restore": True,
        "payment_execution": False,
        "web_admin": True,
    }
