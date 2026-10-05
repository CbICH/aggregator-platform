# Как B/C/D подключают свои модули

## Backend

Маршрутизаторы уже зарегистрированы в `app/modules/__init__.py`. Добавляйте методы в `app/modules/<module>/router.py` и свою внутреннюю структуру. Не добавляйте фиктивные успешные ответы на несуществующие операции.

```python
from typing import Annotated
from fastapi import Depends
from sqlalchemy.orm import Session
from app.contracts.schemas import ActorContext, Role
from app.core.db import get_db
from app.core.security import require_role
from app.core.errors import AppError

@router.get('/candidate/my-feature')
def my_feature(
    actor: Annotated[ActorContext, Depends(require_role(Role.CANDIDATE))],
    db: Annotated[Session, Depends(get_db)],
):
    # Query only records owned by actor.user_id; missing/foreign ID -> 404.
    # Declare a concrete response_model before merging this example.
    raise AppError(404, 'NOT_FOUND', 'Запись не найдена')
```

`require_role` по умолчанию требует подтверждённый email. Для страниц собственного незавершённого профиля при необходимости используйте `verified=False`. Небезопасные методы, использующие эту зависимость, автоматически требуют CSRF. Проверка роли не заменяет проверку владельца записи/компании.

Добавляйте `response_model`; сырые ORM-объекты не должны случайно сериализовать приватные поля. Для публичной карточки используйте `CandidatePublic`, для контактов — отдельный защищённый DTO. Схемы с `extra=forbid` отклоняют неизвестные поля. `Salary` запрещает дробные/отрицательные рубли, иную валюту и перевёрнутый диапазон.

Модели наследуются от `app.core.db.Base`. Перед генерацией миграции зарегистрируйте импорт моделей в `migrations/env.py`; единую последовательность ревизий согласуйте с A. Текущая база — `0001_core`. Проверяйте миграцию на пустой тестовой базе и отсутствие расхождений через `alembic check`.

## Frontend

Каждый модуль имеет `src/features/<module>/index.ts`, экспортирующий манифест `FeatureModule`. Корневой App автоматически собирает его страницы и пункты навигации.

```tsx
import type { FeatureModule } from '../../shared/module';
import { MyPage } from './MyPage';
export const assessment: FeatureModule = {
  routes: [{ path: '/candidate/assessment', element: <MyPage />, roles: ['candidate'] }],
  navigation: [{ to: '/candidate/assessment', label: 'Мой тест', roles: ['candidate'] }],
};
```

При добавлении JSX переименуйте `index.ts` в `index.tsx`. Корневой импорт останется рабочим. Используйте общий `api()` — он передаёт cookie и CSRF, а также распознаёт единый формат ошибок. `useAuth()` предоставляет текущего пользователя; browser guard помогает навигации, сервер остаётся источником прав.

Общие компоненты `Field`, `Notice` и CSS-классы `.button`, `.primary`, `.field` уже доступны. Функциональные стили держите внутри своей папки; изменение общей палитры и навигации согласуйте с A.

## Контракты, заглушки и генерация

- DTO/Protocol: `app/contracts`.
- Машиночитаемые схемы: `contracts/openapi.json`, `contracts/schemas.json`.
- Начальные вымышленные данные: `fixtures/core.json`.
- Для модульного теста реализуйте только нужный Protocol локальным fake; не добавляйте переключатель обхода авторизации в окружение приложения.
- Клиентские типы: `src/shared/api.generated.ts`; вручную их не редактировать.

После изменения схемы:

```sh
PYTHONPATH=apps/api .venv/bin/python apps/api/scripts/export_contracts.py
cd apps/web
npm run api:types
npm run build
```

CI проверяет, что экспорт не меняет закоммиченные схемы и типы. Новое обязательное поле требует синхронного обновления потребителя и фикстуры; необязательное поле добавлять только с понятной семантикой.

## Перед первой интеграцией

1. B отдаёт реальное подтверждение одного теста; C и D читают его по `AssessmentRead`.
2. D отдаёт безопасный профиль и `is_discoverable`; C заменяет fixture реальным портом.
3. C создаёт компанию, связывает работодателя и предоставляет `CompanyRead`.
4. D реализует приглашение, транзакцию принятия и ContactGrant.
5. A соединяет реализации портов и проверяет полный путь. До этого готовность общей авторизации не означает готовность всего MVP.
