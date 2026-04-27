from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.settings import settings


engine = create_async_engine(
    settings.postgres.url,
    echo=settings.app.debug,
    pool_size=settings.postgres.pool_size, 
    max_overflow=settings.postgres.max_overflow,
    pool_pre_ping=True, 
)

SessionLocal = async_sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        await db.close()