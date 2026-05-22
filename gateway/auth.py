"""
Gateway Auth — handles JWT validation for incoming requests.
"""

from typing import Optional, Dict
import jwt
from fastapi import Request, HTTPException
from gateway.config import settings

def validate_token(request: Request) -> Optional[Dict]:
    """
    Validate the 'Authorization: Bearer <token>' header.
    Returns the decoded payload if valid, else raises HTTPException.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None  # Unauthenticated request

    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header format")

    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(
            token, 
            settings.secret_key, 
            algorithms=[settings.jwt_algorithm]
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication error: {str(e)}")
