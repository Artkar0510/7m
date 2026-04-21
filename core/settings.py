from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseModel):
    name: str = "Auth Service"
    version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    debug: bool = False


class PostgresSettings(BaseModel):
    user: str = "postgres"
    password: str = "postgres"
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
    secret_key: str = "change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30


class InternalAuthSettings(BaseModel):
    service_token: str = "internal-service-token"
    service_header: str = "X-Service-Token"


class PasswordHashSettings(BaseModel):
    algorithm: str = "sha256"
    iterations: int = 100_000
    salt_size: int = Field(default=16, ge=16)
    dklen: int = Field(default=32, ge=32)


class Settings(BaseSettings):
    app: AppSettings = AppSettings()
    postgres: PostgresSettings = PostgresSettings()
    redis: RedisSettings = RedisSettings()
    jwt: JwtSettings = JwtSettings()
    internal_auth: InternalAuthSettings = InternalAuthSettings()
    password_hash: PasswordHashSettings = PasswordHashSettings()

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )


settings = Settings()
