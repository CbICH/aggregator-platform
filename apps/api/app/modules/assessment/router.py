from fastapi import APIRouter

from app.core.errors import ERROR_RESPONSES

router = APIRouter(tags=["Assessment"], responses=ERROR_RESPONSES)
