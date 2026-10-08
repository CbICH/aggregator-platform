import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.contracts.schemas import DTO
from app.core.auth import router as auth_router
from app.core.catalogs import router as catalogs_router
from app.core.config import Settings
from app.core.db import get_db, make_engine, make_session_factory
from app.core.errors import ERROR_RESPONSES, AppError, error_response, install_errors
from app.core.mail import Mailer, SmtpMailer
from app.core.models import User
from app.modules import register_modules


class Health(DTO):
    status: str
    version: str = "0.1.0"


def create_app(settings: Settings | None = None, *, mailer: Mailer | None = None) -> FastAPI:
    cfg = settings or Settings()
    engine = make_engine(cfg.database_url)

    @asynccontextmanager
    async def lifespan(_app):
        yield
        engine.dispose()

    app = FastAPI(
        title="ФСП Сигнал API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
        description="Общий слой A. Доменные методы добавляются владельцами B/C/D.",
    )
    app.state.settings = cfg
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.mailer = mailer or SmtpMailer(cfg)
    install_errors(app)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        request.state.request_id = str(uuid4())
        origin = request.headers.get("origin")
        if (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and origin
            and origin != cfg.public_app_url
        ):
            response = error_response(
                request, 403, "ORIGIN_FORBIDDEN", "Источник запроса не разрешён"
            )
        else:
            try:
                response = await call_next(request)
            except Exception as exc:
                logging.getLogger(__name__).error(
                    "request_failed request_id=%s type=%s",
                    request.state.request_id,
                    type(exc).__name__,
                )
                response = error_response(
                    request, 500, "INTERNAL_ERROR", "Не удалось выполнить запрос"
                )
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/v1/health", tags=["Operations"], response_model=Health)
    def health():
        return Health(status="ok")

    @app.get("/api/v1/ready", tags=["Operations"], response_model=Health, responses=ERROR_RESPONSES)
    def ready(db: Session = Depends(get_db)):
        try:
            db.execute(select(User.id).limit(1))
        except SQLAlchemyError:
            raise AppError(503, "DATABASE_UNAVAILABLE", "База данных не готова") from None
        return Health(status="ready")

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(catalogs_router, prefix="/api/v1")
    register_modules(app)
    from app.modules.profiles.dependencies import configure_d

    configure_d(app)
    return app


app = create_app()
