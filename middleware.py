from __future__ import annotations

import os
from functools import wraps
from typing import Any, Callable, TypeVar


F = TypeVar("F", bound=Callable[..., Any])


class AuthenticationError(PermissionError):
    """Raised when the provided API key is missing or invalid."""


def get_expected_api_key() -> str:
    """Read the expected API key from environment variables."""
    api_key = os.getenv("ZAVA_API_KEY") or os.getenv("API_KEY")
    if not api_key:
        raise AuthenticationError(
            "API key is not configured. Set ZAVA_API_KEY (preferred) or API_KEY in the environment."
        )
    return api_key


def validate_api_key(api_key: str | None) -> bool:
    """Return True when the supplied API key matches the configured key."""
    if not api_key:
        return False
    return api_key.strip() == get_expected_api_key().strip()


def require_api_key(func: F) -> F:
    """Decorator for MCP tools that require an api_key keyword argument.

    Example:
        @mcp.tool()
        @require_api_key
        def get_products(api_key: str, category: str | None = None):
            ...
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        api_key = kwargs.get("api_key")
        if not validate_api_key(api_key):
            raise AuthenticationError("Unauthorized: invalid or missing API key.")
        return func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]
