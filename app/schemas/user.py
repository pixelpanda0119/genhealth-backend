"""
Pydantic schemas for user operations
"""

from pydantic import BaseModel, Field, validator, EmailStr
from typing import Optional
from datetime import datetime
import re

class UserBase(BaseModel):
    """Base user schema"""
    username: str = Field(..., min_length=3, max_length=50, description="Username (3-50 characters)")
    email: EmailStr = Field(..., description="Valid email address")
    first_name: str = Field(..., min_length=1, max_length=50, description="First name")
    last_name: str = Field(..., min_length=1, max_length=50, description="Last name")
    phone_number: Optional[str] = Field(None, max_length=20, description="Phone number")
    organization: Optional[str] = Field(None, max_length=100, description="Organization name")
    license_number: Optional[str] = Field(None, max_length=50, description="Professional license number")
    
    @validator('username')
    def validate_username(cls, v):
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('Username can only contain letters, numbers, underscores, and hyphens')
        return v.lower()
    
    @validator('phone_number')
    def validate_phone_number(cls, v):
        if v is None:
            return v
        # Remove all non-digit characters for validation
        digits_only = re.sub(r'\D', '', v)
        if len(digits_only) < 10 or len(digits_only) > 15:
            raise ValueError('Phone number must be between 10-15 digits')
        return v
    
    @validator('first_name', 'last_name')
    def validate_names(cls, v):
        if not re.match(r'^[a-zA-Z\s\'-]+$', v):
            raise ValueError('Names can only contain letters, spaces, hyphens, and apostrophes')
        return v.strip().title()

class UserCreate(UserBase):
    """Schema for creating a new user"""
    password: str = Field(..., min_length=8, max_length=128, description="Password (minimum 8 characters)")
    confirm_password: str = Field(..., description="Password confirmation")
    role: Optional[str] = Field("user", description="User role")
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        
        # Check for at least one uppercase, one lowercase, one digit
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one digit')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('Password must contain at least one special character')
        
        return v
    
    @validator('confirm_password')
    def passwords_match(cls, v, values, **kwargs):
        if 'password' in values and v != values['password']:
            raise ValueError('Passwords do not match')
        return v
    
    @validator('role')
    def validate_role(cls, v):
        allowed_roles = ['user', 'healthcare_worker', 'admin']
        if v not in allowed_roles:
            raise ValueError(f'Role must be one of: {", ".join(allowed_roles)}')
        return v

class UserLogin(BaseModel):
    """Schema for user login"""
    username_or_email: str = Field(..., description="Username or email address")
    password: str = Field(..., description="Password")
    
    @validator('username_or_email')
    def validate_username_or_email(cls, v):
        v = v.strip().lower()
        if not v:
            raise ValueError('Username or email is required')
        return v

class UserUpdate(BaseModel):
    """Schema for updating user information"""
    first_name: Optional[str] = Field(None, min_length=1, max_length=50)
    last_name: Optional[str] = Field(None, min_length=1, max_length=50)
    email: Optional[EmailStr] = Field(None)
    phone_number: Optional[str] = Field(None, max_length=20)
    organization: Optional[str] = Field(None, max_length=100)
    license_number: Optional[str] = Field(None, max_length=50)
    
    @validator('first_name', 'last_name')
    def validate_names(cls, v):
        if v is None:
            return v
        if not re.match(r'^[a-zA-Z\s\'-]+$', v):
            raise ValueError('Names can only contain letters, spaces, hyphens, and apostrophes')
        return v.strip().title()
    
    @validator('phone_number')
    def validate_phone_number(cls, v):
        if v is None:
            return v
        digits_only = re.sub(r'\D', '', v)
        if len(digits_only) < 10 or len(digits_only) > 15:
            raise ValueError('Phone number must be between 10-15 digits')
        return v

class PasswordChange(BaseModel):
    """Schema for password change"""
    current_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=8, max_length=128, description="New password")
    confirm_new_password: str = Field(..., description="Confirm new password")
    
    @validator('new_password')
    def validate_new_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one digit')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('Password must contain at least one special character')
        
        return v
    
    @validator('confirm_new_password')
    def passwords_match(cls, v, values, **kwargs):
        if 'new_password' in values and v != values['new_password']:
            raise ValueError('New passwords do not match')
        return v

class UserResponse(UserBase):
    """Schema for user responses (excludes sensitive data)"""
    id: int
    role: str
    is_active: bool
    is_verified: bool
    last_login: Optional[datetime]
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    """Schema for authentication token response"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse

class UserListResponse(BaseModel):
    """Schema for paginated user list response"""
    users: list[UserResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
