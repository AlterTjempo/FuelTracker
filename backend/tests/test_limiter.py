"""The rate-limit identity must be the real client, and must not be spoofable by a public client."""

from starlette.requests import Request

from limiter import client_ip


def req(peer, **headers):
    return Request(
        {
            "type": "http",
            "headers": [
                (k.lower().replace("_", "-").encode(), v.encode())
                for k, v in headers.items()
            ],
            "client": (peer, 5000),
        }
    )


def test_public_client_cannot_choose_its_identity():
    r = req("93.184.216.34", X_Real_IP="203.0.113.1", X_Forwarded_For="203.0.113.2")
    assert client_ip(r) == "93.184.216.34"


def test_behind_our_proxy_the_real_ip_header_is_used():
    # the direct peer is the nginx container (private docker address)
    assert client_ip(req("172.18.0.4", X_Real_IP="198.51.100.9")) == "198.51.100.9"


def test_x_forwarded_for_is_never_used():
    assert client_ip(req("172.18.0.4", X_Forwarded_For="203.0.113.5")) == "172.18.0.4"
    assert client_ip(req("127.0.0.1", X_Forwarded_For="203.0.113.5")) == "127.0.0.1"


def test_invalid_real_ip_header_falls_back_to_the_peer():
    assert client_ip(req("172.18.0.4", X_Real_IP="not-an-ip")) == "172.18.0.4"
    assert client_ip(req("172.18.0.4")) == "172.18.0.4"
