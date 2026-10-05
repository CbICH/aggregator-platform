from fastapi import APIRouter

from app.core.errors import ERROR_RESPONSES

router = APIRouter(tags=["FSP"], responses=ERROR_RESPONSES)
