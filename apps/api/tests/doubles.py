"""Controlled B/C ports for D tests only; never imported by the application."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.contracts.schemas import CompanySummary, FspEvidence, SkillEvidence, VerifiedCategory


class AssessmentDouble:
    def __init__(self):
        self.categories = {}

    def get_verified(self, candidate_id):
        return self.categories.get(str(candidate_id))

    def verify(self, candidate_id):
        assigned = datetime(2026, 10, 7, tzinfo=UTC)
        self.categories[str(candidate_id)] = VerifiedCategory(
            candidate_id=candidate_id,
            category_code="backend:middle",
            specialization="backend",
            verified_grade="middle",
            test_score=80,
            assessment_id=UUID("30000000-0000-4000-8000-000000000001"),
            assessment_version="backend-v1",
            assigned_at=assigned,
            next_change_at=assigned + timedelta(days=90),
            skills=[SkillEvidence(id="python", score=80), SkillEvidence(id="sql", score=75)],
        )


class CompanyDouble:
    def __init__(self):
        self.companies = {}
        self.needs = {}

    def get_summary(self, company_id):
        return self.companies.get(str(company_id))

    def owns_need(self, company_id, need_id):
        return self.needs.get(str(need_id)) == str(company_id)

    def owns_vacancy(self, company_id, vacancy_id):
        return False

    def add(self, company_id, name):
        self.companies[str(company_id)] = CompanySummary(
            company_id=company_id, name=name, contact="hr@example.com"
        )


class FspDouble:
    def get_evidence(self, candidate_id):
        return FspEvidence(status="not_linked", source="demo")
