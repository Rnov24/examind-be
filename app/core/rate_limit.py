"""Per-IP rate limiting (slowapi, in-memory).

Two layers:
- Global default: generous, so schools behind one NAT IP don't trip it.
- Strict limits on abuse-sensitive endpoints (login, register, OTP, password reset).

Key function uses X-Forwarded-For (real client IP behind Modal/Vercel proxies).
slowapi 0.1.x's get_remote_address only reads request.client.host, which behind
a proxy pool varies per request and makes limits useless — hence this custom one.
"""

from fastapi import Request
from slowapi import Limiter


def get_client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


def global_key(request: Request) -> str:
    """Fixed key for global (cross-IP) limits.

    Modal's edge proxies each request from a different internal IP and strips
    X-Forwarded-For, so per-IP limiting can't work there. Global limits are the
    safety net against floods: one shared budget for everyone.
    """
    return "global"


# ~10 req/s per IP sustained — floods get 429s, normal exam traffic unaffected.
# headers_enabled=False: our endpoints return ApiResponse models (not starlette
# Response), and slowapi's header injection crashes on those. Limiting itself
# is unaffected; the 429 handler sets Retry-After manually.
limiter = Limiter(
    key_func=get_client_ip,
    default_limits=["600 per minute"],
    headers_enabled=False,
)
