"""
Authentication endpoints for user login, signup, and account management
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from datetime import timedelta
import logging
import math

from app.database import get_db
from app.schemas.user import (
    UserCreate, UserLogin, UserUpdate, PasswordChange, 
    UserResponse, TokenResponse, UserListResponse
)
from app.services.user_service import UserService
from app.auth.auth_handler import AuthHandler, get_current_user, admin_required
from app.services.activity_logger import ActivityLogger

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)

router = APIRouter()

@router.post("/signup", response_model=UserResponse, status_code=201)
@limiter.limit("5/minute")  # Strict limit to prevent spam registrations
async def signup(
    request: Request,
    user_data: UserCreate,
    db: Session = Depends(get_db)
):
    """Register a new user account"""
    try:
        user_service = UserService(db)
        
        # Create the user
        new_user = await user_service.create_user(user_data)
        
        # Log the activity
        activity_logger = ActivityLogger(db)
        await activity_logger.log_activity(
            endpoint="/api/v1/auth/signup",
            method="POST",
            status_code=201,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent")
        )
        
        logger.info(f"New user registered: {new_user.username}")
        return new_user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Signup failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user account"
        )

@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")  # Prevent brute force attacks
async def login(
    request: Request,
    login_data: UserLogin,
    db: Session = Depends(get_db)
):
    """Authenticate user and return access token"""
    try:
        user_service = UserService(db)
        auth_handler = AuthHandler()

        # Authenticate user
        user = await user_service.authenticate_user(login_data)
        
        if not user:
            # Log failed login attempt
            activity_logger = ActivityLogger(db)
            await activity_logger.log_activity(
                endpoint="/api/v1/auth/login",
                method="POST",
                status_code=401,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
                error_message=f"Failed login attempt for: {login_data.username_or_email}"
            )
            
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username/email or password"
            )
        
        # Create access token
        access_token_expires = timedelta(minutes=30)  # 30 minutes
        token_data = {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role,
            "email": user.email
        }
        access_token = auth_handler.create_access_token(
            data=token_data,
            expires_delta=access_token_expires
        )
        
        # Log successful login
        activity_logger = ActivityLogger(db)
        await activity_logger.log_activity(
            endpoint="/api/v1/auth/login",
            method="POST",
            status_code=200,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent")
        )
        
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=1800,  # 30 minutes in seconds
            user=UserResponse.from_orm(user)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )

@router.get("/me", response_model=UserResponse)
@limiter.limit("30/minute")
async def get_current_user_info(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user information"""
    try:
        user_service = UserService(db)
        user = await user_service.get_user_by_id(int(current_user["user_id"]))
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return UserResponse.from_orm(user)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get current user info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user information"
        )

@router.put("/me", response_model=UserResponse)
@limiter.limit("10/minute")
async def update_current_user(
    request: Request,
    user_data: UserUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update current user information"""
    try:
        user_service = UserService(db)
        updated_user = await user_service.update_user(int(current_user["user_id"]), user_data)
        
        logger.info(f"User updated their profile: {updated_user.username}")
        return UserResponse.from_orm(updated_user)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user information"
        )

@router.post("/change-password")
@limiter.limit("5/minute")  # Strict limit for password changes
async def change_password(
    request: Request,
    password_data: PasswordChange,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Change user password"""
    try:
        user_service = UserService(db)
        success = await user_service.change_password(int(current_user["user_id"]), password_data)
        
        if success:
            # Log password change
            activity_logger = ActivityLogger(db)
            await activity_logger.log_activity(
                endpoint="/api/v1/auth/change-password",
                method="POST",
                status_code=200,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent")
            )
            
            logger.info(f"Password changed for user: {current_user['username']}")
            return {"message": "Password changed successfully"}
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to change password"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password change failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to change password"
        )

@router.post("/logout")
@limiter.limit("30/minute")
async def logout(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Logout user (client should discard token)"""
    try:
        # Log logout activity
        activity_logger = ActivityLogger(db)
        await activity_logger.log_activity(
            endpoint="/api/v1/auth/logout",
            method="POST",
            status_code=200,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent")
        )
        
        logger.info(f"User logged out: {current_user['username']}")
        return {"message": "Successfully logged out"}
        
    except Exception as e:
        logger.error(f"Logout failed: {e}")
        return {"message": "Logged out"}  # Always return success for logout

# Admin endpoints
@router.get("/users", response_model=UserListResponse)
@limiter.limit("20/minute")
async def get_users(
    request: Request,
    page: int = 1,
    page_size: int = 10,
    role: str = None,
    active_only: bool = True,
    current_user: dict = Depends(admin_required),
    db: Session = Depends(get_db)
):
    """Get paginated list of users (Admin only)"""
    try:
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 100:
            page_size = 10
        
        user_service = UserService(db)
        users, total = await user_service.get_users_paginated(page, page_size, role, active_only)
        
        total_pages = math.ceil(total / page_size)
        
        return UserListResponse(
            users=[UserResponse.from_orm(user) for user in users],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get users: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve users"
        )

@router.get("/users/search")
@limiter.limit("20/minute")
async def search_users(
    request: Request,
    q: str,
    page: int = 1,
    page_size: int = 10,
    current_user: dict = Depends(admin_required),
    db: Session = Depends(get_db)
):
    """Search users by name, username, or email (Admin only)"""
    try:
        if not q or len(q.strip()) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Search term must be at least 2 characters"
            )
        
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 100:
            page_size = 10
        
        user_service = UserService(db)
        users, total = await user_service.search_users(q.strip(), page, page_size)
        
        total_pages = math.ceil(total / page_size)
        
        return UserListResponse(
            users=[UserResponse.from_orm(user) for user in users],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"User search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search failed"
        )

@router.post("/users/{user_id}/deactivate")
@limiter.limit("10/minute")
async def deactivate_user(
    request: Request,
    user_id: int,
    current_user: dict = Depends(admin_required),
    db: Session = Depends(get_db)
):
    """Deactivate a user account (Admin only)"""
    try:
        # Prevent admin from deactivating themselves
        if int(current_user["user_id"]) == user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate your own account"
            )
        
        user_service = UserService(db)
        success = await user_service.deactivate_user(user_id)
        
        if success:
            logger.info(f"Admin {current_user['username']} deactivated user ID: {user_id}")
            return {"message": "User deactivated successfully"}
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deactivate user"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to deactivate user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deactivate user"
        )

@router.post("/users/{user_id}/activate")
@limiter.limit("10/minute")
async def activate_user(
    request: Request,
    user_id: int,
    current_user: dict = Depends(admin_required),
    db: Session = Depends(get_db)
):
    """Activate a user account (Admin only)"""
    try:
        user_service = UserService(db)
        success = await user_service.activate_user(user_id)
        
        if success:
            logger.info(f"Admin {current_user['username']} activated user ID: {user_id}")
            return {"message": "User activated successfully"}
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to activate user"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to activate user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to activate user"
        )
