"""
Enhanced error handling utilities for production-ready error management
"""

import uuid
import traceback
import logging
from typing import Optional, Dict, Any, Union
from datetime import datetime
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

class ErrorContext:
    """Context object for tracking error information across the request lifecycle"""
    
    def __init__(self, request: Request):
        self.request_id = str(uuid.uuid4())
        self.request = request
        self.endpoint = str(request.url.path)
        self.method = request.method
        self.client_ip = self._get_client_ip()
        self.user_agent = request.headers.get("user-agent")
        self.timestamp = datetime.utcnow()
    
    def _get_client_ip(self) -> Optional[str]:
        """Extract client IP from request headers"""
        if "x-forwarded-for" in self.request.headers:
            return self.request.headers["x-forwarded-for"].split(",")[0].strip()
        elif "x-real-ip" in self.request.headers:
            return self.request.headers["x-real-ip"]
        elif self.request.client:
            return self.request.client.host
        return None

class DatabaseError(Exception):
    """Custom exception for database-related errors"""
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        self.message = message
        self.original_error = original_error
        super().__init__(self.message)

class ProcessingError(Exception):
    """Custom exception for document processing errors"""
    def __init__(self, message: str, error_code: str, original_error: Optional[Exception] = None):
        self.message = message
        self.error_code = error_code
        self.original_error = original_error
        super().__init__(self.message)

class ErrorHandler:
    """Centralized error handling service"""
    
    @staticmethod
    def create_error_response(
        error_context: ErrorContext,
        error: Exception,
        status_code: int = 500,
        error_code: Optional[str] = None,
        include_details: bool = False
    ) -> JSONResponse:
        """Create a standardized error response"""
        
        error_data = {
            "error": {
                "code": error_code or ErrorHandler._get_error_code(error),
                "message": ErrorHandler._get_user_friendly_message(error),
                "request_id": error_context.request_id,
                "timestamp": error_context.timestamp.isoformat(),
                "endpoint": error_context.endpoint,
                "method": error_context.method
            }
        }
        
        # Include detailed error information in development
        if include_details:
            error_data["error"]["details"] = {
                "original_error": str(error),
                "error_type": type(error).__name__,
                "stack_trace": traceback.format_exc()
            }
        
        # Log the error with full context
        ErrorHandler._log_error(error_context, error, status_code)
        
        return JSONResponse(
            status_code=status_code,
            content=error_data
        )
    
    @staticmethod
    def _get_error_code(error: Exception) -> str:
        """Generate appropriate error codes based on exception type"""
        if isinstance(error, HTTPException):
            return f"HTTP_{error.status_code}"
        elif isinstance(error, DatabaseError):
            return "DATABASE_ERROR"
        elif isinstance(error, ProcessingError):
            return error.error_code
        elif isinstance(error, ValueError):
            return "VALIDATION_ERROR"
        elif isinstance(error, FileNotFoundError):
            return "FILE_NOT_FOUND"
        elif isinstance(error, PermissionError):
            return "PERMISSION_DENIED"
        else:
            return "INTERNAL_ERROR"
    
    @staticmethod
    def _get_user_friendly_message(error: Exception) -> str:
        """Generate user-friendly error messages"""
        if isinstance(error, HTTPException):
            return error.detail
        elif isinstance(error, DatabaseError):
            return "A database error occurred. Please try again later."
        elif isinstance(error, ProcessingError):
            return error.message
        elif isinstance(error, ValueError):
            return "Invalid input provided. Please check your data and try again."
        elif isinstance(error, FileNotFoundError):
            return "The requested file was not found."
        elif isinstance(error, PermissionError):
            return "You don't have permission to perform this operation."
        else:
            return "An unexpected error occurred. Please try again later."
    
    @staticmethod
    def _log_error(error_context: ErrorContext, error: Exception, status_code: int):
        """Log error with comprehensive context"""
        logger.error(
            f"Error {error_context.request_id}: {type(error).__name__} in {error_context.method} {error_context.endpoint}",
            extra={
                "request_id": error_context.request_id,
                "endpoint": error_context.endpoint,
                "method": error_context.method,
                "status_code": status_code,
                "client_ip": error_context.client_ip,
                "user_agent": error_context.user_agent,
                "error_type": type(error).__name__,
                "error_message": str(error),
                "stack_trace": traceback.format_exc()
            }
        )

class DatabaseManager:
    """Context manager for safe database operations"""
    
    def __init__(self, db_session_factory):
        self.db_session_factory = db_session_factory
        self.db = None
    
    def __enter__(self) -> Session:
        try:
            self.db = self.db_session_factory()
            return self.db
        except Exception as e:
            raise DatabaseError(f"Failed to create database session: {str(e)}", e)
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.db:
            try:
                if exc_type is None:
                    self.db.commit()
                else:
                    self.db.rollback()
            except SQLAlchemyError as e:
                logger.error(f"Database transaction error: {e}")
                self.db.rollback()
                raise DatabaseError(f"Database transaction failed: {str(e)}", e)
            finally:
                self.db.close()
    
    def safe_execute(self, operation, *args, **kwargs):
        """Execute database operation with proper error handling"""
        try:
            return operation(*args, **kwargs)
        except IntegrityError as e:
            self.db.rollback()
            if "UNIQUE constraint failed" in str(e):
                raise DatabaseError("A record with this information already exists", e)
            else:
                raise DatabaseError("Database integrity constraint violation", e)
        except SQLAlchemyError as e:
            self.db.rollback()
            raise DatabaseError(f"Database operation failed: {str(e)}", e)

def handle_exceptions(include_details: bool = False):
    """Decorator for automatic exception handling in route handlers"""
    def decorator(func):
        async def wrapper(request: Request, *args, **kwargs):
            error_context = ErrorContext(request)
            try:
                return await func(request, *args, **kwargs)
            except HTTPException:
                # Let FastAPI handle HTTPExceptions normally
                raise
            except Exception as e:
                # Handle all other exceptions with our error handler
                if isinstance(e, (DatabaseError, ProcessingError)):
                    status_code = 500
                elif isinstance(e, ValueError):
                    status_code = 400
                elif isinstance(e, (FileNotFoundError, PermissionError)):
                    status_code = 403
                else:
                    status_code = 500
                
                return ErrorHandler.create_error_response(
                    error_context, e, status_code, include_details=include_details
                )
        return wrapper
    return decorator
