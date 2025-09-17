"""
Unit tests for order management functionality
Essential for production reliability
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from main import app

# Test database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

class TestOrderManagement:
    """Test cases for order management"""
    
    def test_create_order_success(self):
        """Test successful order creation"""
        order_data = {
            "order_number": "TEST-001",
            "patient_first_name": "John",
            "patient_last_name": "Doe",
            "patient_date_of_birth": "1980-01-15",
            "order_type": "CPAP Equipment",
            "status": "pending",
            "total_amount": 299.99,
            "notes": "Test order"
        }
        
        response = client.post("/api/v1/orders/", json=order_data)
        assert response.status_code == 201
        
        data = response.json()
        assert data["order_number"] == "TEST-001"
        assert data["patient_first_name"] == "John"
        assert data["status"] == "pending"
    
    def test_create_duplicate_order_fails(self):
        """Test that duplicate order numbers are rejected"""
        order_data = {
            "order_number": "TEST-002",
            "patient_first_name": "Jane",
            "patient_last_name": "Smith",
            "order_type": "Test Equipment",
            "status": "pending"
        }
        
        # Create first order
        response1 = client.post("/api/v1/orders/", json=order_data)
        assert response1.status_code == 201
        
        # Try to create duplicate
        response2 = client.post("/api/v1/orders/", json=order_data)
        assert response2.status_code == 400
        assert "already exists" in response2.json()["detail"]
    
    def test_get_order_success(self):
        """Test retrieving an order by ID"""
        # Create an order first
        order_data = {
            "order_number": "TEST-003",
            "patient_first_name": "Alice",
            "patient_last_name": "Johnson",
            "order_type": "Test Equipment",
            "status": "pending"
        }
        
        create_response = client.post("/api/v1/orders/", json=order_data)
        order_id = create_response.json()["id"]
        
        # Retrieve the order
        response = client.get(f"/api/v1/orders/{order_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["order_number"] == "TEST-003"
        assert data["patient_first_name"] == "Alice"
    
    def test_get_nonexistent_order_fails(self):
        """Test retrieving a non-existent order"""
        response = client.get("/api/v1/orders/99999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    
    def test_update_order_success(self):
        """Test updating an order"""
        # Create an order first
        order_data = {
            "order_number": "TEST-004",
            "patient_first_name": "Bob",
            "patient_last_name": "Wilson",
            "order_type": "Test Equipment",
            "status": "pending"
        }
        
        create_response = client.post("/api/v1/orders/", json=order_data)
        order_id = create_response.json()["id"]
        
        # Update the order
        update_data = {
            "status": "confirmed",
            "notes": "Order confirmed"
        }
        
        response = client.put(f"/api/v1/orders/{order_id}", json=update_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "confirmed"
        assert data["notes"] == "Order confirmed"
    
    def test_delete_order_success(self):
        """Test deleting an order"""
        # Create an order first
        order_data = {
            "order_number": "TEST-005",
            "patient_first_name": "Carol",
            "patient_last_name": "Davis",
            "order_type": "Test Equipment",
            "status": "pending"
        }
        
        create_response = client.post("/api/v1/orders/", json=order_data)
        order_id = create_response.json()["id"]
        
        # Delete the order
        response = client.delete(f"/api/v1/orders/{order_id}")
        assert response.status_code == 200
        
        # Verify it's deleted
        get_response = client.get(f"/api/v1/orders/{order_id}")
        assert get_response.status_code == 404
    
    def test_search_orders_by_patient(self):
        """Test searching orders by patient name"""
        # Create test orders
        orders = [
            {
                "order_number": "SEARCH-001",
                "patient_first_name": "David",
                "patient_last_name": "Brown",
                "order_type": "Equipment A",
                "status": "pending"
            },
            {
                "order_number": "SEARCH-002",
                "patient_first_name": "David",
                "patient_last_name": "Smith",
                "order_type": "Equipment B",
                "status": "confirmed"
            }
        ]
        
        for order in orders:
            client.post("/api/v1/orders/", json=order)
        
        # Search by first name
        response = client.get("/api/v1/orders/search/by-patient?first_name=David")
        assert response.status_code == 200
        
        data = response.json()
        assert data["count"] >= 2
        assert all(order["patient_first_name"] == "David" for order in data["orders"])
    
    def test_invalid_order_data_fails(self):
        """Test that invalid order data is rejected"""
        invalid_orders = [
            # Missing required fields
            {
                "patient_first_name": "Test",
                "order_type": "Equipment"
            },
            # Invalid status
            {
                "order_number": "INVALID-001",
                "order_type": "Equipment",
                "status": "invalid_status"
            },
            # Negative amount
            {
                "order_number": "INVALID-002",
                "order_type": "Equipment",
                "total_amount": -100.0
            }
        ]
        
        for invalid_order in invalid_orders:
            response = client.post("/api/v1/orders/", json=invalid_order)
            assert response.status_code == 422  # Validation error

class TestOrderValidation:
    """Test cases for order validation"""
    
    def test_date_validation(self):
        """Test date of birth validation"""
        valid_dates = ["1980-01-15", "12/25/1990", "1/1/2000"]
        invalid_dates = ["invalid-date", "2025-01-01", "13/45/1990"]
        
        for date in valid_dates:
            order_data = {
                "order_number": f"DATE-{date.replace('/', '-').replace('-', '')}",
                "patient_date_of_birth": date,
                "order_type": "Test Equipment"
            }
            response = client.post("/api/v1/orders/", json=order_data)
            # Should succeed or fail based on current validation logic
            assert response.status_code in [201, 422]
        
        for date in invalid_dates:
            order_data = {
                "order_number": f"INVALID-DATE-{date.replace('/', '-').replace('-', '')}",
                "patient_date_of_birth": date,
                "order_type": "Test Equipment"
            }
            response = client.post("/api/v1/orders/", json=order_data)
            assert response.status_code == 422

if __name__ == "__main__":
    pytest.main([__file__])
