# React Authentication Integration Guide

## Overview

This guide shows how to integrate your React application with the API Gateway's authentication and authorization system. The gateway uses Keycloak for authentication (JWT tokens) and an external authorization service for role-based access control.

## Architecture

```
React App → API Gateway (Envoy) → Authorization Service
    ↓             ↓                        ↓
  JWT Token   Validates JWT         Looks up roles
                                    (DB + Redis cache)
```

**Key Points:**
- Keycloak issues JWT tokens (authentication only)
- Authorization service manages platform roles (not stored in JWT)
- React fetches roles via `/auth/me` endpoint
- All backend API calls validate permissions server-side

---

## Quick Start

### 1. Get JWT Token from Keycloak

```javascript
async function login(username, password) {
  const response = await fetch('http://localhost:8080/auth/realms/api-gateway-poc/protocol/openid-connect/token', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: new URLSearchParams({
      client_id: 'test-client',
      username: username,
      password: password,
      grant_type: 'password',
    }),
  });

  if (!response.ok) {
    throw new Error('Login failed');
  }

  const data = await response.json();
  
  // Store tokens
  localStorage.setItem('access_token', data.access_token);
  localStorage.setItem('refresh_token', data.refresh_token);
  
  return data.access_token;
}
```

### 2. Fetch User Roles from `/auth/me`

```javascript
async function fetchUserRoles() {
  const token = localStorage.getItem('access_token');
  
  if (!token) {
    throw new Error('No access token found');
  }

  const response = await fetch('http://localhost:8080/auth/me', {
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    if (response.status === 401) {
      // Token expired or invalid - redirect to login
      localStorage.removeItem('access_token');
      window.location.href = '/login';
      return null;
    }
    throw new Error('Failed to fetch user roles');
  }

  const userData = await response.json();
  // Returns: { email: "user@example.com", roles: ["user", "customer-manager"] }
  
  return userData;
}
```

### 3. Create Auth Context for React

```javascript
import React, { createContext, useState, useEffect, useContext } from 'react';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadUserData();
  }, []);

  async function loadUserData() {
    try {
      const token = localStorage.getItem('access_token');
      if (!token) {
        setLoading(false);
        return;
      }

      const userData = await fetchUserRoles();
      setUser(userData); // { email, roles }
    } catch (error) {
      console.error('Failed to load user data:', error);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }

  async function login(username, password) {
    await loginUser(username, password); // Your login function
    await loadUserData(); // Fetch roles after login
  }

  function logout() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    setUser(null);
  }

  const value = {
    user,
    loading,
    login,
    logout,
    refreshUser: loadUserData,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
```

### 4. Use Roles in Components

```javascript
import { useAuth } from './AuthContext';

function CustomerManagementPage() {
  const { user } = useAuth();

  // Check if user has required role
  const canManageCustomers = user?.roles.includes('customer-manager');

  if (!canManageCustomers) {
    return <div>Access Denied: You need customer-manager role</div>;
  }

  return (
    <div>
      <h1>Customer Management</h1>
      {/* Customer management UI */}
    </div>
  );
}
```

### 5. Protected Route Component

```javascript
import { Navigate } from 'react-router-dom';
import { useAuth } from './AuthContext';

function ProtectedRoute({ children, requiredRoles = [] }) {
  const { user, loading } = useAuth();

  if (loading) {
    return <div>Loading...</div>;
  }

  if (!user) {
    return <Navigate to="/login" />;
  }

  // Check if user has any of the required roles
  const hasRequiredRole = requiredRoles.length === 0 || 
    requiredRoles.some(role => user.roles.includes(role));

  if (!hasRequiredRole) {
    return <div>Access Denied</div>;
  }

  return children;
}

// Usage in router
<Route 
  path="/customers" 
  element={
    <ProtectedRoute requiredRoles={['user', 'customer-manager']}>
      <CustomerPage />
    </ProtectedRoute>
  } 
/>
```

### 6. Conditional UI Rendering

```javascript
function Navigation() {
  const { user } = useAuth();

  return (
    <nav>
      <a href="/">Home</a>
      
      {user?.roles.includes('user') && (
        <a href="/products">Products</a>
      )}
      
      {user?.roles.includes('customer-manager') && (
        <a href="/customers">Manage Customers</a>
      )}
      
      {user?.roles.includes('product-manager') && (
        <a href="/products/admin">Manage Products</a>
      )}
    </nav>
  );
}
```

---

## Available Platform Roles

| Role | Description |
|------|-------------|
| `guest` | Unauthenticated user (no JWT) |
| `unverified-user` | Authenticated but not assigned roles in system |
| `user` | Standard authenticated user |
| `customer-manager` | Can manage customer data |
| `product-manager` | Can manage product catalog |

---

## Security Best Practices

### ⚠️ Client-Side Role Checks Are for UX Only

**Important:** Role checks in React are for UI optimization only. They improve user experience by hiding unavailable features, but **do NOT provide security**.

**Always validate permissions on the backend:**
- Every API request is validated by the gateway
- Backend services enforce authorization rules
- Users cannot bypass server-side checks by manipulating client code

### Token Refresh Strategy

```javascript
// Refresh token before expiration (e.g., every 4 minutes if TTL is 5 minutes)
useEffect(() => {
  const interval = setInterval(async () => {
    const refreshToken = localStorage.getItem('refresh_token');
    if (!refreshToken) return;

    try {
      const response = await fetch('http://localhost:8080/auth/realms/api-gateway-poc/protocol/openid-connect/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          client_id: 'test-client',
          grant_type: 'refresh_token',
          refresh_token: refreshToken,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        localStorage.setItem('access_token', data.access_token);
        // Optionally refresh user roles
        await refreshUser();
      }
    } catch (error) {
      console.error('Token refresh failed:', error);
    }
  }, 4 * 60 * 1000); // Every 4 minutes

  return () => clearInterval(interval);
}, []);
```

### Handle Stale Roles

Role data cached in React may become stale if roles change on the backend. Strategies:

1. **Refresh on visibility change** (user returns to tab):
```javascript
useEffect(() => {
  const handleVisibilityChange = () => {
    if (document.visibilityState === 'visible') {
      refreshUser();
    }
  };
  
  document.addEventListener('visibilitychange', handleVisibilityChange);
  return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
}, []);
```

2. **Refresh after sensitive operations**:
```javascript
async function updateUserRole(userId, newRole) {
  await fetch('/admin/users/roles', { 
    method: 'POST', 
    body: JSON.stringify({ userId, role: newRole }) 
  });
  
  // Refresh current user's roles
  await refreshUser();
}
```

3. **Periodic refresh** (e.g., every 5 minutes):
```javascript
useEffect(() => {
  const interval = setInterval(() => refreshUser(), 5 * 60 * 1000);
  return () => clearInterval(interval);
}, []);
```

---

## API Reference

### `GET /auth/me`

Fetch authenticated user's email and platform roles.

**Request:**
```http
GET /auth/me HTTP/1.1
Host: localhost:8080
Authorization: Bearer <jwt-token>
```

**Response (200 OK):**
```json
{
  "email": "user@example.com",
  "roles": ["user", "customer-manager"]
}
```

**Response (401 Unauthorized):**
```json
{
  "detail": "No authorization token provided"
}
```

**Caching:**
- Roles are cached in Redis (5-minute TTL by default)
- Subsequent calls within TTL return cached data
- Cache shared with backend authorization checks

---

## Troubleshooting

### Issue: "No authorization token provided" (401)

**Cause:** JWT token missing or not sent in Authorization header.

**Solution:** Ensure token is stored and included in request:
```javascript
headers: { 'Authorization': `Bearer ${token}` }
```

### Issue: Roles appear stale in UI

**Cause:** React cached user data doesn't reflect backend role changes.

**Solution:** Call `refreshUser()` to fetch fresh roles from `/auth/me`.

### Issue: CORS errors when calling API

**Cause:** Gateway not configured for CORS (if React runs on different origin).

**Solution:** Configure Envoy CORS policy or use same origin for React app.

---

## Complete Example

See `examples/react-auth-demo` for a full working example with:
- Login/logout flow
- Role-based routing
- Conditional UI rendering
- Token refresh
- Error handling

---

## Questions?

For technical support or questions:
- Check API Gateway logs: `docker-compose logs gateway`
- Check authz-service logs: `docker-compose logs authz-service`
- Review security documentation: `docs/security/`
