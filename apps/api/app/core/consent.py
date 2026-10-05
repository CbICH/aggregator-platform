from uuid import UUID

from sqlalchemy.orm import Session

from app.core.models import RegistrationConsent

CONSENT_VERSION = "registration-v1"
CONSENT_TEXT = (
    "Я согласен на обработку email, данных аккаунта и технических событий безопасности "
    "для регистрации и работы в ФСП Сигнал. Публикация резюме и передача контактов "
    "работодателю требуют отдельных действий."
)


class SqlRegistrationConsent:
    """Implements ConsentWrite without committing the caller's transaction."""

    def __init__(self, db: Session):
        self.db = db

    def record_registration(self, user_id: UUID, version: str) -> None:
        self.db.add(RegistrationConsent(user_id=str(user_id), version=version))
