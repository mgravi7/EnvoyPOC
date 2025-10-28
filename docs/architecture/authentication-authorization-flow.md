# Authentication & Authorization Flow

This document illustrates the comprehensive authentication and authorization flow in the API Gateway POC, showing how security is implemented across multiple layers.

## Overview

The system implements a layered security approach:

1. **Authentication Layer**: Keycloak handles user authentication and JWT token issuance
2. **Gateway Authorization**: Envoy validates JWT tokens and enforces role-based routing
3. **Service Authorization**: Individual services implement business logic authorization
4. **Data Access Layer**: Secure data operations with clean separation of concerns

## Sequence Diagram

```mermaid
sequenceDiagram
    participant User as User<br/>(role: "user")
    participant Keycloak as Keycloak<br/>Identity Provider
    participant Envoy as Envoy Gateway<br/>API Gateway
    participant CustomerAPI as Customer Service<br/>FastAPI
    participant AuthModule as JWT Auth Module<br/>(shared/auth.py)
    participant DataAccess as Customer Data Access<br/>(customer_data_access.py)

    Note over User, DataAccess: Phase 1: Authentication with Keycloak
    
    User->>+Keycloak: POST /realms/api-gateway-poc/protocol/openid-connect/token<br/>client_id: test-client<br/>username: testuser<br/>password: testpass<br/>grant_type: password
    
    Keycloak->>Keycloak: Validate credentials<br/>Check user roles
    
    Keycloak->>-User: Return JWT Token<br/>{ "email": "testuser@example.com",<br/>  "realm_access": { "roles": ["user"] },<br/>  "exp": 1761529888, ... }

  Note over User, DataAccess: Phase 2: API Request with JWT

    User->>+Envoy: GET /customers/2<br/>Authorization: Bearer <jwt_token>
    
    Note over Envoy: Envoy Gateway Authorization Layer
    
    Envoy->>Envoy: Extract JWT from Authorization header
    
    Envoy->>+Keycloak: Validate JWT signature<br/>GET /realms/api-gateway-poc/protocol/openid-connect/certs
    Keycloak->>-Envoy: Return JWKS (public keys)
 
    Envoy->>Envoy: Verify JWT signature<br/>Check token expiration<br/>Extract user roles: ["user"]
    
    alt JWT Invalid or Expired
      Envoy->>User: 401 Unauthorized<br/>Invalid or expired token
 else JWT Valid but Missing Required Role
   Envoy->>User: 403 Forbidden<br/>Insufficient permissions
    else JWT Valid with "user" Role
        Note over Envoy: JWT valid, "user" role present - forward request
        Envoy->>+CustomerAPI: GET /customers/2<br/>Authorization: Bearer <jwt_token><br/>(request forwarded)
        
      Note over CustomerAPI, DataAccess: Phase 3: Service-Level Authorization

     CustomerAPI->>+AuthModule: get_current_user(authorization_header)
     
  AuthModule->>AuthModule: Extract Bearer token<br/>Split JWT into parts<br/>Base64 decode payload
        
        AuthModule->>AuthModule: Parse JWT payload:<br/>{ "email": "testuser@example.com",<br/>  "realm_access": { "roles": ["user"] } }
        
        AuthModule->>-CustomerAPI: Return JWTPayload object<br/>email: testuser@example.com<br/>roles: ["user"]

        CustomerAPI->>CustomerAPI: Log: "Fetching customer ID: 2<br/>(requested by: testuser@example.com)"

 Note over CustomerAPI: Business Logic Authorization Check

        CustomerAPI->>+DataAccess: get_customer_by_id(2)
        DataAccess->>DataAccess: Search mock database<br/>for customer ID: 2
        DataAccess->>-CustomerAPI: Return Customer object<br/>{ id: 2, email: "testuser@example.com", ... }

        alt Customer Not Found
            CustomerAPI->>User: 404 Not Found<br/>"Customer not found"
    else Customer Found - Check Authorization
        CustomerAPI->>CustomerAPI: Check if user has<br/>"customer-manager" role
  
            alt User has "customer-manager" role
          CustomerAPI->>CustomerAPI: Log: "Access granted:<br/>customer-manager role"
  CustomerAPI->>User: 200 OK<br/>Return customer data
     else User email matches customer email
 CustomerAPI->>CustomerAPI: Compare emails (case-insensitive):<br/>JWT email: "testuser@example.com"<br/>Customer email: "testuser@example.com"
   CustomerAPI->>CustomerAPI: Log: "Access granted:<br/>user accessing own record"
           CustomerAPI->>User: 200 OK<br/>Return customer data
            else Access Denied
     CustomerAPI->>CustomerAPI: Log: "Access denied:<br/>email mismatch"
   CustomerAPI->>User: 403 Forbidden<br/>"Access denied: You can only view<br/>your own customer information"
        end
        end
        CustomerAPI->>-Envoy: Response sent
    end
    Envoy->>-User: Final response delivered

    Note over User, DataAccess: Security Layers Summary:<br/>1. Keycloak: Authentication & Role Assignment<br/>2. Envoy: JWT Validation & Role-Based Routing<br/>3. Service: Business Logic Authorization<br/>4. Data Access: Secure Data Operations
```

## Security Layers Explained

### 1. Keycloak Authentication Layer
- **Purpose**: User authentication and JWT token generation
- **Responsibilities**:
  - Validate user credentials
  - Issue JWT tokens with user roles
  - Provide JWKS endpoint for token validation
- **Roles**: `user`, `admin`, `customer-manager`, `product-manager`

### 2. Envoy Gateway Authorization Layer
- **Purpose**: First line of defense for API access
- **Responsibilities**:
  - Validate JWT token signatures
  - Check token expiration
  - Enforce role-based routing rules
  - Forward valid requests to services
- **Configuration**: Routes require minimum "user" role for service access

### 3. Service-Level Authorization Layer
- **Purpose**: Business logic authorization
- **Responsibilities**:
  - Decode JWT payload for user information
  - Implement role-based access control (RBAC)
  - Enforce business rules (e.g., users can only access their own data)
  - Comprehensive audit logging

### 4. Data Access Layer
- **Purpose**: Secure data operations
- **Responsibilities**:
  - Abstract data access from business logic
  - Provide clean interface for data operations
  - Future database integration point

## Authorization Rules

### Customer Service
- **GET /customers**: 
  - `customer-manager` role: Access all customers
  - `user` role: Access only own customer record
- **GET /customers/{id}**: 
  - `customer-manager` role: Access any customer
  - `user` role: Access only if email matches

### Product Service
- **All GET endpoints**: Any user with `user` role (handled by Envoy)
- **Future write operations**: Will require `product-manager` role

## JWT Token Structure
```json
{
  "exp": 1761529888,
  "iat": 1761529588,
  "jti": "onrtro:f5c157db-fae7-c91c-9be1-6743885440ca",
  "iss": "http://localhost:8180/realms/api-gateway-poc",
  "sub": "ff7c5cc6-7c87-4f47-94af-f51a641dbbec",
  "typ": "Bearer",
  "azp": "test-client",
  "sid": "d1646165-67e7-5dbf-72c7-2c1b563aaba9",
  "acr": "1",
  "allowed-origins": [
    "http://127.0.0.1:*",
    "http://localhost:*"
  ],
  "realm_access": {
    "roles": [
      "user"
    ]
  },
  "scope": "profile email",
  "email_verified": true,
  "name": "Test User",
  "preferred_username": "testuser",
  "given_name": "Test",
  "family_name": "User",
  "email": "testuser@example.com"
}
```

## Error Responses

- **401 Unauthorized**: Invalid or missing JWT token
- **403 Forbidden**: Valid token but insufficient permissions
- **404 Not Found**: Resource doesn't exist
- **403 Business Logic**: Valid access but business rules deny operation

## Benefits of This Architecture

1. **Defense in Depth**: Multiple security layers
2. **Separation of Concerns**: Each layer has specific responsibilities
3. **Scalability**: Easy to add new services with consistent security
4. **Auditability**: Comprehensive logging at each layer
5. **Flexibility**: Different authorization rules per service
6. **Future-Proof**: Ready for database integration and additional roles

## Related Documentation

- [Security Guide](../security/security-guide.md)
- [Keycloak Setup](../setup/keycloak-setup.md)
- [Quick Reference](../development/quick-reference.md)