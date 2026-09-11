import logging
import time
import uuid

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings, require_persistent_database
from app.core.rate_limit import RateLimitMiddleware
from app.database import Base, engine
from app.routers import auth, demo, health, pipeline, resources

settings = get_settings()

# Guard against the login-persistence bug regressing: raises in production,
# warns everywhere else. See app/config.py for the full explanation.
require_persistent_database(settings)

class _RequestIdDefaultFilter(logging.Filter):
    """Ensures %(request_id)s never KeyErrors for log calls that don't pass one."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True


logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s %(levelname)s request_id=%(request_id)s %(name)s %(message)s",
)
for _handler in logging.getLogger().handlers:
    _handler.addFilter(_RequestIdDefaultFilter())
logger = logging.getLogger("rauzr")
logger.info(
    "Startup config: env=%s railway=%s database=%s cors_origins=%s",
    settings.ENV,
    settings.is_railway,
    "postgres" if settings.DATABASE_URL.startswith("postgres") else settings.DATABASE_URL,
    settings.cors_origin_list,
)

app = FastAPI(
    title=settings.APP_NAME,
    description="API for Rauzr Technologies Pvt Ltd -- an AI workspace for pharma CMC / GxP regulatory compliance.",
    version="0.1.0",
    docs_url="/api/docs" if not settings.is_production else None,
    redoc_url=None,
)

# --- Database bootstrap ---
# For an MVP scaffold, create_all() is sufficient. Once the schema needs to
# evolve safely against live data, switch to Alembic migrations -- see
# README "Limitations & Future Work".
Base.metadata.create_all(bind=engine)

# Idempotent: only inserts resources whose slug isn't already present, so
# this is safe to run on every boot (including every Railway redeploy).
# Keeps the public /resources hub populated with real editorial content
# without a manual seeding step.
from scripts.seed_resources import main as _seed_resources  # noqa: E402

_seed_resources()

# --- CORS: only the configured origins may call the API from a browser ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.add_middleware(RateLimitMiddleware)


@app.middleware("http")
async def add_request_id_and_security_headers(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start) * 1000, 1)

    # Baseline security headers. Fronting this with a CDN/proxy (Railway's
    # edge, Cloudflare, etc.) that terminates TLS and adds HSTS is still
    # recommended for production -- see README.
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Request-ID"] = request_id

    logger.info(
        "%s %s -> %s (%sms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        extra={"request_id": request_id},
    )
    return response


# --- Consistent JSON error shape across the API ---


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": f"HTTP_{exc.status_code}"},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    fields = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", []) if part != "body")
        message = error.get("msg", "Invalid value")
        fields.append(f"{location}: {message}" if location else message)
    detail = "Invalid request payload."
    if fields:
        detail = f"Invalid request payload: {'; '.join(fields)}"
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": detail, "code": "VALIDATION_ERROR", "errors": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Never leak stack traces / internals to the client.
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred. Please try again.", "code": "INTERNAL_ERROR"},
    )


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(demo.router)
app.include_router(pipeline.router)
app.include_router(resources.router)


@app.get("/api")
def root():
    return {"name": settings.APP_NAME, "status": "ok", "docs": "/api/docs"}
