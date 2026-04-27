from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_salt: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    yandex_user_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    google_user_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    vk_user_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    region_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    last_device_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )