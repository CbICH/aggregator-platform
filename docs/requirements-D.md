# Матрица требований D

Срез 9 октября 2026. Тесты названы по актуальным файлам в `apps/api/tests/`. Изолированный браузер D использует контролируемые порты; `tests/bcd-integration.spec.ts` проверяет настоящий B, компанию C и D на Docker-стенде.

| ID | Поведение | Авторитетная проверка |
|---|---|---|
| R03 | Все ручные поля профиля/контактов сохраняются | `test_profiles.py`, `tests/profile.spec.ts` |
| R04 | Стандартный PDF, кириллица, длинный текст, только владелец | `test_profile_pdf.py`; скачивание в `tests/d/invitations.spec.ts` |
| R13 | Входящие, просмотр, принять/отклонить | `test_full_invitation_flow_and_snapshot`, `test_owned_need_and_csrf`; D E2E |
| R15 | Согласия/видимость влияют на live API | `test_privacy.py`, отзыв grants и processing, D E2E |
| R18 | Кандидат читает/изменяет только свои данные | `test_profiles.py`, `test_foreign_candidate_company_and_employer_decision_are_denied`, PDF guards |
| R23 | Предложение без вакансии | `test_full_invitation_flow_and_snapshot`, `test_invalid_refs_and_fields`; D E2E |
| R25 | Контакты только принявшей компании, отзыв без восстановления повтором | `test_revoked_contact_grant_is_not_resurrected_by_accept_replay`, foreign-company test, D E2E |
| R28 | Положительный целый RUB-диапазон и min≤max | `test_invalid_salary_rejected_before_storage`, общие salary contract tests |
| R29 | Company/описание/зарплата/связь до общения; immutable snapshot | `test_full_invitation_flow_and_snapshot`; D E2E |
| R30 | Статусы обеих сторон, повторы, конкуренция | `test_concurrent_decisions_have_one_final_status_and_one_event`, repeated view/decision, D E2E |
| R41 | A auth/CSRF/roles + владение D, приватный audit, лимиты | весь `test_auth.py`, `test_d_audit.py`, private DTO/PDF tests |

## Границы доказательства

Готовы исходники, API/UI D, миграции, синтетические данные и проверки SQLite/PostgreSQL. В `D` подключены B, компания C, сохранённые потребности и демонстрационный ranking C. `test_bcd_integration.py` и `tests/bcd-integration.spec.ts` подтверждают реальный тест/категорию B, компанию C, публикацию, приглашение, контакты и отзыв D. Полный G1/G2 ещё требует ranking через live ProfileRead/AssessmentRead и backend связи ФСП ID. CI опубликованного D (`2fb0793`) прошёл 3/3; новый локальный merge ещё не опубликован и своего CI не имеет. Локальные проверки обновлений: 131 API-тест на каждой СУБД, пять миграционных исходных состояний, рабочие UI-сценарии и 28 независимых проб.

Контракт перехода из будущей live-подборки C в форму D: `/employer/invitations/new?candidate_id=<uuid>&need_id=<optional uuid>`. Демо-карточка C пока такой переход не создаёт. D повторно проверяет кандидата и принадлежность потребности; параметры ссылки не дают права доступа.
