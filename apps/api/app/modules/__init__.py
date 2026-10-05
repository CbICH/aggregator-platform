"""Composition point. Module owners edit their router, not this registry."""

from fastapi import FastAPI

from app.modules.assessment.router import router as assessment
from app.modules.fsp.router import router as fsp
from app.modules.invitations.router import router as invitations
from app.modules.matching.router import router as matching
from app.modules.profiles.router import router as profiles


def register_modules(app: FastAPI):
    for router in (assessment, matching, fsp, profiles, invitations):
        app.include_router(router, prefix="/api/v1")
