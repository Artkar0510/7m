from fastapi import FastAPI

from api.v1.router import api_router
from core.settings import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app.name,
        version=settings.app.version,
        debug=settings.app.debug,
    )
    app.include_router(api_router, prefix=settings.app.api_v1_prefix)
    return app


app = create_app()
