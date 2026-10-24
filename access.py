"""Single-process local/private access boundaries, enforced before body parsing."""
from __future__ import annotations

import ipaddress
import json
import os
from urllib.parse import urlsplit
from starlette.exceptions import HTTPException
from starlette.formparsers import MultiPartException

DEFAULT_MAX_BYTES = 2 * 1024 * 1024 * 1024
CHUNK_BYTES = 8 * 1024 * 1024


def get_mode() -> str:
    value = os.environ.get("LISTENFLOW_MODE", "").strip().lower()
    return value or ("private" if os.environ.get("LISTENFLOW_PRIVATE_USER") or os.environ.get("LISTENFLOW_PRIVATE_ORIGIN") else "local")


def get_configured_owner() -> str | None:
    return os.environ.get("LISTENFLOW_PRIVATE_USER", "").strip() or None


def get_private_origin() -> str:
    value = os.environ.get("LISTENFLOW_PRIVATE_ORIGIN", "").strip().rstrip("/")
    parsed = urlsplit(value)
    try:
        valid_port = parsed.port in (None, 443)
    except ValueError:
        return ""
    if (parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".ts.net")
            or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment or not valid_port):
        return ""
    return "https://" + parsed.hostname.lower()


def get_max_upload_bytes() -> int:
    value = int(os.environ.get("LISTENFLOW_MAX_UPLOAD_BYTES", str(DEFAULT_MAX_BYTES)))
    if value <= 0:
        raise ValueError("Upload limit must be positive.")
    return value


class AccessControlMiddleware:
    def __init__(self, app):
        self.app = app

    @staticmethod
    async def _send_json(send, status, message):
        body = json.dumps({"detail": message}).encode()
        await send({"type": "http.response.start", "status": status, "headers": [
            (b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
            (b"cache-control", b"no-store")]})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {}
        protected = {b"host", b"origin", b"tailscale-user-login", b"content-length"}
        for key, value in scope.get("headers", []):
            key = key.lower()
            if key in protected and key in headers:
                return await self._send_json(send, 400, "Duplicate request header.")
            headers[key] = value.decode("latin1").strip()
        mode = get_mode()
        try:
            max_bytes = get_max_upload_bytes()
        except ValueError:
            return await self._send_json(send, 503, "Invalid upload-limit configuration.")
        if mode not in ("local", "private"):
            return await self._send_json(send, 503, "Invalid access-mode configuration.")
        if mode == "private":
            owner, origin = get_configured_owner(), get_private_origin()
            if not owner or not origin:
                return await self._send_json(send, 503, "Private owner and HTTPS origin must be configured.")
            try:
                loopback = ipaddress.ip_address(scope.get("client", ("", 0))[0]).is_loopback
            except ValueError:
                loopback = False
            if not loopback:
                return await self._send_json(send, 403, "Requests must arrive through the local private proxy.")
            login = headers.get(b"tailscale-user-login", "")
            if not login:
                return await self._send_json(send, 401, "Missing Tailscale identity.")
            if login.casefold() != owner.casefold():
                return await self._send_json(send, 403, "Identity is not authorized.")
            host = headers.get(b"host", "").lower()
            expected = urlsplit(origin).netloc
            if host not in (expected, expected + ":443"):
                return await self._send_json(send, 403, "Unexpected private host.")
            # Native clients omit Origin; browsers must use the configured origin.
            if b"origin" in headers and headers[b"origin"] != origin:
                return await self._send_json(send, 403, "Cross-origin requests are not permitted.")
            scope.setdefault("state", {})["tailscale_user"] = login
        elif b"tailscale-user-login" in headers:
            return await self._send_json(send, 403, "Enable private mode before using Tailscale Serve.")
        # Bound the request as it is consumed, including requests without Content-Length.
        limit = max_bytes + 1024 * 1024 if headers.get(b"content-type", "").startswith("multipart/") else max_bytes
        if scope["method"] == "PATCH" and scope["path"].startswith("/api/uploads/"):
            limit = min(limit, CHUNK_BYTES)
        if b"content-length" in headers:
            try:
                length = int(headers[b"content-length"])
                if length < 0:
                    raise ValueError()
            except ValueError:
                return await self._send_json(send, 400, "Invalid Content-Length.")
            if length > limit:
                return await self._send_json(send, 413, "Request exceeds the upload limit.")
        count, exceeded, responded = 0, False, False

        async def limited_receive():
            nonlocal count, exceeded
            message = await receive()
            if message["type"] == "http.request":
                count += len(message.get("body", b""))
                if count > limit:
                    exceeded = True
                    # Starlette closes any multipart temporary files on this exception.
                    raise MultiPartException("Request exceeds the upload limit.")
            return message

        async def guarded_send(message):
            nonlocal responded
            if exceeded:
                if not responded:
                    responded = True
                    await self._send_json(send, 413, "Request exceeds the upload limit.")
                return
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except (MultiPartException, HTTPException):
            if not exceeded:
                raise
            if not responded:
                await self._send_json(send, 413, "Request exceeds the upload limit.")
