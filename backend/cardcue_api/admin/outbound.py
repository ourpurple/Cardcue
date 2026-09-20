"""Resolve and pin outbound connections; never follow provider redirects."""
import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit
import httpx
from cardcue_api.config import settings

class UnsafeDestination(ValueError):
    pass

def validate_url(url: str):
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise UnsafeDestination("模型地址必须是无账号、查询参数的 HTTP 或 HTTPS 地址")
        port = parsed.port or (80 if parsed.scheme == "http" else 443)
        if not (1 <= port <= 65535):
            raise UnsafeDestination("端口号不合法")
        return parsed
    except UnsafeDestination:
        raise
    except ValueError as e:
        raise UnsafeDestination(f"地址格式或端口不合法: {e}") from e

def resolve_public(host: str, port: int) -> str:
    allowed = {h.strip().lower() for h in settings.outbound_allowed_hosts.split(",") if h.strip()}
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not addresses:
        raise UnsafeDestination("服务地址无法解析")
    for item in addresses:
        ip = ipaddress.ip_address(item[4][0])
        if ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast or ip.is_reserved:
            raise UnsafeDestination("禁止访问本机、元数据或保留网络地址")
        if not ip.is_global and host.lower() not in allowed:
            raise UnsafeDestination("不允许访问未授权内网地址")
    return addresses[0][4][0]

class PinnedTransport(httpx.AsyncBaseTransport):
    def __init__(self):
        self.inner = httpx.AsyncHTTPTransport(retries=0)
    async def handle_async_request(self, request):
        parsed = validate_url(str(request.url))
        port = parsed.port or (80 if parsed.scheme == "http" else 443)
        ip = await asyncio.to_thread(resolve_public, parsed.hostname, port)
        headers = request.headers.copy()
        headers["Host"] = parsed.netloc
        extensions = dict(request.extensions)
        if parsed.scheme == "https":
            extensions["sni_hostname"] = parsed.hostname
        pinned = httpx.Request(
            request.method,
            request.url.copy_with(host=ip),
            headers=headers,
            stream=request.stream,
            extensions=extensions,
        )
        return await self.inner.handle_async_request(pinned)
    async def aclose(self):
        await self.inner.aclose()

async def post_json(url: str, key: str, payload: dict, timeout: int = 30):
    async with httpx.AsyncClient(transport=PinnedTransport(), timeout=timeout, follow_redirects=False) as client:
        async with client.stream("POST", url, headers={"Authorization": f"Bearer {key}"}, json=payload) as response:
            if response.status_code != 200:
                raise ValueError(f"provider_http_{response.status_code}")
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                raw.extend(chunk)
                if len(raw) > 1024 * 1024:
                    raise ValueError("provider_response_too_large")
            import json
            return json.loads(raw)
