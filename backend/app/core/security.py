import time
from collections import defaultdict, deque
from secrets import compare_digest

from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from app.core.config import get_settings

admin_api_key_header = APIKeyHeader(name="X-Admin-API-Key", auto_error=False)
PLACEHOLDER_ADMIN_KEYS = {
    "change-me-local-demo-only",
    "replace-with-a-long-local-demo-key",
}


async def require_admin(x_admin_api_key: str | None = Security(admin_api_key_header)) -> None:
    settings = get_settings()
    if not x_admin_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing admin API key")
    if settings.environment not in {"local", "demo", "test"} and settings.admin_api_key in PLACEHOLDER_ADMIN_KEYS:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Admin API key is not configured",
        )
    if not compare_digest(x_admin_api_key, settings.admin_api_key):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin API key")


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._requests: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window_seconds: int = 60) -> None:
        now = time.time()
        bucket = self._requests[key]
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        bucket.append(now)


rate_limiter = InMemoryRateLimiter()


async def sensitive_rate_limit(request: Request) -> None:
    settings = get_settings()
    client = request.client.host if request.client else "unknown"
    rate_limiter.check(client, settings.sensitive_rate_limit_per_minute)
