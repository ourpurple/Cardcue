"""Encryption and decryption utilities for sensitive mailbox authentication tokens."""

import base64
import hashlib
from cryptography.fernet import Fernet, InvalidToken

from cardcue_api.config import settings


class MailCryptoError(Exception):
    """Raised when encryption or decryption fails."""
    pass


def _derive_fernet_key(secret: str | None = None) -> bytes:
    key_str = secret or settings.mail_encryption_key
    digest = hashlib.sha256(key_str.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_token(plain_text: str, secret: str | None = None) -> str:
    """Encrypt a plain text password or auth token using Fernet symmetric encryption."""
    if not plain_text:
        return ""
    fernet = Fernet(_derive_fernet_key(secret))
    encrypted_bytes = fernet.encrypt(plain_text.encode("utf-8"))
    return encrypted_bytes.decode("ascii")


def decrypt_token(cipher_text: str, secret: str | None = None) -> str:
    """Decrypt a Fernet cipher text back to plain text."""
    if not cipher_text:
        return ""
    try:
        fernet = Fernet(_derive_fernet_key(secret))
        decrypted_bytes = fernet.decrypt(cipher_text.encode("ascii"))
        return decrypted_bytes.decode("utf-8")
    except (InvalidToken, Exception) as e:
        raise MailCryptoError("Failed to decrypt auth token: invalid or corrupted key/data") from e


def mask_token(plain_or_cipher: str) -> str:
    """Return a masked representation of the token for safe display in logs and APIs."""
    if not plain_or_cipher:
        return ""
    return "********"
