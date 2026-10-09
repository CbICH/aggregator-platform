"""Live matching through B/D/FSP read ports, with company-owned search history."""

from datetime import UTC
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts.ports import AssessmentRead, FspRead, ProfileRead
from app.contracts.schemas import ActorContext, CandidatePublic, FspEvidence
from app.core.catalogs import catalogs
from app.core.errors import AppError
from app.modules.matching.models import Company, EmployerNeed, SearchSnapshot
from app.modules.matching.schemas import (
    CandidateCard,
    CandidateList,
    CategoryCard,
    CategoryList,
    SearchFilters,
    SearchHistory,
    SearchResponse,
    SearchSummary,
)

WEIGHT_TEST_NO_NEED = 0.90
WEIGHT_FSP_NO_NEED = 0.10
WEIGHT_TEST_WITH_NEED = 0.65
WEIGHT_RELEVANCE_WITH_NEED = 0.25
WEIGHT_FSP_WITH_NEED = 0.10


def relevance(skills: dict[str, float], required: list[dict]) -> float:
    total_weight = sum(skill["weight"] for skill in required)
    return (
        sum(skill["weight"] * skills.get(skill["id"], 0) for skill in required) / total_weight
        if total_weight
        else 0
    )


def score_profile(
    profile: CandidatePublic, evidence: FspEvidence, need: dict | None
) -> CandidateCard:
    category = profile.verified_category
    if category is None:
        raise ValueError("Only verified categories can be ranked")
    test = category.test_score
    fsp = evidence.signal if evidence.status == "linked_with_data" else 0
    skills = {skill.id: skill.score for skill in category.skills}
    required = need["required_skills"] if need else []
    reasons = [{"code": "GRADE_VERIFIED", "label": f"{category.category_code} подтверждена тестом"}]
    if need:
        match = relevance(skills, required)
        score = (
            WEIGHT_TEST_WITH_NEED * test
            + WEIGHT_RELEVANCE_WITH_NEED * match
            + WEIGHT_FSP_WITH_NEED * fsp
        )
        components = {"test": test, "relevance": match, "fsp": fsp}
        reasons.extend(
            {"code": "SKILL_MATCH", "skill_id": skill["id"], "score": skills[skill["id"]]}
            if skill["id"] in skills
            else {
                "code": "SKILL_NOT_ASSESSED",
                "skill_id": skill["id"],
                "label": f"{skill['id']} не проверялся в тесте",
            }
            for skill in required
        )
    else:
        score = WEIGHT_TEST_NO_NEED * test + WEIGHT_FSP_NO_NEED * fsp
        components = {"test": test, "fsp": fsp}
        reasons.extend(
            {"code": "SKILL", "skill_id": key, "score": value} for key, value in skills.items()
        )
    if evidence.status == "linked_with_data":
        reasons.append(
            {
                "code": "FSP_SIGNAL",
                "label": "Достижения демонстрационного реестра учтены"
                if evidence.source == "demo"
                else "Достижения реестра ФСП учтены",
                "score": fsp,
            }
        )
    elif evidence.status == "unavailable":
        reasons.append(
            {"code": "FSP_UNAVAILABLE", "label": "Реестр ФСП недоступен; подбор работает по тесту"}
        )
    else:
        reasons.append(
            {
                "code": "FSP_NO_HISTORY",
                "label": "Без истории ФСП; результат теста учитывается полностью",
            }
        )
    return CandidateCard(
        **profile.model_dump(),
        specialization=category.specialization,
        verified_grade=category.verified_grade,
        category_code=category.category_code,
        experience_years=profile.experience_months / 12
        if profile.experience_months is not None
        else None,
        score=round(score, 1),
        components=components,
        skills=[skill.model_dump(include={"id", "score"}) for skill in category.skills],
        fsp_status=evidence.status,
        fsp_source=evidence.source,
        fsp_achievements=evidence.achievements,
        reasons=reasons,
    )


class MatchingService:
    def __init__(
        self, db: Session, profiles: ProfileRead, assessments: AssessmentRead, fsp: FspRead
    ):
        self.db, self.profiles, self.assessments, self.fsp = db, profiles, assessments, fsp

    def company_id(self, actor: ActorContext) -> str:
        company = self.db.scalar(select(Company).where(Company.owner_user_id == str(actor.user_id)))
        if company is None or company.id != str(actor.company_id):
            raise AppError(409, "COMPANY_REQUIRED", "Сначала заполните профиль компании")
        return company.id

    def need(self, actor: ActorContext, need_id: UUID | None) -> dict | None:
        company_id = self.company_id(actor)
        if need_id is None:
            return None
        need = self.db.get(EmployerNeed, str(need_id))
        if need is None or need.company_id != company_id:
            raise AppError(404, "NEED_NOT_FOUND", "Потребность не найдена")
        return {
            "id": need.id,
            "title": need.title,
            "specialization": need.specialization,
            "grades": need.grades,
            "declared_stack": need.declared_stack,
            "required_skills": need.required_skills,
        }

    def public_profiles(self, actor: ActorContext) -> list[CandidatePublic]:
        cursor = None
        profiles = []
        while True:
            page = self.profiles.list_public(actor, after=cursor, limit=50)
            profiles.extend(page)
            if len(page) < 50:
                return profiles
            cursor = page[-1].candidate_id

    def evidence(self, candidate_id: UUID) -> FspEvidence:
        try:
            return self.fsp.get_evidence(candidate_id)
        except (TimeoutError, ConnectionError):
            return FspEvidence(status="unavailable")
        except AppError as exc:
            if exc.status == 503:
                return FspEvidence(status="unavailable")
            raise

    def rank(
        self,
        profiles: list[CandidatePublic],
        filters: SearchFilters,
        need: dict | None,
        *,
        apply_filters: bool = True,
    ) -> list[CandidateCard]:
        ranked = []
        for profile in profiles:
            category = self.assessments.get_verified(profile.candidate_id)
            if category is None or category.candidate_id != profile.candidate_id:
                continue
            profile = profile.model_copy(update={"verified_category": category})
            if apply_filters:
                if need and (
                    category.specialization != need["specialization"]
                    or category.verified_grade not in need["grades"]
                ):
                    continue
                if filters.specialization and category.specialization != filters.specialization:
                    continue
                if filters.grade and category.verified_grade != filters.grade:
                    continue
                if filters.category_code and category.category_code != filters.category_code:
                    continue
                # Filtering hidden fields would reveal them through membership/counts.
                stack = filters.stack or (need.get("declared_stack", []) if need else [])
                if stack and (
                    profile.declared_stack is None
                    or not set(stack).issubset(set(profile.declared_stack))
                ):
                    continue
            evidence = self.evidence(profile.candidate_id)
            if apply_filters and filters.with_fsp_only and evidence.status != "linked_with_data":
                continue
            ranked.append(score_profile(profile, evidence, need))
        ranked.sort(key=lambda item: (-item.score, str(item.candidate_id)))
        return ranked

    def search(
        self, actor: ActorContext, filters: SearchFilters, *, limit: int = 20, offset: int = 0
    ) -> CandidateList:
        need = self.need(actor, filters.need_id)
        ranked = self.rank(self.public_profiles(actor), filters, need)
        return self.page(ranked, filters.need_id, limit, offset)

    @staticmethod
    def page(
        ranked: list[CandidateCard], need_id: UUID | None, limit: int, offset: int
    ) -> CandidateList:
        return CandidateList(
            items=ranked[offset : offset + limit],
            total=len(ranked),
            applied_need_id=need_id,
            limit=limit,
            next_offset=offset + limit if offset + limit < len(ranked) else None,
        )

    def categories(self, actor: ActorContext) -> CategoryList:
        self.company_id(actor)
        counts = {}
        for profile in self.public_profiles(actor):
            category = profile.verified_category
            if category:
                counts[category.category_code] = counts.get(category.category_code, 0) + 1
        return CategoryList(
            items=[
                CategoryCard(
                    code=item.id,
                    specialization=item.id.split(":")[0],
                    grade=item.id.split(":")[1],
                    active=item.active,
                    candidate_count=counts.get(item.id, 0),
                )
                for item in catalogs().categories
            ]
        )

    @staticmethod
    def summary(snapshot: SearchSnapshot) -> SearchSummary:
        created = snapshot.created_at
        return SearchSummary(
            id=snapshot.id,
            created_at=created.replace(tzinfo=UTC) if created.tzinfo is None else created,
            filters=snapshot.filters,
            original_total=len(snapshot.candidate_ids),
            need_title=snapshot.need_snapshot["title"] if snapshot.need_snapshot else None,
        )

    def create_snapshot(self, actor: ActorContext, filters: SearchFilters) -> SearchResponse:
        company_id = self.company_id(actor)
        need = self.need(actor, filters.need_id)
        ranked = self.rank(self.public_profiles(actor), filters, need)
        snapshot = SearchSnapshot(
            company_id=company_id,
            filters=filters.model_dump(mode="json"),
            need_snapshot=need,
            candidate_ids=[str(item.candidate_id) for item in ranked],
        )
        self.db.add(snapshot)
        self.db.flush()
        return SearchResponse(
            **self.summary(snapshot).model_dump(),
            **self.page(ranked, filters.need_id, 20, 0).model_dump(),
        )

    def get_snapshot(
        self, actor: ActorContext, snapshot_id: UUID, *, limit: int, offset: int
    ) -> SearchResponse:
        company_id = self.company_id(actor)
        snapshot = self.db.scalar(
            select(SearchSnapshot).where(
                SearchSnapshot.id == str(snapshot_id), SearchSnapshot.company_id == company_id
            )
        )
        if snapshot is None:
            raise AppError(404, "SEARCH_NOT_FOUND", "Подборка не найдена")
        # Re-read all public fields and B/FSP results; never replay a stale public DTO.
        profiles = [
            profile
            for key in snapshot.candidate_ids
            if (profile := self.profiles.get_public(UUID(key), actor)) is not None
        ]
        filters = SearchFilters.model_validate(snapshot.filters)
        ranked = self.rank(profiles, filters, snapshot.need_snapshot, apply_filters=False)
        return SearchResponse(
            **self.summary(snapshot).model_dump(),
            **self.page(ranked, filters.need_id, limit, offset).model_dump(),
            unavailable_count=len(snapshot.candidate_ids) - len(ranked),
        )

    def history(self, actor: ActorContext, *, limit: int, offset: int) -> SearchHistory:
        company_id = self.company_id(actor)
        snapshots = self.db.scalars(
            select(SearchSnapshot)
            .where(SearchSnapshot.company_id == company_id)
            .order_by(SearchSnapshot.created_at.desc(), SearchSnapshot.id.desc())
            .offset(offset)
            .limit(limit + 1)
        ).all()
        return SearchHistory(
            items=[self.summary(item) for item in snapshots[:limit]],
            next_offset=offset + limit if len(snapshots) > limit else None,
        )
