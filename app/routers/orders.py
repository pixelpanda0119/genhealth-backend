"""
Order management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from typing import Optional
import logging
import math

from app.database import get_db
from app.models.order import Order
from app.schemas.order import OrderCreate, OrderUpdate, OrderResponse, OrderListResponse
from app.services.activity_logger import ActivityLogger
from app.auth.auth_handler import get_current_user, admin_required, user_required

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)

router = APIRouter()

@router.post("/", response_model=OrderResponse, status_code=201)
@limiter.limit("10/minute")
async def create_order(
    request: Request,
    order: OrderCreate,
    current_user: dict = Depends(user_required),
    db: Session = Depends(get_db)
):
    """Create a new order"""
    try:
        # Check if order number already exists
        existing_order = db.query(Order).filter(Order.order_number == order.order_number).first()
        if existing_order:
            raise HTTPException(
                status_code=400,
                detail=f"Order with number '{order.order_number}' already exists"
            )
        
        # Create new order
        db_order = Order(**order.dict())
        db.add(db_order)
        db.commit()
        db.refresh(db_order)
        
        logger.info(f"Created order with ID: {db_order.id}")
        return db_order
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create order: {e}")
        raise HTTPException(status_code=500, detail="Failed to create order")

@router.get("/", response_model=OrderListResponse)
@limiter.limit("30/minute")
async def get_orders(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by status"),
    order_type: Optional[str] = Query(None, description="Filter by order type"),
    current_user: dict = Depends(user_required),
    db: Session = Depends(get_db)
):
    """Get paginated list of orders with optional filtering"""
    try:
        # Build query
        query = db.query(Order)
        
        # Apply filters
        if status:
            query = query.filter(Order.status == status)
        if order_type:
            query = query.filter(Order.order_type == order_type)
        
        # Get total count
        total = query.count()
        
        # Apply pagination
        offset = (page - 1) * page_size
        orders = query.order_by(Order.created_at.desc()).offset(offset).limit(page_size).all()
        
        # Calculate total pages
        total_pages = math.ceil(total / page_size)
        
        return OrderListResponse(
            orders=orders,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
        
    except Exception as e:
        logger.error(f"Failed to get orders: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve orders")

@router.get("/{order_id}", response_model=OrderResponse)
@limiter.limit("30/minute")
async def get_order(
    request: Request,
    order_id: int,
    current_user: dict = Depends(user_required),
    db: Session = Depends(get_db)
):
    """Get a specific order by ID"""
    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        return order
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get order {order_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve order")

@router.put("/{order_id}", response_model=OrderResponse)
@limiter.limit("10/minute")
async def update_order(
    request: Request,
    order_id: int,
    order_update: OrderUpdate,
    current_user: dict = Depends(user_required),
    db: Session = Depends(get_db)
):
    """Update an existing order"""
    try:
        # Get existing order
        db_order = db.query(Order).filter(Order.id == order_id).first()
        if not db_order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        # Check if order number is being changed and if it conflicts
        if order_update.order_number and order_update.order_number != db_order.order_number:
            existing_order = db.query(Order).filter(
                Order.order_number == order_update.order_number,
                Order.id != order_id
            ).first()
            if existing_order:
                raise HTTPException(
                    status_code=400,
                    detail=f"Order with number '{order_update.order_number}' already exists"
                )
        
        # Update fields
        update_data = order_update.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_order, field, value)
        
        db.commit()
        db.refresh(db_order)
        
        logger.info(f"Updated order with ID: {order_id}")
        return db_order
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update order {order_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update order")

@router.delete("/{order_id}")
@limiter.limit("10/minute")
async def delete_order(
    request: Request,
    order_id: int,
    current_user: dict = Depends(admin_required),
    db: Session = Depends(get_db)
):
    """Delete an order"""
    try:
        # Get existing order
        db_order = db.query(Order).filter(Order.id == order_id).first()
        if not db_order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        db.delete(db_order)
        db.commit()
        
        logger.info(f"Deleted order with ID: {order_id}")
        return {"message": "Order deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete order {order_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete order")

@router.get("/search/by-patient")
@limiter.limit("20/minute")
async def search_orders_by_patient(
    request: Request,
    first_name: Optional[str] = Query(None, description="Patient first name"),
    last_name: Optional[str] = Query(None, description="Patient last name"),
    current_user: dict = Depends(user_required),
    db: Session = Depends(get_db)
):
    """Search orders by patient information"""
    try:
        if not first_name and not last_name:
            raise HTTPException(
                status_code=400,
                detail="At least one of first_name or last_name must be provided"
            )
        
        query = db.query(Order)
        
        if first_name:
            query = query.filter(Order.patient_first_name.ilike(f"%{first_name}%"))
        if last_name:
            query = query.filter(Order.patient_last_name.ilike(f"%{last_name}%"))
        
        orders = query.order_by(Order.created_at.desc()).all()
        
        return {"orders": orders, "count": len(orders)}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to search orders: {e}")
        raise HTTPException(status_code=500, detail="Failed to search orders")
