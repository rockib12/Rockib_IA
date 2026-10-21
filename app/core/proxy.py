"""Resolve client addresses without trusting arbitrary forwarded headers."""
from __future__ import annotations

import ipaddress

from fastapi import Request

from app.core.config import settings


def _is_trusted_proxy(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
        return any(ip in ipaddress.ip_network(cidr) for cidr in settings.TRUSTED_PROXY_CIDRS)
    except ValueError:
        return False


def get_client_ip(request: Request) -> str:
    """Use X-Forwarded-For only when the direct peer is explicitly trusted."""
    peer = request.client.host if request.client else "127.0.0.1"
    if not _is_trusted_proxy(peer):
        return peer

    forwarded = request.headers.get("x-forwarded-for", "")
    if not forwarded:
        return peer

    # The header is ordered client -> proxies. Walk from the nearest proxy outward,
    # skipping only addresses that are explicitly configured as trusted proxies.
    chain = [part.strip() for part in forwarded.split(",") if part.strip()]
    for address in reversed(chain):
        try:
            ipaddress.ip_address(address)
        except ValueError:
            continue
        if not _is_trusted_proxy(address):
            return address
    return peer
