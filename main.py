from contextlib import asynccontextmanager

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api.v1.router import api_router
from core.rate_limit import limiter
from core.settings import settings
from core.tracing import configure_request_id_middleware, configure_tracing, shutdown_tracing
from db.redis import close_redis_client, init_redis_client
from db.session import engine


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await init_redis_client()
        try:
            yield
        finally:
            shutdown_tracing(app)
            await close_redis_client()
            await engine.dispose()

    app = FastAPI(
        title=settings.app.name,
        version=settings.app.version,
        debug=settings.app.debug,
        lifespan=lifespan,
    )
    app.state.limiter = limiter
    configure_request_id_middleware(app)
    configure_tracing(app)
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(api_router, prefix=settings.app.api_v1_prefix)
    return app


app = create_app()
