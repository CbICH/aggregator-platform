"""Server-only generators and rubrics for the 18 assessment templates."""

import random
from dataclasses import dataclass
from typing import Any

GRADE_ORDER = {"junior": 0, "middle": 1, "senior": 2}
FAMILIES = {"backend": ("api", "data", "decision"), "qa": ("defects", "test_design", "risk")}
WEIGHTS = {"api": 40, "data": 35, "decision": 25, "defects": 40, "test_design": 35, "risk": 25}
PASSING_SCORE = 70
NEXT_GRADE_SCORE = 85
SKILLS = {
    "api": ("api.behavior", "api.idempotency"),
    "data": ("data.sql", "data.boundaries"),
    "decision": ("api.behavior",),
    "defects": ("qa.defect_analysis",),
    "test_design": ("qa.test_design",),
    "risk": ("qa.risk_priority",),
}
TITLES = {
    "api": "Поведение API и повторные запросы",
    "data": "Данные, SQL и границы",
    "decision": "Решение при ограничениях",
    "defects": "Поиск дефектов",
    "test_design": "Набор проверок и границы",
    "risk": "Приоритизация рисков",
}


@dataclass(frozen=True)
class Template:
    specialization: str
    grade: str
    family: str

    @property
    def id(self) -> str:
        return f"{self.specialization}-{self.grade}-{self.family}-v1"

    @property
    def weight(self) -> int:
        return WEIGHTS[self.family]


TEMPLATES = tuple(Template(s, g, f) for s, fs in FAMILIES.items() for g in GRADE_ORDER for f in fs)


def templates_for(specialization: str, grade: str) -> tuple[Template, ...]:
    return tuple(
        item for item in TEMPLATES if item.specialization == specialization and item.grade == grade
    )


def question(
    name: str, label: str, kind: str, choices: list[tuple[str, str]] | None = None
) -> dict[str, Any]:
    value: dict[str, Any] = {"name": name, "label": label, "kind": kind}
    if choices:
        value["choices"] = [{"id": key, "label": text} for key, text in choices]
    return value


def variant_choices(
    rng: random.Random, choices: list[tuple[str, str]]
) -> tuple[list[tuple[str, str]], dict[str, str]]:
    """Use seed-derived opaque values so copied request JSON is not a solution key."""
    form_namespace = f"{rng.getrandbits(64):016x}"
    identifiers = [f"option_{form_namespace}_{index}" for index in range(1, len(choices) + 1)]
    rng.shuffle(identifiers)
    mapping = {
        semantic: identifier for (semantic, _), identifier in zip(choices, identifiers, strict=True)
    }
    rendered = [(mapping[semantic], label) for semantic, label in choices]
    rng.shuffle(rendered)
    return rendered, mapping


def build(template: Template, seed: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return public prompt and private rubric. The seed is never returned by the API."""
    rng = random.Random(seed)
    level = GRADE_ORDER[template.grade] + 1
    family = template.family
    if family == "api":
        orders = rng.randint(100 + level * 10, 9_999)
        retries = rng.randint(1, 8 + level)
        retry_choices, retry_values = variant_choices(
            rng,
            [
                ("same", "Вернуть исходный результат"),
                ("new", "Создать новый заказ"),
                ("ignore", "Молча проигнорировать"),
            ],
        )
        fix_choices, fix_values = variant_choices(
            rng,
            [
                ("persist", "Сохранить ключ и результат операции"),
                ("timeout", "Увеличить таймаут"),
                ("disable", "Отключить повторы"),
            ],
        )
        prompt = {
            "title": TITLES[family],
            "scenario": f"Сервис заказов получил {orders} уникальных ключей идемпотентности и {retries} повторных запросов после потери ответа. Заказ создаётся один раз на ключ.",
            "questions": [
                question("created_orders", "Сколько заказов будет создано?", "number"),
                question(
                    "retry",
                    "Как обработать повтор с тем же ключом?",
                    "choice",
                    retry_choices,
                ),
                question(
                    "fix",
                    "Какое исправление сохраняет идемпотентность?",
                    "choice",
                    fix_choices,
                ),
            ],
        }
        rubric = [
            ("created_orders", orders, 20, "equals"),
            ("retry", retry_values["same"], 10, "equals"),
            ("fix", fix_values["persist"], 10, "equals"),
        ]
    elif family == "data":
        rows = rng.randint(100 + level * 10, 9_999)
        boundary_choices, boundary_values = variant_choices(
            rng,
            [
                ("half", "created_at >= start AND created_at < end"),
                ("closed", "created_at >= start AND created_at <= end"),
                ("open", "created_at > start AND created_at < end"),
            ],
        )
        duplicate_choices, duplicate_values = variant_choices(
            rng,
            [
                ("unique", "Обеспечить уникальность ключа операции"),
                ("latest", "Оставить случайную последнюю строку"),
                ("client", "Доверить устранение дублей клиенту"),
            ],
        )
        prompt = {
            "title": TITLES[family],
            "scenario": f"В журнале {rows} записей принадлежат выбранному временному окну. Окна не должны пересекаться на верхней границе.",
            "questions": [
                question("rows", "Сколько строк вернёт корректный запрос?", "number"),
                question(
                    "boundary",
                    "Как выбрать полуоткрытый интервал [start, end)?",
                    "choice",
                    boundary_choices,
                ),
                question(
                    "duplicates",
                    "Как обработать повтор операции?",
                    "choice",
                    duplicate_choices,
                ),
            ],
        }
        rubric = [
            ("rows", rows, 15, "equals"),
            ("boundary", boundary_values["half"], 10, "equals"),
            ("duplicates", duplicate_values["unique"], 10, "equals"),
        ]
    elif family == "decision":
        entity, provider = rng.choice(
            (
                ("заказа", "сервис уведомлений"),
                ("платежа", "сервис чеков"),
                ("возврата", "сервис сообщений"),
            )
        )
        retries = rng.randint(3 + level, 30 + level)
        outage_minutes = rng.randint(10, 180)
        pattern_choices, pattern_values = variant_choices(
            rng,
            [
                ("outbox", "Записать событие в outbox в той же транзакции"),
                ("retry", "Повторять внешний вызов внутри запроса"),
                ("manual", "Попросить клиента отправить заказ ещё раз"),
            ],
        )
        proof_choices, proof_values = variant_choices(
            rng,
            [
                ("idem", "Повтор доставки не создаёт второй заказ"),
                ("fast", "Страница открывается быстрее"),
                ("logs", "В логах стало больше строк"),
            ],
        )
        prompt = {
            "title": TITLES[family],
            "scenario": f"После записи {entity} внешний {provider} недоступен уже {retries} попытки и {outage_minutes} минут. Нужно не потерять событие и не повторить бизнес-операцию.",
            "questions": [
                question(
                    "pattern",
                    "Какое решение выбрать?",
                    "choice",
                    pattern_choices,
                ),
                question(
                    "proof",
                    "Какая проверка подтверждает исправление?",
                    "choice",
                    proof_choices,
                ),
            ],
        }
        rubric = [
            ("pattern", pattern_values["outbox"], 15, "equals"),
            ("proof", proof_values["idem"], 10, "equals"),
        ]
    elif family == "defects":
        first_threshold = level * 100_000 + rng.randint(1_000, 99_000)
        second_threshold = first_threshold * 5
        defect_choices, defect_values = variant_choices(
            rng,
            [
                ("lower", f"{first_threshold - 1} ₽ получает скидку"),
                ("first", f"{first_threshold} ₽ получает 10%"),
                ("upper", f"{second_threshold} ₽ получает 10%"),
                ("rounding", "Скидка округляется вверх без правила"),
            ],
        )
        first_choices, first_values = variant_choices(
            rng,
            [
                (
                    "boundary",
                    f"Границы {first_threshold - 1} / {first_threshold} / {second_threshold}",
                ),
                ("copy", "Текст кнопки"),
                ("color", "Цвет бейджа"),
            ],
        )
        prompt = {
            "title": TITLES[family],
            "scenario": f"Скидка: 10% при сумме от {first_threshold} ₽, 15% от {second_threshold} ₽. В наблюдениях есть расхождения на границах и при округлении.",
            "questions": [
                question(
                    "defects",
                    "Какие наблюдения указывают на дефект?",
                    "multi",
                    defect_choices,
                ),
                question(
                    "first",
                    "Что проверить первым?",
                    "choice",
                    first_choices,
                ),
            ],
        }
        rubric = [
            (
                "defects",
                [defect_values[value] for value in ("lower", "upper", "rounding")],
                30,
                "set_equals",
            ),
            ("first", first_values["boundary"], 10, "equals"),
        ]
    elif family == "test_design":
        first_threshold = level * 100_000 + rng.randint(1_000, 99_000)
        second_threshold = first_threshold * 5
        case_choices, case_values = variant_choices(
            rng,
            [
                ("999", f"{first_threshold - 1} ₽"),
                ("1000", f"{first_threshold} ₽"),
                ("4999", f"{second_threshold - 1} ₽"),
                ("5000", f"{second_threshold} ₽"),
                ("6000", f"{second_threshold + first_threshold} ₽"),
            ],
        )
        oracle_choices, oracle_values = variant_choices(
            rng,
            [
                ("spec", "На согласованную спецификацию"),
                ("previous", "На случайный прошлый ответ"),
                ("ui", "Только на внешний вид формы"),
            ],
        )
        prompt = {
            "title": TITLES[family],
            "scenario": f"Нужно проверить API расчёта скидки с порогами {first_threshold} и {second_threshold} ₽. Базовый положительный сценарий уже покрыт.",
            "questions": [
                question(
                    "cases",
                    "Выберите минимальный набор граничных проверок.",
                    "multi",
                    case_choices,
                ),
                question(
                    "oracle",
                    "На что опирается проверка?",
                    "choice",
                    oracle_choices,
                ),
            ],
        }
        rubric = [
            (
                "cases",
                [case_values[value] for value in ("999", "1000", "4999", "5000")],
                25,
                "set_equals",
            ),
            ("oracle", oracle_values["spec"], 10, "equals"),
        ]
    else:
        endpoint = rng.choice(("платёжного", "возвратного", "переводного"))
        release_window = rng.choice(("15 минут", "30 минут", "час"))
        operations_per_minute = rng.randint(50, 5_000)
        risk_choices, risk_values = variant_choices(
            rng,
            [
                ("double", "Повторное списание"),
                ("amount", "Неверная сумма"),
                ("copy", "Опечатка в тексте"),
                ("spacing", "Отступ в письме"),
            ],
        )
        proof_choices, proof_values = variant_choices(
            rng,
            [
                ("repeat", "Повторить запрос с тем же ключом и сверить одну операцию"),
                ("refresh", "Обновить страницу"),
                ("meeting", "Обсудить риск на встрече"),
            ],
        )
        prompt = {
            "title": TITLES[family],
            "scenario": f"После исправления {endpoint} API есть окно регрессии длиной {release_window}; через него проходит {operations_per_minute} операций в минуту. Риски: повторное списание, неверная сумма и опечатка в уведомлении.",
            "questions": [
                question(
                    "risks",
                    "Какие риски приоритетны перед выпуском?",
                    "multi",
                    risk_choices,
                ),
                question(
                    "proof",
                    "Какая проверка доказывает исправление?",
                    "choice",
                    proof_choices,
                ),
            ],
        }
        rubric = [
            ("risks", [risk_values[value] for value in ("double", "amount")], 15, "set_equals"),
            ("proof", proof_values["repeat"], 10, "equals"),
        ]
    return prompt, [
        {"field": key, "expected": expected, "points": points, "kind": kind}
        for key, expected, points, kind in rubric
    ]


def score(rubric: list[dict[str, Any]], answers: dict[str, Any]) -> float:
    total = 0.0
    for rule in rubric:
        actual, expected = answers.get(rule["field"]), rule["expected"]
        correct = (
            (str(actual) == str(expected))
            if rule["kind"] == "equals"
            else (
                set(map(str, actual if isinstance(actual, list) else [])) == set(map(str, expected))
            )
        )
        if correct:
            total += float(rule["points"])
    return total


def passes_assessment(
    total: float, family_scores: dict[str, float], critical_families: tuple[str, str]
) -> bool:
    return total >= PASSING_SCORE and all(
        family_scores.get(family, 0) >= WEIGHTS[family] / 2 for family in critical_families
    )


def recommends_next_grade(total: float) -> bool:
    return total >= NEXT_GRADE_SCORE
