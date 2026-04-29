import hashlib
import secrets


def generate_salt() -> str:
    return secrets.token_hex(16)


def hash_password(raw_password: str, salt: str) -> str:
    password_hash = hashlib.pbkdf2_hmac(
        "sha256", raw_password.encode("utf-8"), salt.encode("utf-8"), 120000
    )
    return password_hash.hex()


def verify_password(raw_password: str, salt: str, expected_hash: str) -> bool:
    return hash_password(raw_password, salt) == expected_hash
