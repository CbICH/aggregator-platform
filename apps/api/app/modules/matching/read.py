"""Read-only company adapter consumed by D within the request transaction."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.contracts.schemas import CompanySummary
from app.modules.matching.models import Company


class SqlAlchemyCompanyRead:
    def __init__(self, db: Session):
        self.db = db

    def get_summary(self, company_id: UUID) -> CompanySummary | None:
        company = self.db.get(Company, str(company_id))
        if company is None:
            return None
        return CompanySummary(
            company_id=company.id,
            name=company.name,
            contact=company.contact_email,
        )

    def owns_need(self, company_id: UUID, need_id: UUID) -> bool:
        # The incoming C branch has no persisted needs yet; never authorize a supplied ID.
        return False

    def owns_vacancy(self, company_id: UUID, vacancy_id: UUID) -> bool:
        return False
