from fastapi import FastAPI, HTTPException, Depends, status
from typing import List
from datetime import datetime
import os
import sys
sys.path.append('/app')

from models.customer import Customer, CustomerCreate, CustomerResponse
from shared.common import setup_logging, create_health_response
from shared.auth import get_current_user, JWTPayload

# Setup logging
logger = setup_logging("customer-service")

app = FastAPI(
    title="Customer Service",
    description="Microservice for managing customers",
    version="1.0.0"
)

# Mock data for now (will be replaced with database)
customers_db = [
    Customer(
        id=1,
        name="Test UserUNV",
        email="testuserUNV@example.com",
        phone="+1234567891",
        created_at=datetime.now()
    ),
    Customer(
        id=2,
        name="Test User",
        email="testuser@example.com",
        phone="+1234567892",
        created_at=datetime.now()
    ),
    Customer(
        id=3,
        name="Admin User",
        email="adminuser@example.com",
        phone="+1234567893",
        created_at=datetime.now()
    ),
    Customer(
        id=4,
        name="Test UserCM",
        email="testuserCM@example.com",
        phone="+1234567894",
        created_at=datetime.now()
    ),
    Customer(
        id=5,
        name="Test UserPM",
        email="testuserPM@example.com",
        phone="+1234567895",
        created_at=datetime.now()
    ),
    Customer(
        id=6,
        name="Test UserPCM",
        email="testuserPCM@example.com",
        phone="+1234567896",
        created_at=datetime.now()
    ),
    Customer(
        id=7,
        name="John Doe",
        email="john.doe@example.com",
        phone="+1234567897",
        created_at=datetime.now()
    ),
    Customer(
        id=8,
        name="Jane Smith",
        email="jane.smith@example.com",
        phone="+1234567898",
        created_at=datetime.now()
    )
]

@app.get("/customers/health")
def health_check():
    """Health check endpoint"""
    logger.info("Health check requested")
    return create_health_response("customer-service")

@app.get("/customers", response_model=List[CustomerResponse])
def get_customers():
    """Get all customers"""
    logger.info(f"Fetching all customers. Count: {len(customers_db)}")
    return customers_db

@app.get("/customers/{customer_id}", response_model=CustomerResponse)
def get_customer(customer_id: int, current_user: JWTPayload = Depends(get_current_user)):
    """
    Get a specific customer by ID
    
    Authorization:
    - Users with 'customer-manager' role can retrieve any customer
    - Other users can only retrieve their own customer record (email must match)
    """
    logger.info(f"Fetching customer with ID: {customer_id} (requested by: {current_user.email})")
    
    # Find the customer
    customer = next((c for c in customers_db if c.id == customer_id), None)
    if not customer:
        logger.warning(f"Customer not found with ID: {customer_id}")
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Check authorization
    # 1. If user has 'customer-manager' role, they can view any customer
    if current_user.has_role("customer-manager"):
        logger.info(f"Access granted: User {current_user.email} has customer-manager role")
        return customer
    
    # 2. Otherwise, check if the customer email matches the user's email
    if customer.email.lower() == current_user.email.lower():
        logger.info(f"Access granted: User {current_user.email} accessing their own record")
        return customer
 
    # 3. Deny access - user is not a customer-manager and email doesn't match
    logger.warning(
     f"Access denied: User {current_user.email} attempted to access customer {customer_id} "
     f"(customer email: {customer.email})"
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied: You can only view your own customer information"
    )

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("SERVICE_PORT", 8000))
    logger.info(f"Starting customer service on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)