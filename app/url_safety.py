from __future__ import annotations

import ipaddress
import socket
from functools import lru_cache
from urllib.parse import urljoin, urlparse, urlunparse


ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443}
BLOCKED_HOSTS = {"localhost", "localhost.localdomain"}


class UnsafeUrlError(ValueError):
    pass


def canonicalize_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        raise UnsafeUrlError("URL 不能为空")
    if not value.lower().startswith(("http://", "https://")):
        value = f"https://{value}"

    parsed = urlparse(value)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeUrlError("只允许 http 或 https 地址")
    if not parsed.hostname:
        raise UnsafeUrlError("URL 缺少有效域名")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("URL 不能包含用户名或密码")

    host = _normalize_host(parsed.hostname)
    port = parsed.port
    if port is not None and port not in ALLOWED_PORTS:
        raise UnsafeUrlError("只允许 80 或 443 端口")

    netloc = host
    if port is not None:
        netloc = f"{host}:{port}"
    if ":" in host and not host.startswith("["):
        netloc = f"[{host}]"
        if port is not None:
            netloc = f"[{host}]:{port}"

    path = parsed.path or "/"
    return urlunparse((parsed.scheme.lower(), netloc.lower(), path.rstrip("/") or "/", "", parsed.query, ""))


def validate_public_http_url(url: str) -> str:
    normalized = canonicalize_url(url)
    parsed = urlparse(normalized)
    host = parsed.hostname
    if not host:
        raise UnsafeUrlError("URL 缺少有效域名")
    if _is_blocked_hostname(host):
        raise UnsafeUrlError("不允许访问本机或内部地址")

    literal_ip = _parse_ip(host)
    if literal_ip:
        _ensure_public_ip(literal_ip)
        return normalized

    addresses = _resolve_host(host)
    if not addresses:
        raise UnsafeUrlError("域名无法解析")
    for address in addresses:
        _ensure_public_ip(address)
    return normalized


def resolve_redirect_url(current_url: str, location: str) -> str:
    if not location:
        raise UnsafeUrlError("重定向地址为空")
    return validate_public_http_url(urljoin(current_url, location))


def _normalize_host(host: str) -> str:
    host = host.strip().strip("[]").rstrip(".")
    if not host:
        raise UnsafeUrlError("URL 缺少有效域名")
    ip = _parse_ip(host)
    if ip:
        return str(ip)
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise UnsafeUrlError("域名格式无效") from exc


def _is_blocked_hostname(host: str) -> bool:
    lowered = host.lower().rstrip(".")
    return lowered in BLOCKED_HOSTS or lowered.endswith(".localhost")


def _parse_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return None


def _ensure_public_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    if (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        raise UnsafeUrlError("不允许访问本机、内网或保留地址")


@lru_cache(maxsize=2048)
def _resolve_host(host: str) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeUrlError("域名无法解析") from exc

    addresses = []
    seen = set()
    for info in infos:
        raw_ip = info[4][0]
        if raw_ip in seen:
            continue
        seen.add(raw_ip)
        addresses.append(ipaddress.ip_address(raw_ip))
    return tuple(addresses)
