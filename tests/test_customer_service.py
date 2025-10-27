"""
Integration tests for Customer Service
"""
import pytest
import requests
# conftest.py functions and constants are automatically available
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import get_auth_headers, GATEWAY_BASE_URL


class TestCustomerService:
    """Test customer service endpoints"""
    
    def test_health_check_via_gateway(self):
        """Test health check through API Gateway"""
        headers = get_auth_headers("testuser")
        
        response = requests.get(f"{GATEWAY_BASE_URL}/customers/health", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "customer-service"
    
    def test_get_all_customers_via_gateway(self):
        """Test getting all customers through API Gateway"""
        headers = get_auth_headers("testuser")
        
        response = requests.get(f"{GATEWAY_BASE_URL}/customers", headers=headers)
        assert response.status_code == 200
        customers = response.json()
        assert isinstance(customers, list)
        assert len(customers) >= 8  # We have 8 mock customers
        
        # Check first customer structure
        customer = customers[0]
        assert "id" in customer
        assert "name" in customer
        assert "email" in customer
        assert "created_at" in customer
    
    def test_get_customer_by_id_via_gateway(self):
        """Test getting specific customer through API Gateway"""
        headers = get_auth_headers("testuser")
        
        response = requests.get(f"{GATEWAY_BASE_URL}/customers/7", headers=headers)
        assert response.status_code == 200
        customer = response.json()
        assert customer["id"] == 7
        assert customer["name"] == "John Doe"
        assert customer["email"] == "john.doe@example.com"
    
    def test_get_nonexistent_customer(self):
        """Test getting non-existent customer"""
        headers = get_auth_headers("testuser")
        
        response = requests.get(f"{GATEWAY_BASE_URL}/customers/999", headers=headers)
        assert response.status_code == 404
        error = response.json()
        assert "Customer not found" in error["detail"]
    
    def test_unauthorized_access_without_token(self):
        """Test that requests without token are rejected"""
        response = requests.get(f"{GATEWAY_BASE_URL}/customers")
        assert response.status_code == 401  # Unauthorized

    def test_unverified_user_blocked_from_customers(self):
        """Test that unverified users cannot access customer service"""
        headers = get_auth_headers("testuserUNV")
        
        # Should get 403 Forbidden (RBAC blocks unverified users)
        response = requests.get(f"{GATEWAY_BASE_URL}/customers", headers=headers)
        assert response.status_code == 403  # RBAC denial