from utils.jwt import create_refresh_token, decode_refresh_token


def test_refresh_token_contains_refresh_type() -> None:
    refresh_token, _ = create_refresh_token(user_id=1, email="user@example.com")

    payload = decode_refresh_token(refresh_token)

    assert payload["type"] == "refresh"
    assert payload["email"] == "user@example.com"
