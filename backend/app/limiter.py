from ipaddress import ip_address

from fastapi import Request
from slowapi import Limiter


def client_ip(request: Request) -> str:
    """The real client address.

    Behind our nginx the TCP peer is the proxy (a private docker address), so
    every visitor would otherwise share one rate-limit bucket. nginx overwrites
    `X-Real-IP` with the real peer address, so that header is only trusted when
    the direct peer is a private/loopback address (i.e. our proxy). Anyone
    connecting from a public address cannot choose their own identity, and the
    client-supplied `X-Forwarded-For` is never used.
    """
    peer = request.client.host if request.client else "unknown"
    try:
        parsed = ip_address(peer)
    except ValueError:
        return peer
    if parsed.is_private or parsed.is_loopback:
        real = request.headers.get("x-real-ip", "").strip()
        try:
            ip_address(real)
            return real
        except ValueError:
            pass
    return peer


# Single shared rate-limiter instance.  Import this in main.py (to attach to
# app.state.limiter) and in any router that needs the @limiter.limit decorator,
# so all decorators and the SlowAPI exception handler operate on the same object
# and storage backend.
limiter = Limiter(
    key_func=client_ip,
    default_limits=["120/minute"],
    storage_uri="memory://",
)
