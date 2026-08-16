"""RFC 6238 TOTP for local GoTrue MFA enrollment proofs.

Stdlib only. Do not add ``pyotp``; lock updates are out of scope.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time


def hotp_sha1(key: bytes, counter: int, *, digits: int = 6) -> str:
    """Return one HMAC-SHA1 HOTP code.

    Args:
        key: Shared secret bytes.
        counter: 8-byte big-endian moving factor.
        digits: Decimal length. GoTrue TOTP uses 6.

    Returns:
        Zero-padded decimal code.
    """

    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{truncated % (10**digits):0{digits}d}"


def totp_from_base32(
    secret: str,
    *,
    timestamp: float | None = None,
    period: int = 30,
    digits: int = 6,
) -> str:
    """Return a TOTP code for a base32 secret as GoTrue enroll returns.

    Args:
        secret: Base32 shared secret from ``totp.secret``.
        timestamp: Unix seconds. Default is now.
        period: Step seconds. GoTrue uses 30.
        digits: Code length. GoTrue uses 6.

    Returns:
        Zero-padded decimal code for the current (or supplied) step.
    """

    padded = secret.upper() + "=" * ((8 - len(secret.upper()) % 8) % 8)
    key = base64.b32decode(padded)
    counter = int((time.time() if timestamp is None else timestamp) // period)
    return hotp_sha1(key, counter, digits=digits)


def totp_window(secret: str, *, period: int = 30, digits: int = 6) -> tuple[str, ...]:
    """Return previous, current, and next TOTP codes.

    GoTrue accepts one-interval clock skew. Tests try the window in order.

    Args:
        secret: Base32 shared secret.
        period: Step seconds.
        digits: Code length.

    Returns:
        Three codes: ``t-1``, ``t``, ``t+1``.
    """

    now = time.time()
    return (
        totp_from_base32(secret, timestamp=now - period, period=period, digits=digits),
        totp_from_base32(secret, timestamp=now, period=period, digits=digits),
        totp_from_base32(secret, timestamp=now + period, period=period, digits=digits),
    )
