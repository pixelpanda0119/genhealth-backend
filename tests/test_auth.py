"""
Unit tests for authentication functionality
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from main import app

# Test database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_auth.db"

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

class TestUserRegistration:
    """Test cases for user registration"""
    
    def test_signup_success(self):
        """Test successful user registration"""
        user_data = {
            "username": "testuser",
            "email": "test@example.com",
            "password": "TestPass123!",
            "confirm_password": "TestPass123!",
            "first_name": "Test",
            "last_name": "User",
            "role": "user"
        }
        
        response = client.post("/api/v1/auth/signup", json=user_data)
        assert response.status_code == 201
        
        data = response.json()
        assert data["username"] == "testuser"
        assert data["email"] == "test@example.com"
        assert data["first_name"] == "Test"
        assert data["last_name"] == "User"
        assert data["role"] == "user"
        assert data["is_active"] == True
        assert data["is_verified"] == False
        assert "hashed_password" not in data  # Should not return password
    
    def test_signup_duplicate_username(self):
        """Test registration with duplicate username"""
        user_data = {
            "username": "duplicate",
            "email": "user1@example.com",
            "password": "TestPass123!",
            "confirm_password": "TestPass123!",
            "first_name": "User",
            "last_name": "One"
        }
        
        # Create first user
        response1 = client.post("/api/v1/auth/signup", json=user_data)
        assert response1.status_code == 201
        
        # Try to create user with same username
        user_data["email"] = "user2@example.com"
        response2 = client.post("/api/v1/auth/signup", json=user_data)
        assert response2.status_code == 400
        assert "Username already registered" in response2.json()["detail"]
    
    def test_signup_duplicate_email(self):
        """Test registration with duplicate email"""
        user_data = {
            "username": "user1",
            "email": "duplicate@example.com",
            "password": "TestPass123!",
            "confirm_password": "TestPass123!",
            "first_name": "User",
            "last_name": "One"
        }
        
        # Create first user
        response1 = client.post("/api/v1/auth/signup", json=user_data)
        assert response1.status_code == 201
        
        # Try to create user with same email
        user_data["username"] = "user2"
        response2 = client.post("/api/v1/auth/signup", json=user_data)
        assert response2.status_code == 400
        assert "Email already registered" in response2.json()["detail"]
    
    def test_signup_invalid_password(self):
        """Test registration with invalid passwords"""
        invalid_passwords = [
            "short",  # Too short
            "nouppercase123!",  # No uppercase
            "NOLOWERCASE123!",  # No lowercase
            "NoNumbers!",  # No numbers
            "NoSpecial123",  # No special characters
        ]
        
        for password in invalid_passwords:
            user_data = {
                "username": f"user_{password[:5]}",
                "email": f"{password[:5]}@example.com",
                "password": password,
                "confirm_password": password,
                "first_name": "Test",
                "last_name": "User"
            }
            
            response = client.post("/api/v1/auth/signup", json=user_data)
            assert response.status_code == 422  # Validation error
    
    def test_signup_password_mismatch(self):
        """Test registration with mismatched passwords"""
        user_data = {
            "username": "mismatch",
            "email": "mismatch@example.com",
            "password": "TestPass123!",
            "confirm_password": "DifferentPass123!",
            "first_name": "Test",
            "last_name": "User"
        }
        
        response = client.post("/api/v1/auth/signup", json=user_data)
        assert response.status_code == 422
    
    def test_signup_invalid_email(self):
        """Test registration with invalid email"""
        user_data = {
            "username": "invalidemail",
            "email": "not-an-email",
            "password": "TestPass123!",
            "confirm_password": "TestPass123!",
            "first_name": "Test",
            "last_name": "User"
        }
        
        response = client.post("/api/v1/auth/signup", json=user_data)
        assert response.status_code == 422

class TestUserLogin:
    """Test cases for user login"""
    
    def setup_method(self):
        """Set up test user for login tests"""
        self.test_user = {
            "username": "loginuser",
            "email": "login@example.com",
            "password": "LoginPass123!",
            "confirm_password": "LoginPass123!",
            "first_name": "Login",
            "last_name": "User"
        }
        
        # Create test user
        response = client.post("/api/v1/auth/signup", json=self.test_user)
        assert response.status_code == 201
    
    def test_login_with_username(self):
        """Test successful login with username"""
        login_data = {
            "username_or_email": "loginuser",
            "password": "LoginPass123!"
        }
        
        response = client.post("/api/v1/auth/login", json=login_data)
        assert response.status_code == 200
        
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == 1800
        assert "user" in data
        assert data["user"]["username"] == "loginuser"
    
    def test_login_with_email(self):
        """Test successful login with email"""
        login_data = {
            "username_or_email": "login@example.com",
            "password": "LoginPass123!"
        }
        
        response = client.post("/api/v1/auth/login", json=login_data)
        assert response.status_code == 200
        
        data = response.json()
        assert "access_token" in data
        assert data["user"]["email"] == "login@example.com"
    
    def test_login_wrong_password(self):
        """Test login with wrong password"""
        login_data = {
            "username_or_email": "loginuser",
            "password": "WrongPassword123!"
        }
        
        response = client.post("/api/v1/auth/login", json=login_data)
        assert response.status_code == 401
        assert "Invalid username/email or password" in response.json()["detail"]
    
    def test_login_nonexistent_user(self):
        """Test login with non-existent user"""
        login_data = {
            "username_or_email": "nonexistent",
            "password": "TestPass123!"
        }
        
        response = client.post("/api/v1/auth/login", json=login_data)
        assert response.status_code == 401
        assert "Invalid username/email or password" in response.json()["detail"]

class TestAuthenticatedEndpoints:
    """Test cases for authenticated endpoints"""
    
    def setup_method(self):
        """Set up authenticated user for tests"""
        # Create test user
        user_data = {
            "username": "authuser",
            "email": "auth@example.com",
            "password": "AuthPass123!",
            "confirm_password": "AuthPass123!",
            "first_name": "Auth",
            "last_name": "User"
        }
        
        signup_response = client.post("/api/v1/auth/signup", json=user_data)
        assert signup_response.status_code == 201
        
        # Login to get token
        login_data = {
            "username_or_email": "authuser",
            "password": "AuthPass123!"
        }
        
        login_response = client.post("/api/v1/auth/login", json=login_data)
        assert login_response.status_code == 200
        
        self.token = login_response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_current_user(self):
        """Test getting current user information"""
        response = client.get("/api/v1/auth/me", headers=self.headers)
        assert response.status_code == 200
        
        data = response.json()
        assert data["username"] == "authuser"
        assert data["email"] == "auth@example.com"
        assert data["first_name"] == "Auth"
        assert data["last_name"] == "User"
    
    def test_update_current_user(self):
        """Test updating current user information"""
        update_data = {
            "first_name": "Updated",
            "last_name": "Name",
            "phone_number": "+1234567890"
        }
        
        response = client.put("/api/v1/auth/me", json=update_data, headers=self.headers)
        assert response.status_code == 200
        
        data = response.json()
        assert data["first_name"] == "Updated"
        assert data["last_name"] == "Name"
        assert data["phone_number"] == "+1234567890"
    
    def test_change_password(self):
        """Test password change"""
        password_data = {
            "current_password": "AuthPass123!",
            "new_password": "NewPass123!",
            "confirm_new_password": "NewPass123!"
        }
        
        response = client.post("/api/v1/auth/change-password", json=password_data, headers=self.headers)
        assert response.status_code == 200
        assert "Password changed successfully" in response.json()["message"]
        
        # Test login with new password
        login_data = {
            "username_or_email": "authuser",
            "password": "NewPass123!"
        }
        
        login_response = client.post("/api/v1/auth/login", json=login_data)
        assert login_response.status_code == 200
    
    def test_change_password_wrong_current(self):
        """Test password change with wrong current password"""
        password_data = {
            "current_password": "WrongPass123!",
            "new_password": "NewPass123!",
            "confirm_new_password": "NewPass123!"
        }
        
        response = client.post("/api/v1/auth/change-password", json=password_data, headers=self.headers)
        assert response.status_code == 400
        assert "Current password is incorrect" in response.json()["detail"]
    
    def test_logout(self):
        """Test user logout"""
        response = client.post("/api/v1/auth/logout", headers=self.headers)
        assert response.status_code == 200
        assert "Successfully logged out" in response.json()["message"]
    
    def test_unauthorized_access(self):
        """Test access without token"""
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 403  # No authorization header
    
    def test_invalid_token(self):
        """Test access with invalid token"""
        invalid_headers = {"Authorization": "Bearer invalid_token"}
        response = client.get("/api/v1/auth/me", headers=invalid_headers)
        assert response.status_code == 401

if __name__ == "__main__":
    pytest.main([__file__])
