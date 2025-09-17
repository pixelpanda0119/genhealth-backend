"""
GenHealthAI - Document Processing REST API
A production-ready FastAPI application for processing medical documents
"""

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import uvicorn
from contextlib import asynccontextmanager
import logging
from datetime import datetime

# Import our modules
from app.database import engine, Base, get_db
from app.routers import orders, documents, auth
from app.services.activity_logger import ActivityLogger

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Rate limiting
limiter = Limiter(key_func=get_remote_address)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    # Startup
    logger.info("Starting GenHealthAI API...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified")
    
    yield
    
    # Shutdown
    logger.info("Shutting down GenHealthAI API...")

# Create FastAPI app
app = FastAPI(
    title="GenHealthAI Document Processing API",
    description="A production-ready REST API for processing medical documents and extracting patient information",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Add rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["authentication"])
app.include_router(orders.router, prefix="/api/v1/orders", tags=["orders"])
app.include_router(documents.router, prefix="/api/v1/documents", tags=["documents"])

@app.get("/")
@limiter.limit("10/minute")
async def root(request: Request):
    """Root endpoint with API information - publicly accessible"""
    return {
        "message": "GenHealthAI Document Processing API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/health")
@limiter.limit("30/minute")
async def health_check(request: Request):
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Enhanced global exception handler with proper error tracking"""
    import uuid
    import traceback
    
    # Generate unique error ID for tracking
    error_id = str(uuid.uuid4())
    
    # Log the error with full context
    logger.error(
        f"Unhandled exception {error_id}: {type(exc).__name__} in {request.method} {request.url.path}",
        extra={
            "error_id": error_id,
            "endpoint": str(request.url.path),
            "method": request.method,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "stack_trace": traceback.format_exc()
        },
        exc_info=True
    )
    
    # Try to log the error activity (but don't fail if this fails)
    try:
        db = next(get_db())
        activity_logger = ActivityLogger(db)
        await activity_logger.log_activity(
            endpoint=str(request.url.path),
            method=request.method,
            status_code=500,
            error_message=f"[{error_id}] {str(exc)}"
        )
    except Exception as log_error:
        logger.error(f"Failed to log error activity: {log_error}")
    
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred. Please try again later.",
                "error_id": error_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        }
    )

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
