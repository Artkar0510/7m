from utils.security import hash_password, verify_password


def test_hash_password_uses_dynamic_salt() -> None:
    first_hash, first_salt = hash_password("strong-password")
    second_hash, second_salt = hash_password("strong-password")

    assert first_salt != second_salt
    assert first_hash != second_hash


def test_verify_password_validates_hash_with_salt() -> None:
    hashed_password, salt = hash_password("strong-password")

    assert verify_password("strong-password", hashed_password, salt) is True
    assert verify_password("wrong-password", hashed_password, salt) is False
