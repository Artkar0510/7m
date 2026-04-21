import hashlib
import hmac
import secrets

from core.settings import settings


def generate_salt() -> str:
    return secrets.token_hex(settings.password_hash.salt_size)


def get_password_hash(password: str, salt: str) -> str:
    hash_settings = settings.password_hash
    derived_key = hashlib.pbkdf2_hmac(
        hash_name=hash_settings.algorithm,
        password=password.encode("utf-8"),
        salt=bytes.fromhex(salt),
        iterations=hash_settings.iterations,
        dklen=hash_settings.dklen,
    )
    return derived_key.hex()


def hash_password(password: str) -> tuple[str, str]:
    salt = generate_salt()
    return get_password_hash(password=password, salt=salt), salt


def verify_password(plain_password: str, hashed_password: str, salt: str) -> bool:
    calculated_hash = get_password_hash(password=plain_password, salt=salt)
    return hmac.compare_digest(calculated_hash, hashed_password)
