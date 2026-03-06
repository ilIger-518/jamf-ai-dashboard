"""Fernet-based encryption for persisting Jamf credentials at rest.

If FERNET_KEY is set in the environment the value is encrypted; otherwise the
value is stored as-is (development / no-key scenario).
"""

from app.config import get_settings


def _get_fernet():
    """Return a Fernet instance or None if no key is configured."""
    key = get_settings().fernet_key
    if not key:
        return None
    from cryptography.fernet import Fernet

    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str) -> str:
    """Encrypt *plaintext*. Returns ciphertext string or plaintext if no key."""
    f = _get_fernet()
    if f is None:
        return plaintext
    return f.encrypt(plaintext.encode()).decode()


def decrypt(value: str) -> str:
    """Decrypt *value*. Returns plaintext or value unchanged if no key."""
    f = _get_fernet()
    if f is None:
        return value
    try:
        return f.decrypt(value.encode()).decode()
    except Exception:
        # Value may not be encrypted (e.g. migrated records) — return as-is
        return value
