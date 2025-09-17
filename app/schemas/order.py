"""
Pydantic schemas for Order operations
"""

from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime
import re

class OrderBase(BaseModel):
    """Base order schema"""
    order_number: str = Field(..., min_length=1, max_length=50, description="Unique order number")
    patient_first_name: Optional[str] = Field(None, max_length=100, description="Patient's first name")
    patient_last_name: Optional[str] = Field(None, max_length=100, description="Patient's last name")
    patient_date_of_birth: Optional[str] = Field(None, description="Patient's date of birth (YYYY-MM-DD or MM/DD/YYYY)")
    order_type: str = Field(..., min_length=1, max_length=50, description="Type of order")
    status: Optional[str] = Field("pending", description="Order status")
    total_amount: Optional[float] = Field(None, ge=0, description="Total amount for the order")
    notes: Optional[str] = Field(None, description="Additional notes")

    @validator('patient_date_of_birth')
    def validate_date_of_birth(cls, v):
        if v is None:
            return v
        
        # Accept various date formats
        date_patterns = [
            r'^\d{4}-\d{2}-\d{2}$',  # YYYY-MM-DD
            r'^\d{2}/\d{2}/\d{4}$',  # MM/DD/YYYY
            r'^\d{1,2}/\d{1,2}/\d{4}$',  # M/D/YYYY
        ]
        
        if not any(re.match(pattern, v) for pattern in date_patterns):
            raise ValueError('Date of birth must be in format YYYY-MM-DD or MM/DD/YYYY')
        
        return v

    @validator('status')
    def validate_status(cls, v):
        allowed_statuses = ['pending', 'confirmed', 'processing', 'shipped', 'delivered', 'cancelled']
        if v not in allowed_statuses:
            raise ValueError(f'Status must be one of: {", ".join(allowed_statuses)}')
        return v

class OrderCreate(OrderBase):
    """Schema for creating a new order"""
    pass

class OrderUpdate(BaseModel):
    """Schema for updating an existing order"""
    order_number: Optional[str] = Field(None, min_length=1, max_length=50)
    patient_first_name: Optional[str] = Field(None, max_length=100)
    patient_last_name: Optional[str] = Field(None, max_length=100)
    patient_date_of_birth: Optional[str] = Field(None)
    order_type: Optional[str] = Field(None, min_length=1, max_length=50)
    status: Optional[str] = Field(None)
    total_amount: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = Field(None)

    @validator('patient_date_of_birth')
    def validate_date_of_birth(cls, v):
        if v is None:
            return v
        
        date_patterns = [
            r'^\d{4}-\d{2}-\d{2}$',
            r'^\d{2}/\d{2}/\d{4}$',
            r'^\d{1,2}/\d{1,2}/\d{4}$',
        ]
        
        if not any(re.match(pattern, v) for pattern in date_patterns):
            raise ValueError('Date of birth must be in format YYYY-MM-DD or MM/DD/YYYY')
        
        return v

    @validator('status')
    def validate_status(cls, v):
        if v is None:
            return v
        allowed_statuses = ['pending', 'confirmed', 'processing', 'shipped', 'delivered', 'cancelled']
        if v not in allowed_statuses:
            raise ValueError(f'Status must be one of: {", ".join(allowed_statuses)}')
        return v

class OrderResponse(OrderBase):
    """Schema for order responses"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True

class OrderListResponse(BaseModel):
    """Schema for paginated order list responses"""
    orders: list[OrderResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
