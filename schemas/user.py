from datetime import date

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    email: EmailStr
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    region_code: str | None = Field(default=None, min_length=1, max_length=32)
    birth_date: date | None = None
    last_device_type: str | None = Field(default=None, min_length=1, max_length=32)


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserResponse(UserBase):
    is_active: bool

    model_config = {"from_attributes": True}
