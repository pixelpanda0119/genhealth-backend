"""
User service for authentication and user management
Handles all user-related business logic
"""

from sqlalchemy.orm import Session
from sqlalchemy import or_
from fastapi import HTTPException, status
from datetime import datetime, timedelta
from typing import Optional
import logging

from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, UserUpdate, PasswordChange
from app.auth.auth_handler import AuthHandler
from app.utils.error_handler import DatabaseError

logger = logging.getLogger(__name__)

class UserService:
    """Service for user management operations"""
    
    def __init__(self, db: Session):
        self.db = db
        self.auth_handler = AuthHandler()
    
    async def create_user(self, user_data: UserCreate) -> User:
        """Create a new user account"""
        try:
            # Check if username already exists
            existing_user = self.db.query(User).filter(
                or_(
                    User.username == user_data.username.lower(),
                    User.email == user_data.email.lower()
                )
            ).first()
            
            if existing_user:
                if existing_user.username == user_data.username.lower():
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Username already registered"
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Email already registered"
                    )
            
            # Hash the password
            hashed_password = self.auth_handler.get_password_hash(user_data.password)
            
            # Create user object
            db_user = User(
                username=user_data.username.lower(),
                email=user_data.email.lower(),
                hashed_password=hashed_password,
                first_name=user_data.first_name,
                last_name=user_data.last_name,
                role=user_data.role,
                phone_number=user_data.phone_number,
                organization=user_data.organization,
                license_number=user_data.license_number,
                is_active=True,
                is_verified=False  # Require email verification in production
            )
            
            self.db.add(db_user)
            self.db.commit()
            self.db.refresh(db_user)
            
            logger.info(f"Created new user: {db_user.username} ({db_user.email})")
            return db_user
            
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to create user: {e}")
            raise DatabaseError(f"Failed to create user account: {str(e)}", e)
    
    async def authenticate_user(self, login_data: UserLogin) -> Optional[User]:
        """Authenticate user credentials"""
        try:
            # Find user by username or email
            user = self.db.query(User).filter(
                or_(
                    User.username == login_data.username_or_email.lower(),
                    User.email == login_data.username_or_email.lower()
                )
            ).first()
            
            if not user:
                logger.warning(f"Login attempt with non-existent user: {login_data.username_or_email}")
                return None
            
            if not user.is_active:
                logger.warning(f"Login attempt with inactive user: {user.username}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Account is deactivated"
                )
            
            # Verify password
            if not self.auth_handler.verify_password(login_data.password, user.hashed_password):
                logger.warning(f"Failed login attempt for user: {user.username}")
                return None
            
            # Update last login time
            user.last_login = datetime.utcnow()
            self.db.commit()
            
            logger.info(f"Successful login for user: {user.username}")
            return user
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            raise DatabaseError(f"Authentication failed: {str(e)}", e)
    
    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID"""
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            return user
        except Exception as e:
            logger.error(f"Failed to get user by ID {user_id}: {e}")
            return None
    
    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username"""
        try:
            user = self.db.query(User).filter(User.username == username.lower()).first()
            return user
        except Exception as e:
            logger.error(f"Failed to get user by username {username}: {e}")
            return None
    
    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        try:
            user = self.db.query(User).filter(User.email == email.lower()).first()
            return user
        except Exception as e:
            logger.error(f"Failed to get user by email {email}: {e}")
            return None
    
    async def update_user(self, user_id: int, user_data: UserUpdate) -> User:
        """Update user information"""
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )
            
            # Check if email is being changed and if it conflicts
            if user_data.email and user_data.email.lower() != user.email:
                existing_user = self.db.query(User).filter(
                    User.email == user_data.email.lower(),
                    User.id != user_id
                ).first()
                if existing_user:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Email already registered by another user"
                    )
            
            # Update fields
            update_data = user_data.dict(exclude_unset=True)
            for field, value in update_data.items():
                if field == 'email' and value:
                    setattr(user, field, value.lower())
                else:
                    setattr(user, field, value)
            
            user.updated_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(user)
            
            logger.info(f"Updated user: {user.username}")
            return user
            
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to update user {user_id}: {e}")
            raise DatabaseError(f"Failed to update user: {str(e)}", e)
    
    async def change_password(self, user_id: int, password_data: PasswordChange) -> bool:
        """Change user password"""
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )
            
            # Verify current password
            if not self.auth_handler.verify_password(password_data.current_password, user.hashed_password):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Current password is incorrect"
                )
            
            # Hash new password
            new_hashed_password = self.auth_handler.get_password_hash(password_data.new_password)
            
            # Update password
            user.hashed_password = new_hashed_password
            user.updated_at = datetime.utcnow()
            self.db.commit()
            
            logger.info(f"Password changed for user: {user.username}")
            return True
            
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to change password for user {user_id}: {e}")
            raise DatabaseError(f"Failed to change password: {str(e)}", e)
    
    async def deactivate_user(self, user_id: int) -> bool:
        """Deactivate user account"""
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )
            
            user.is_active = False
            user.updated_at = datetime.utcnow()
            self.db.commit()
            
            logger.info(f"Deactivated user: {user.username}")
            return True
            
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to deactivate user {user_id}: {e}")
            raise DatabaseError(f"Failed to deactivate user: {str(e)}", e)
    
    async def activate_user(self, user_id: int) -> bool:
        """Activate user account"""
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )
            
            user.is_active = True
            user.updated_at = datetime.utcnow()
            self.db.commit()
            
            logger.info(f"Activated user: {user.username}")
            return True
            
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to activate user {user_id}: {e}")
            raise DatabaseError(f"Failed to activate user: {str(e)}", e)
    
    async def verify_user_email(self, user_id: int) -> bool:
        """Mark user email as verified"""
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )
            
            user.is_verified = True
            user.updated_at = datetime.utcnow()
            self.db.commit()
            
            logger.info(f"Verified email for user: {user.username}")
            return True
            
        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to verify user {user_id}: {e}")
            raise DatabaseError(f"Failed to verify user: {str(e)}", e)
    
    async def get_users_paginated(self, page: int = 1, page_size: int = 10, role: Optional[str] = None, active_only: bool = True) -> tuple[list[User], int]:
        """Get paginated list of users"""
        try:
            query = self.db.query(User)
            
            # Apply filters
            if role:
                query = query.filter(User.role == role)
            if active_only:
                query = query.filter(User.is_active == True)
            
            # Get total count
            total = query.count()
            
            # Apply pagination
            offset = (page - 1) * page_size
            users = query.order_by(User.created_at.desc()).offset(offset).limit(page_size).all()
            
            return users, total
            
        except Exception as e:
            logger.error(f"Failed to get users: {e}")
            raise DatabaseError(f"Failed to retrieve users: {str(e)}", e)
    
    async def search_users(self, search_term: str, page: int = 1, page_size: int = 10) -> tuple[list[User], int]:
        """Search users by name, username, or email"""
        try:
            search_pattern = f"%{search_term.lower()}%"
            
            query = self.db.query(User).filter(
                or_(
                    User.username.ilike(search_pattern),
                    User.email.ilike(search_pattern),
                    User.first_name.ilike(search_pattern),
                    User.last_name.ilike(search_pattern),
                    (User.first_name + ' ' + User.last_name).ilike(search_pattern)
                )
            )
            
            # Get total count
            total = query.count()
            
            # Apply pagination
            offset = (page - 1) * page_size
            users = query.order_by(User.created_at.desc()).offset(offset).limit(page_size).all()
            
            return users, total
            
        except Exception as e:
            logger.error(f"Failed to search users: {e}")
            raise DatabaseError(f"Failed to search users: {str(e)}", e)
