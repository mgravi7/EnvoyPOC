"""
External Authorization Service
Provides role lookup for authenticated users based on email from JWT.

This service is called by Envoy's ext_authz filter to retrieve user roles
from a PostgreSQL database (currently mocked). Roles are returned in response
headers and used by Envoy's RBAC filter for authorization decisions.
"""

import sys
from fastapi import FastAPI, Request, HTTPException, Response
import os
import json
import base64
from typing import Optional
sys.path.append('/app')

from authz_data_access import get_user_roles, UserNotFoundException
from shared.common import setup_logging, create_health_response
from redis_cache import get_cache_instance, PlatformRolesCache

# Setup logging
logger = setup_logging("authz-service")

# Initialize cache (may be None if Redis not configured)
cache: PlatformRolesCache | None = get_cache_instance()

app = FastAPI(
    title="Authorization Service",
    description="External authorization service for role lookup",
    version="1.0.0"
)


def extract_email_from_jwt(token: str) -> str:
    """
    Extract email from JWT payload.
    
    Note: JWT signature is already validated by Envoy's JWT filter.
    We only decode the payload to extract user information.
    
    Args:
        token: JWT token string (without 'Bearer ' prefix)
    
    Returns:
        User email address from JWT 'email' claim
    
    Raises:
        HTTPException: If token cannot be decoded or email claim missing
    """
    try:
        # JWT structure: header.payload.signature
        # We only need the payload (middle part)
        parts = token.split('.')
        if len(parts) != 3:
            raise ValueError("Invalid JWT token format")
        
        # Decode the payload (add padding if needed)
        payload_part = parts[1]
        # Add padding if needed for base64 decoding
        padding = 4 - (len(payload_part) % 4)
        if padding != 4:
            payload_part += '=' * padding
        
        # Decode base64
        decoded_bytes = base64.urlsafe_b64decode(payload_part)
        payload = json.loads(decoded_bytes)
        
        # Extract email
        email = payload.get('email')
        if not email:
            raise ValueError("Email claim not found in JWT payload")
        
        return email
    
    except (ValueError, json.JSONDecodeError, KeyError) as e:
        logger.error(f"Failed to extract email from JWT: {e}")
        raise HTTPException(
            status_code=401,
            detail=f"Invalid token: {str(e)}"
        )


@app.get("/authz/health")
def health_check():
    """
    Health check endpoint.
    
    Used by Docker healthcheck and Envoy health checking.
    Includes Redis cache health status if caching is enabled.
    
    Returns:
        Health status information
    """
    logger.info("Health check requested")
    response = create_health_response("authz-service")
    
    # Add cache health status if caching is enabled
    if cache:
        response["cache_enabled"] = True
        response["cache_healthy"] = cache.health_check()
    else:
        response["cache_enabled"] = False
    
    return response

@app.get("/authz/me")
async def get_current_user(request: Request):
    """
    Get current user information and roles.
    
    Public endpoint for React UI to fetch authenticated user's email and platform roles.
    This endpoint requires a valid JWT token (validated by Envoy before reaching this service).
    
    Request Headers:
        authorization: Bearer <jwt-token> (validated by Envoy)
    
    Returns:
        200 OK: User information with roles
        {
            "email": "user@example.com",
            "roles": ["user", "customer-manager"]
        }
        
        401 Unauthorized: Missing or invalid JWT token
        {
            "detail": "No authorization token provided"
        }
    
    Note: This endpoint uses the same role lookup logic as ext_authz,
          including Redis caching for performance.
    """
    logger.info("User info request received (/authz/me)")
    
    # Extract JWT token
    auth_header = request.headers.get("authorization")
    if not auth_header:
        logger.warning("No authorization header in /authz/me request")
        raise HTTPException(
            status_code=401,
            detail="No authorization token provided"
        )
    
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        logger.warning("Invalid authorization header format in /authz/me request")
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header format"
        )
    
    token = parts[1]
    
    # Extract email from JWT
    try:
        email = extract_email_from_jwt(token)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to extract email from JWT: {e}")
        raise HTTPException(
            status_code=401,
            detail="Invalid JWT token"
        )
    
    logger.info(f"User info request for email: {email}")
    
    # Try cache first if available
    roles = None
    if cache:
        roles = cache.get(email)
    
    # If cache miss, query database
    if roles is None:
        try:
            roles = get_user_roles(email)
            # Cache the result for future requests
            if cache and roles:
                cache.set(email, roles)
        except UserNotFoundException:
            logger.info(f"User not found in database: {email}. Returning unverified-user role.")
            roles = ["unverified-user"]
    
    # Default to unverified-user if no roles found
    if not roles:
        logger.info(f"No roles found for {email}. Returning unverified-user role.")
        roles = ["unverified-user"]
    
    logger.info(f"Returning user info for {email}: roles={roles}")
    
    return {
        "email": email,
        "roles": roles
    }

@app.api_route("/authz/roles", methods=["GET", "POST"])
@app.api_route("/authz/roles/{path:path}", methods=["GET", "POST"])
async def get_user_roles_endpoint(request: Request, path: Optional[str] = None):
    """
    Role lookup endpoint called by Envoy ext_authz filter.
    
    Accepts both GET and POST methods (Envoy may use either depending on original request).
    Accepts both /authz/roles and /authz/roles/* paths.
    The path suffix (e.g., /customers, /products) is ignored and can be used
    for logging/debugging purposes. This allows Envoy's path_prefix to work
    correctly with ext_authz filter.
    
    Extracts user email from JWT token and returns roles in response headers.
    This endpoint is only called by Envoy after JWT validation.
    
    Request Headers:
        authorization: Bearer <jwt-token> (validated by Envoy)
        x-request-id: <uuid> (optional, for request tracing)
    
    Response Headers (200 OK, HTTP/2 lowercase):
        x-user-email: user@example.com
        x-user-roles: user,customer-manager (comma-separated, NO spaces or whitespace)
    
    Note: Role names must contain only printable characters (no whitespace).
          Multiple roles are returned as a comma-separated list with NO spaces
          between role names (e.g., "user,customer-manager" not "user, customer-manager").
    
    Args:
        path: Optional path suffix from original request (e.g., "customers", "products")
              This is ignored but logged for debugging.
    
    Returns:
        200 OK: User found, roles returned in headers
        500 Internal Server Error: Service error
    """
    # Extract request ID for logging correlation
    request_id = request.headers.get("x-request-id", "unknown")
    
    # Log the original request path for debugging
    if path:
        logger.info(f"[{request_id}] AuthZ role lookup request ({request.method}) for path: /{path}")
    else:
        logger.info(f"[{request_id}] AuthZ role lookup request ({request.method}) received")
    
    try:
        auth_header = request.headers.get("authorization")
        if not auth_header:
            logger.info(f"[{request_id}] No authorization header found. Returning role 'guest'.")
            return Response(
                status_code=200,
                content="",
                headers={
                    "x-user-email": "",
                    "x-user-roles": "guest"
                }
            )

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            logger.info(f"[{request_id}] Authorization header format invalid. Returning role 'guest'.")
            return Response(
                status_code=200,
                content="",
                headers={
                    "x-user-email": "",
                    "x-user-roles": "guest"
                }
            )

        token = parts[1]
        try:
            email = extract_email_from_jwt(token)
        except Exception as e:
            logger.info(f"[{request_id}] JWT extraction failed. Returning role 'guest'. Reason: {e}")
            return Response(
                status_code=200,
                content="",
                headers={
                    "x-user-email": "",
                    "x-user-roles": "guest"
                }
            )

        logger.info(f"[{request_id}] User email extracted: {email}")
        
        # Try cache first if available
        roles = None
        if cache:
            roles = cache.get(email)
        
        # If cache miss, query database
        if roles is None:
            try:
                roles = get_user_roles(email)
                # Cache the result for future requests
                if cache and roles:
                    cache.set(email, roles)
            except UserNotFoundException:
                logger.info(f"[{request_id}] No DB entry for {email}. Returning role 'unverified-user'.")
                return Response(
                    status_code=200,
                    content="",
                    headers={
                        "x-user-email": email,
                        "x-user-roles": "unverified-user"
                    }
                )
        
        if not roles:
            logger.info(f"[{request_id}] No roles found for {email}. Returning role 'unverified-user'.")
            return Response(
                status_code=200,
                content="",
                headers={
                    "x-user-email": email,
                    "x-user-roles": "unverified-user"
                }
            )
        
        roles_str = ",".join(roles)
        logger.info(f"[{request_id}] Roles found for {email}: {roles}")
        return Response(
            status_code=200,
            content="",
            headers={
                "x-user-email": email,
                "x-user-roles": roles_str
            }
        )
    except Exception as e:
        logger.error(f"[{request_id}] Unexpected authorization error: {e}", exc_info=True)
        return Response(
            status_code=500,
            content="Internal authorization error",
            headers={}
        )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("SERVICE_PORT", 9000))
    logger.info(f"Starting authorization service on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
