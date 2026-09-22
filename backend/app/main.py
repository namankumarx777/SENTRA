from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.ingestion import router as ingestion_router
from app.api.rules import findings_router, router as rules_router
from app.api.execution_gap import router as execution_gap_router
from app.api.negative_space import router as negative_space_router
from app.api.peer_anomaly import router as peer_anomaly_router
from app.api.supervisory_risk import router as supervisory_risk_router
from app.api.blockchain import router as blockchain_router
from app.config import settings

from app.api.security import PathTraversalError, PayloadSizeLimitMiddleware
from app.logging import setup_logging, LoggingMiddleware
from app.analytics.store import PhaseNotFoundError

setup_logging()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
)
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:;"
        )
        return response

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(PayloadSizeLimitMiddleware)
app.add_middleware(LoggingMiddleware)

# CORSMiddleware must be added last so it is the outermost middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(PathTraversalError)
async def path_traversal_exception_handler(request: Request, exc: PathTraversalError):
    return JSONResponse(status_code=400, content={"detail": "Invalid or disallowed path provided"})

@app.exception_handler(PhaseNotFoundError)
async def phase_not_found_exception_handler(request: Request, exc: PhaseNotFoundError):
    return JSONResponse(status_code=404, content={"detail": "Requested record or phase dataset not found"})

@app.exception_handler(ValueError)
async def value_error_exception_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=422, content={"detail": "Unprocessable entity or invalid input"})
app.include_router(ingestion_router)
app.include_router(rules_router)
app.include_router(findings_router)
app.include_router(execution_gap_router)
app.include_router(negative_space_router)
app.include_router(peer_anomaly_router)
app.include_router(supervisory_risk_router)
app.include_router(blockchain_router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "SENTRA API",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "SENTRA",
        "environment": settings.environment,
    }