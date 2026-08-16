"""RFC 6238 test-vector checks for the local TOTP helper."""

from __future__ import annotations

from tests.contract.rfc6238_totp import hotp_sha1, totp_from_base32


def test_rfc6238_sha1_8_digit_vector() -> None:
    """Appendix B SHA-1 vector at T=59 is 94287082 for eight digits."""

    key = b"12345678901234567890"
    assert hotp_sha1(key, 1, digits=8) == "94287082"


def test_totp_from_base32_uses_thirty_second_steps() -> None:
    """A known base32 secret at a frozen timestamp is stable."""

    code = totp_from_base32(
        "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ",
        timestamp=59,
        period=30,
        digits=8,
    )
    assert code == "94287082"
