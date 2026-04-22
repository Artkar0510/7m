from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).parent.parent


class AppSettings(BaseModel):
    name: str = "Auth Service"
    version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    debug: bool = False


class PostgresSettings(BaseModel):
    user: str = "postgres"
    password: str
    host: str = "localhost"
    port: int = 5432
    db: str = "auth_service"
    url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/auth_service"


class RedisSettings(BaseModel):
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    url: str = "redis://localhost:6379/0"
    user_cache_ttl_seconds: int = 300
    user_cache_prefix: str = "auth:user"
    refresh_blacklist_prefix: str = "auth:blacklist:refresh"


class JwtSettings(BaseModel):
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30


class InternalAuthSettings(BaseModel):
    service_token: str
    service_header: str = "X-Service-Token"


class PasswordHashSettings(BaseModel):
    algorithm: str = "sha256"
    iterations: int = 100_000
    salt_size: int = Field(default=16, ge=16)
    dklen: int = Field(default=32, ge=32)


class AuthSettings(BaseModel):
    login_rate_limit: str = "10/minute"
    register_rate_limit: str = "10/minute"


class Settings(BaseSettings):
    app: AppSettings = Field(default_factory=AppSettings)
    postgres: PostgresSettings
    redis: RedisSettings = Field(default_factory=RedisSettings)
    jwt: JwtSettings
    internal_auth: InternalAuthSettings
    password_hash: PasswordHashSettings = Field(default_factory=PasswordHashSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)

    model_config = SettingsConfigDict(
        env_file=BASE_DIR /".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )


settings = Settings()
