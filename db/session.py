from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from core.settings import settings

engine = create_engine(settings.postgres.url, echo=settings.app.debug)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
