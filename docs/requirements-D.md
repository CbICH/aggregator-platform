# Матрица требований D

Срез 10 октября 2026. Пути тестов относятся к `apps/api/tests/` и `apps/web/tests/`. Сквозной браузер использует реальные A/B/C/D API на Docker/PostgreSQL и явно синтетический FSP-реестр.

| ID | Поведение | Проверка |
|---|---|---|
| R03 | Все ручные поля профиля/контактов сохраняются | `test_profiles.py`, `profile.spec.ts` |
| R04 | Стандартный PDF, кириллица, длинный текст, только владелец | `test_profile_pdf.py`, `d/invitations.spec.ts` |
| R13 | Входящие, просмотр, принять/отклонить | `test_invitations.py`, D E2E |
| R15 | Согласия/видимость меняют live API и старые подборки | `test_privacy.py`, `test_matching.py`, BCD E2E |
| R16 / D09 | Собственный ФСП ID, четыре состояния и история | `test_fsp.py`, `bcd-integration.spec.ts`; demo-source явно обозначен |
| R18 | Кандидат читает/изменяет только свои данные | `test_profiles.py`, foreign candidate/PDF guards |
| R23 | Предложение без вакансии | `test_invitations.py`, D и BCD E2E |
| R25 | Контакты только принявшей компании; отзыв без восстановления повтором | `test_contact_access.py`, гонки в `test_d_concurrency.py`, D E2E |
| R28 | Положительный целый RUB-диапазон, min≤max | `test_invitations.py`, `test_d_contracts.py` |
| R29 | Название компании, описание, зарплата, связь до общения; immutable snapshot | `test_invitations.py`, BCD E2E |
| R30 | Статусы обеих сторон, повторы, конкуренция | `test_d_concurrency.py`, D E2E |
| R41 | Auth/CSRF/roles, владение D, приватный audit, лимиты | `test_auth.py`, `test_d_audit.py`, DTO/PDF tests |
| C/D: R20/R22/R26 | Потребность, пять фильтров, ранжирование по реальным B/D | `test_matching.py`, BCD E2E |
| C/D: R27 | Уточнение и возврат к исходной подборке с актуальной приватностью | `test_matching.py`, BCD E2E |

Проверено 149 API-тестов на каждой СУБД, шесть миграционных исходных состояний, production Chromium-сценарии и отдельный D E2E. История сохраняет membership, но перечитывает актуальные безопасные поля и результаты. Переход `/employer/invitations/new?candidate_id=<uuid>&need_id=<optional uuid>` предзаполняет условия; API заново проверяет кандидата и владельца потребности.

G1 подтверждён сквозным путём регистрации → тестирования → live-подбора → приглашения → контактов. Готовность общего G2 по всей команде нельзя вывести только из D: внешний пилот/валидация B и финальные командные материалы проверяются отдельно. Изолированный D E2E использует контролируемые B/C ports и дополняет основной production-сценарий.
