from hmac import compare_digest
from typing import Annotated

from fastapi import Header, HTTPException, status

from app.config import get_settings


def require_api_identity(
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> str:
    expected = get_settings().app_api_key
    if not expected:
        return "local-development"
    token = x_api_key
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if token is None or not compare_digest(token, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "A valid API key is required.")
    return "api-key-user"
