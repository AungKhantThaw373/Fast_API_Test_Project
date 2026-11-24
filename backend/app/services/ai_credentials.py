import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


def _fernet() -> Fernet:
    secret = settings.AI_SETTINGS_ENCRYPTION_KEY or settings.JWT_SECRET
    material = b"stillroom:ai-settings:v1:" + secret.encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(material).digest())
    return Fernet(key)


def encrypt_api_key(api_key: str) -> str:
    return _fernet().encrypt(api_key.encode("utf-8")).decode("ascii")


def decrypt_api_key(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError) as exc:
        raise RuntimeError(
            "The saved AI key cannot be decrypted. Check AI_SETTINGS_ENCRYPTION_KEY and restore the key in AI settings."
        ) from exc
