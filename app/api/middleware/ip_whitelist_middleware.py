# ===== app/api/middleware/ip_whitelist_middleware.py =====
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from ipaddress import ip_address, ip_network


class IPWhitelistMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce IP whitelisting if configured on API key.
    """

    async def dispatch(self, request: Request, call_next):
        # Only apply to API routes
        if not request.url.path.startswith("/api/v1/"):
            return await call_next(request)

        api_key = getattr(request.state, "api_key", None)

        if api_key and api_key.allowed_ips:
            client_ip = request.client.host if request.client else None

            if not client_ip:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Unable to determine client IP address"}
                )

            # Check if client IP is in allowed list
            is_allowed = False
            client_ip_obj = ip_address(client_ip)

            for allowed in api_key.allowed_ips:
                try:
                    # Check if it's a CIDR range or single IP
                    if "/" in allowed:
                        if client_ip_obj in ip_network(allowed, strict=False):
                            is_allowed = True
                            break
                    else:
                        if str(client_ip_obj) == allowed:
                            is_allowed = True
                            break
                except ValueError:
                    continue

            if not is_allowed:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "IP address not whitelisted for this API key"}
                )

        return await call_next(request)