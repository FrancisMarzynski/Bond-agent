import hmac

INTERNAL_PROXY_TOKEN_HEADER = "X-Bond-Internal-Proxy-Token"
REQUEST_ID_HEADER = "X-Request-Id"
INTERNAL_AUTH_BYPASS_PATHS = frozenset(
    {
        "/health",
        "/health/live",
        "/health/ready",
    }
)


def normalize_request_path(path: str) -> str:
    """Normalize trailing slashes so bypass rules stay stable."""
    if not path:
        return "/"
    if path == "/":
        return path
    normalized = path.rstrip("/")
    return normalized or "/"


def is_internal_auth_bypass_path(path: str) -> bool:
    """Return True for backend paths that must remain probeable."""
    return normalize_request_path(path) in INTERNAL_AUTH_BYPASS_PATHS


def is_internal_auth_protected_path(path: str) -> bool:
    """All backend paths are protected unless explicitly bypassed."""
    return not is_internal_auth_bypass_path(path)


def has_valid_internal_proxy_token(
    provided_token: str | None,
    expected_token: str,
) -> bool:
    """Validate the trusted proxy token using constant-time comparison."""
    provided = provided_token or ""
    expected = expected_token or ""
    return bool(expected) and hmac.compare_digest(provided, expected)
