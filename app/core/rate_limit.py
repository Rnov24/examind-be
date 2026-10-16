"""Per-IP rate limiting (slowapi, in-memory).

Two layers:
- Global default: generous, so schools behind one NAT IP don't trip it.
- Strict limits on abuse-sensitive endpoints (login, register, OTP, password reset).

Behind Modal/Vercel the real client IP comes from X-Forwarded-For, which
slowapi's get_remote_address already honors.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# ~10 req/s per IP sustained — floods get 429s, normal exam traffic unaffected.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["600 per minute"],
    headers_enabled=True,  # X-RateLimit-* response headers
)
