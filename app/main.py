"""Change-Aware Auditor - FastAPI Application."""
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os
import logging
import time

from app.config import settings
from app.api.routes import router

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup."""
    logger.info("Starting Change-Aware Auditor")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Log level: {settings.log_level}")
    if settings.akashml_api_key:
        logger.info("AkashML API key configured")
    else:
        logger.warning("AKASHML_API_KEY not set - API calls will fail")

    # Security: Block wildcard CORS in production
    if "*" in settings.cors_origins_list:
        if settings.environment == "production":
            logger.critical(
                "FATAL: CORS_ALLOWED_ORIGINS is set to '*' in production! "
                "This allows any website to make requests to your API. "
                "Set specific domains in CORS_ALLOWED_ORIGINS or set ENVIRONMENT=development."
            )
            raise RuntimeError(
                "Wildcard CORS ('*') is not allowed in production. "
                "Set CORS_ALLOWED_ORIGINS to specific domains."
            )
        else:
            logger.warning(
                "CORS_ALLOWED_ORIGINS is set to '*'. "
                "This is acceptable for development but will be blocked in production."
            )
    yield
    logger.info("Shutting down Change-Aware Auditor")


app = FastAPI(
    title="Change-Aware Auditor",
    description="AI-powered code change analysis with evidence-backed findings",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware for cross-origin requests
# Security: Don't allow credentials with wildcard origins (browser security requirement)
_cors_origins = settings.cors_origins_list
_allow_credentials = "*" not in _cors_origins  # Credentials not allowed with wildcard

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests with timing information."""
    start_time = time.time()

    # Log request
    logger.info(f"Request: {request.method} {request.url.path}")

    response = await call_next(request)

    # Calculate request duration
    duration = time.time() - start_time
    logger.info(f"Response: {response.status_code} ({duration:.2f}s)")

    return response


# Get the base directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Mount static files
static_dir = os.path.join(BASE_DIR, "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Templates
templates_dir = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=templates_dir)

# Include API routes
app.include_router(router, prefix="/api/v1")


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Serve the web UI."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "change-aware-auditor",
        "version": "1.0.0",
        "environment": settings.environment,
        "api_configured": bool(settings.akashml_api_key)
    }
