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


# ~10 req/s per IP sustained — floods get 429s, normal exam traffic unaffected.
limiter = Limiter(
    key_func=get_client_ip,
    default_limits=["600 per minute"],
    headers_enabled=True,  # X-RateLimit-* response headers
)
