from fastapi import APIRouter

from app.contracts.schemas import DTO
from app.core.errors import ERROR_RESPONSES

router = APIRouter(tags=["Catalogs"], responses=ERROR_RESPONSES)


class CatalogItem(DTO):
    id: str
    label: str
    active: bool = True


class Catalogs(DTO):
    version: str
    specializations: list[CatalogItem]
    grades: list[CatalogItem]
    skills: list[CatalogItem]
    stack: list[CatalogItem]
    categories: list[CatalogItem]


@router.get("/catalogs", response_model=Catalogs)
def catalogs():
    return Catalogs(
        version="0.1.0",
        specializations=[
            CatalogItem(id="backend", label="Backend"),
            CatalogItem(id="qa", label="QA"),
        ],
        grades=[CatalogItem(id=g, label=g.title()) for g in ("junior", "middle", "senior")],
        skills=[
            CatalogItem(id=k, label=v)
            for k, v in {
                "api.behavior": "Поведение API",
                "api.idempotency": "Идемпотентность",
                "data.sql": "SQL",
                "data.boundaries": "Граничные случаи",
                "qa.test_design": "Проектирование тестов",
                "qa.defect_analysis": "Анализ дефектов",
                "qa.risk_priority": "Приоритизация рисков",
            }.items()
        ],
        stack=[CatalogItem(id=s, label=s) for s in ("python", "postgresql", "javascript")],
        # B enables only categories with implemented and validated assessments.
        categories=[
            CatalogItem(id=f"{s}:{g}", label=f"{s.title()} · {g.title()}", active=False)
            for s in ("backend", "qa")
            for g in ("junior", "middle", "senior")
        ],
    )
