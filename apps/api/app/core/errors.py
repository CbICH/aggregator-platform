from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException


class ErrorDetail(BaseModel):
    code: str
    message: str
    fields: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
    request_id: str


ERROR_RESPONSES = {
    code: {"model": ErrorResponse, "description": text}
    for code, text in {
        400: "Некорректная команда",
        401: "Требуется вход",
        403: "Действие запрещено",
        404: "Объект недоступен",
        409: "Конфликт состояния",
        422: "Ошибка полей",
        429: "Лимит запросов",
        500: "Внутренняя ошибка",
        503: "Зависимость временно недоступна",
    }.items()
}


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, fields=None):
        self.status, self.code, self.message, self.fields = status, code, message, fields


def error_response(request: Request, status: int, code: str, message: str, fields=None):
    return JSONResponse(
        status_code=status,
        content={
            "error": {"code": code, "message": message, "fields": fields},
            "request_id": getattr(request.state, "request_id", "unknown"),
        },
    )


def install_errors(app):
    @app.exception_handler(AppError)
    async def app_error(request, exc):
        return error_response(request, exc.status, exc.code, exc.message, exc.fields)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Never serialize Pydantic's input values: they may include a password or token.
        fields = {".".join(map(str, e["loc"][1:])): e["msg"] for e in exc.errors()}
        return error_response(request, 422, "VALIDATION_ERROR", "Проверьте поля формы", fields)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error_response(request, exc.status_code, "HTTP_ERROR", "Запрос недоступен")
