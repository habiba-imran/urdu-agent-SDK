"""Password hashing (PBKDF2-HMAC) and TOTP (RFC 6238), stdlib only.

Deliberately NOT `bcrypt`/`pyotp`: neither was already in requirements.txt, and this is an
unattended overnight session (no human available to review a new third-party dependency choice).
`hashlib.pbkdf2_hmac` and RFC 6238 are both stdlib/spec-implementable without guessing a vendor
API surface (anti-hallucination rule 8.1 is about not guessing an installed library's signature;
implementing a public IETF RFC directly, cited below, is not that). Flagged in the morning report
as a judgment call, not silently made.

RFC 6238 (TOTP): https://www.rfc-editor.org/rfc/rfc6238
RFC 4226 (HOTP, which 6238 extends): https://www.rfc-editor.org/rfc/rfc4226
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
import time

PBKDF2_ITERATIONS = 600_000  # OWASP 2023 minimum recommendation for PBKDF2-HMAC-SHA256
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    salt = os.urandom(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations_s, salt_hex, digest_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iterations_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, AttributeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return hmac.compare_digest(actual, expected)


def random_base32_secret(num_bytes: int = 20) -> str:
    """A fresh TOTP shared secret, RFC 4648 base32, no padding — the form authenticator apps expect."""
    return base64.b32encode(os.urandom(num_bytes)).decode("ascii").rstrip("=")


def _hotp(secret_b32: str, counter: int, digits: int = 6) -> str:
    # RFC 4226 §5.3. base32 secret padded back to a multiple of 8 chars for b32decode.
    padded = secret_b32 + "=" * (-len(secret_b32) % 8)
    key = base64.b32decode(padded.upper())
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code_int = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % (
        10**digits
    )
    return str(code_int).zfill(digits)


def totp_now(
    secret_b32: str, *, step: int = 30, digits: int = 6, at: float | None = None
) -> str:
    t = at if at is not None else time.time()
    counter = int(t // step)
    return _hotp(secret_b32, counter, digits)


def totp_verify(
    secret_b32: str,
    code: str,
    *,
    step: int = 30,
    digits: int = 6,
    window: int = 1,
    at: float | None = None,
) -> bool:
    """Accept the current step +/- `window` steps (RFC 6238 §5.2 clock-drift tolerance)."""
    if not code or not code.isdigit() or len(code) != digits:
        return False
    t = at if at is not None else time.time()
    counter = int(t // step)
    for offset in range(-window, window + 1):
        if hmac.compare_digest(_hotp(secret_b32, counter + offset, digits), code):
            return True
    return False
