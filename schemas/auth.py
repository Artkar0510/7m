from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    access_token_expires_in: int
    refresh_token_expires_in: int


class LogoutRequest(BaseModel):
    refresh_token: str


class AccessTokenIntrospectRequest(BaseModel):
    access_token: str


class AccessTokenIntrospectResponse(BaseModel):
    active: bool
    user_id: int
    email: EmailStr
    token_type: str
    expires_at: int
