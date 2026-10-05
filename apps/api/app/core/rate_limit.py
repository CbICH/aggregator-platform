import time

from fastapi import Request
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.core.errors import AppError
from app.core.models import RateWindow
from app.core.security import digest


def rate_limit(request: Request, scope: str, identity: str, *, limit: int, seconds: int):
    """Atomic, database-backed limit shared by workers. Never trusts X-Forwarded-For here."""
    now = int(time.time())
    window = now // seconds
    key = digest(f"{scope}:{identity}")
    with request.app.state.session_factory.begin() as db:
        insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
        stmt = insert(RateWindow).values(key=key, window=window, count=1)
        count = db.scalar(
            stmt.on_conflict_do_update(
                index_elements=[RateWindow.key, RateWindow.window],
                set_={"count": RateWindow.count + 1},
            ).returning(RateWindow.count)
        )
        # Cleanup only this identity/scope; other scopes may use a different window size.
        db.execute(delete(RateWindow).where(RateWindow.key == key, RateWindow.window < window - 1))
    if count > limit:
        raise AppError(
            429,
            "RATE_LIMITED",
            "Слишком много попыток. Попробуйте позже",
            {"retry_after_seconds": seconds - now % seconds},
        )


def auth_limits(request: Request, scope: str, email: str):
    ip = request.client.host if request.client else "unknown"
    rate_limit(request, f"{scope}:ip", ip, limit=30, seconds=60)
    rate_limit(request, f"{scope}:email", email, limit=5, seconds=300)
