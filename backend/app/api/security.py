import os
from pathlib import Path

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse
from starlette.types import Message


class PathTraversalError(Exception):
    """Raised when a resolved path is outside the allowed base directory."""
    pass


def safe_resolve_path(base_dir: Path, requested_path: str | Path) -> Path:
    """Resolve a path and ensure it remains strictly within the base_dir.

    Containment is verified by ancestor relationship (``base in candidate.parents``),
    not by string prefix, so sibling directories whose names share a textual prefix
    (e.g. ``data_evil`` vs ``data``) cannot bypass the sandbox.
    """
    try:
        resolved_base = base_dir.resolve(strict=False)
        # Joining with an absolute path yields the absolute path itself.
        candidate = (resolved_base / Path(requested_path)).resolve(strict=False)
    except Exception as exc:
        raise PathTraversalError(f"Invalid path: {exc}") from exc

    if candidate != resolved_base and resolved_base not in candidate.parents:
        raise PathTraversalError("Path traversal attempt detected")

    return candidate


class PayloadSizeLimitMiddleware(BaseHTTPMiddleware):
    """Enforce a maximum payload size for incoming requests.

    The limit is enforced in two layers so it cannot be bypassed:
    1. a pre-flight check on the ``Content-Length`` header when present; and
    2. an actual body-length check for chunked or headerless requests, since
       a streamed body carries no reliable ``Content-Length``.
    """

    def __init__(self, app, max_upload_size: int = 100 * 1024 * 1024):
        super().__init__(app)
        self.max_upload_size = max_upload_size

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_upload_size:
                    return self._too_large_response()
            except ValueError:
                # Malformed header; let the body-length check below decide.
                pass

        # Reading the body through ``request.body()`` caches it on the Starlette
        # ``_CachedRequest``, which replays those bytes to the downstream app, so
        # normal request handling is unaffected.
        body = await request.body()
        if body and len(body) > self.max_upload_size:
            return self._too_large_response()

        return await call_next(request)

    @staticmethod
    def _too_large_response() -> JSONResponse:
        return JSONResponse(
            status_code=413,
            content={"detail": "Payload too large. Maximum size is 100MB."},
        )