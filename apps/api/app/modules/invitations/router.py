from fastapi import APIRouter

from app.core.errors import ERROR_RESPONSES

router = APIRouter(tags=["Invitations"], responses=ERROR_RESPONSES)
