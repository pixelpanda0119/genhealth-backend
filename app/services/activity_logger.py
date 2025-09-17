"""
Activity logging service for tracking all user activities
"""

from sqlalchemy.orm import Session
from app.models.activity_log import ActivityLog
import json
from typing import Optional

class ActivityLogger:
    """Service for logging user activities"""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def log_activity(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_body: Optional[dict] = None,
        response_time_ms: Optional[int] = None,
        error_message: Optional[str] = None
    ) -> Optional[ActivityLog]:
        """Log an activity to the database with proper error handling"""
        
        try:
            # Convert request body to JSON string if provided
            request_body_str = None
            if request_body:
                try:
                    request_body_str = json.dumps(request_body)
                except (TypeError, ValueError):
                    request_body_str = str(request_body)
            
            activity_log = ActivityLog(
                endpoint=endpoint,
                method=method,
                status_code=status_code,
                ip_address=ip_address,
                user_agent=user_agent,
                request_body=request_body_str,
                response_time_ms=response_time_ms,
                error_message=error_message
            )
            
            self.db.add(activity_log)
            self.db.commit()
            self.db.refresh(activity_log)
            
            return activity_log
            
        except Exception as e:
            # Log the error but don't fail the main operation
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to log activity: {e}")
            
            # Rollback the transaction
            try:
                self.db.rollback()
            except Exception:
                pass  # If rollback fails, there's not much we can do
            
            return None
    
    def get_recent_activities(self, limit: int = 100) -> list[ActivityLog]:
        """Get recent activities"""
        return (
            self.db.query(ActivityLog)
            .order_by(ActivityLog.created_at.desc())
            .limit(limit)
            .all()
        )
