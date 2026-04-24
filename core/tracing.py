from uuid import uuid4

from fastapi import FastAPI, Request, Response
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from core.settings import settings

REQUEST_ID_ATTRIBUTE = "http.request_id"


def _normalize_request_id(value: str | None) -> str:
    if value is None:
        return str(uuid4())

    normalized_value = value.strip()
    if normalized_value:
        return normalized_value
    return str(uuid4())


def _build_resource() -> Resource:
    return Resource.create(
        {
            "service.name": settings.tracing.service_name,
            "service.version": settings.app.version,
        }
    )


def configure_request_id_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next) -> Response:
        request_id = _normalize_request_id(
            request.headers.get(settings.tracing.request_id_header)
        )
        request.state.request_id = request_id

        current_span = trace.get_current_span()
        if current_span.is_recording():
            current_span.set_attribute(REQUEST_ID_ATTRIBUTE, request_id)

        response = await call_next(request)
        response.headers[settings.tracing.request_id_header] = request_id
        return response


def configure_tracing(app: FastAPI) -> None:
    if getattr(app.state, "tracing_configured", False):
        return

    if settings.tracing.enabled:
        tracer_provider = TracerProvider(resource=_build_resource())
        span_exporter = OTLPSpanExporter(endpoint=settings.tracing.jaeger_endpoint)
        tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(tracer_provider)
        FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider)
        app.state.tracer_provider = tracer_provider

    app.state.tracing_configured = True


def shutdown_tracing(app: FastAPI) -> None:
    if not settings.tracing.enabled:
        return

    tracer_provider = getattr(app.state, "tracer_provider", None)
    if tracer_provider is None:
        return

    tracer_provider.shutdown()
