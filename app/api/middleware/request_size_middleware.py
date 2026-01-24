# ===== app/api/middleware/request_size_middleware.py =====
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Limit the size of incoming request bodies to prevent abuse.
    Default: 10MB limit
    """

    def __init__(self, app, max_upload_size: int = 10 * 1024 * 1024):  # 10MB default
        super().__init__(app)
        self.max_upload_size = max_upload_size

    async def dispatch(self, request: Request, call_next):
        # Only check POST, PUT, PATCH requests (they have request bodies)
        if request.method in ["POST", "PUT", "PATCH"]:
            content_length = request.headers.get("content-length")

            if content_length and int(content_length) > self.max_upload_size:
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": "Request body too large",
                        "max_size_mb": self.max_upload_size / (1024 * 1024)
                    }
                )

        return await call_next(request)