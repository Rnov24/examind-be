"""Cloudflare Edge Guard Middleware (Origin Lock, 2-Phase Rollout).

Protects the backend origin behind a Cloudflare Worker reverse proxy using
a shared secret header (X-Examind-Edge-Secret).
- Phase 1 (EDGE_ENFORCE=False): Logs warnings for requests without valid edge secret, allows traffic.
- Phase 2 (EDGE_ENFORCE=True): Rejects requests without valid edge secret with 403 Forbidden.
- /health is exempt from rejection in both phases (load-balancer/uptime friendly), but still logged.
- Real client IP (CF-Connecting-IP) is trusted and patched to scope['client'] only when edge secret is valid.
"""

import hmac
import logging
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import settings

logger = logging.getLogger("examind.edge_guard")


class EdgeGuardMiddleware:
    """ASGI middleware enforcing Cloudflare edge secret validation and CF-Connecting-IP resolution."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        configured_secret = settings.EDGE_SECRET.strip() if settings.EDGE_SECRET else ""
        if not configured_secret:
            # Edge lock disabled, zero behavior change
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        edge_secret_header = headers.get("x-examind-edge-secret")

        is_valid = bool(
            edge_secret_header and hmac.compare_digest(edge_secret_header, configured_secret)
        )

        if is_valid:
            # Valid edge secret: trust CF-Connecting-IP for downstream rate limiting
            cf_connecting_ip = headers.get("cf-connecting-ip")
            if cf_connecting_ip:
                client_ip = cf_connecting_ip.strip()
                existing_port = scope.get("client")[1] if scope.get("client") else 0
                scope["client"] = (client_ip, existing_port)
                scope["edge_verified"] = True

            await self.app(scope, receive, send)
            return

        # Edge secret is configured, but header is missing or incorrect
        path = scope.get("path") or ""
        logger.warning(f"[EdgeGuard] request without valid edge secret: {path}")

        # /health is EXEMPT from enforcement in both phases
        if path == "/health" or path.rstrip("/") == "/health":
            await self.app(scope, receive, send)
            return

        # Phase 2 enforcement: reject direct hits with 403 Forbidden
        if settings.EDGE_ENFORCE:
            response = JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "message": "Akses langsung ditolak.",
                    "error": {"code": "EDGE_FORBIDDEN"},
                },
            )
            await response(scope, receive, send)
            return

        # Phase 1: allow traffic for observability
        await self.app(scope, receive, send)
