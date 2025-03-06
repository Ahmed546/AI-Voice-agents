from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import logging
import time
import sentry_sdk
from prometheus_client import Counter, Histogram
from prometheus_client import make_asgi_app

from app.api import voice, webhook, admin
from app.db.database import engine, Base
from app.utils.logger import setup_logging
from app.config import settings

# Initialize Sentry for production error tracking
if settings.ENVIRONMENT == "production":
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        traces_sample_rate=0.2,
        environment=settings.ENVIRONMENT,
    )

# Setup logging
logger = setup_logging()

# Create tables in the database
Base.metadata.create_all(bind=engine)

# Initialize FastAPI app
app = FastAPI(
    title="Restaurant AI Voice Agent",
    description="AI-powered voice agent for restaurant orders and reservations",
    version="1.0.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics
REQUEST_COUNT = Counter(
    "http_requests_total", "Total HTTP Requests", ["method", "endpoint", "status"]
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds", "HTTP Request Latency", ["method", "endpoint"]
)

# Add Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Middleware for request timing and metrics
@app.middleware("http")
async def add_metrics(request: Request, call_next):
    start_time = time.time()
    
    # Process the request
    response = await call_next(request)
    
    # Record metrics
    duration = time.time() - start_time
    REQUEST_LATENCY.labels(request.method, request.url.path).observe(duration)
    REQUEST_COUNT.labels(request.method, request.url.path, response.status_code).inc()
    
    # Add processing time header
    response.headers["X-Process-Time"] = str(duration)
    
    return response

# Register API routers
app.include_router(voice.router, prefix="/api/voice", tags=["voice"])
app.include_router(webhook.router, prefix="/api/webhook", tags=["webhook"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])

@app.get("/", tags=["health"])
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": app.version,
        "environment": settings.ENVIRONMENT
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)