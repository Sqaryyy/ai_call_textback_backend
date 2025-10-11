# ===== app/utils/encryption.py =====
from cryptography.fernet import Fernet
from app.config.settings import Settings


# Generate a key once and store in your settings/env
# ENCRYPTION_KEY = Fernet.generate_key()
# Store this in your .env file


def get_cipher():
    """Get Fernet cipher instance"""
    settings=Settings
    # Ensure the key is properly formatted
    key = settings.ENCRYPTION_KEY.encode() if isinstance(settings.ENCRYPTION_KEY, str) else settings.ENCRYPTION_KEY
    return Fernet(key)


def encrypt_token(token: str) -> bytes:
    """Encrypt a token string"""
    if not token:
        return None
    cipher = get_cipher()
    return cipher.encrypt(token.encode())


def decrypt_token(encrypted_token: bytes) -> str:
    """Decrypt a token"""
    if not encrypted_token:
        return None
    cipher = get_cipher()
    return cipher.decrypt(encrypted_token).decode()

