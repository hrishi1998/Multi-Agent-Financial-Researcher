import logging
import os
from typing import Annotated

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_bearer = HTTPBearer(auto_error=False)
_unauthenticated_warning_emitted = False


def _presented_key(
    api_key: str | None,
    credentials: HTTPAuthorizationCredentials | None,
) -> str | None:
    if api_key:
        return api_key
    if credentials and credentials.credentials:
        return credentials.credentials
    return None


async def verify_api_key(
    api_key: Annotated[str | None, Security(_api_key_header)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
) -> bool:
    """Require X-API-Key or Bearer token when API_KEY is configured."""
    global _unauthenticated_warning_emitted
    expected = os.getenv("API_KEY")
    if not expected:
        if not _unauthenticated_warning_emitted:
            logger.warning(
                "API_KEY is not set; research endpoints are unauthenticated. "
                "Set API_KEY before exposing this service."
            )
            _unauthenticated_warning_emitted = True
        return True

    presented = _presented_key(api_key, credentials)
    if presented != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )
    return True
