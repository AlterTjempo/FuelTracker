from slowapi import Limiter
from slowapi.util import get_remote_address

# Single shared rate-limiter instance.  Import this in main.py (to attach to
# app.state.limiter) and in any router that needs the @limiter.limit decorator,
# so all decorators and the SlowAPI exception handler operate on the same object
# and storage backend.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["120/minute"],
    storage_uri="memory://",
)
