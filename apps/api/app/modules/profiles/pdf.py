"""Owner-only, deterministic-layout PDF using bundled Unicode fonts."""

from html import escape
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.modules.profiles.schemas import CandidateSelf

ASSETS = Path(__file__).parent / "assets"
pdfmetrics.registerFont(TTFont("NotoSans", str(ASSETS / "NotoSans-Regular.ttf")))
pdfmetrics.registerFont(TTFont("NotoSansBold", str(ASSETS / "NotoSans-Bold.ttf")))

FSP_LABELS = {
    "not_linked": "ФСП ID не связан",
    "linked_empty": "ФСП ID связан; истории достижений нет",
    "linked_with_data": "Есть данные о достижениях ФСП",
    "unavailable": "Источник ФСП недоступен",
}
ROLE_LABELS = {
    "backend": "Backend",
    "frontend": "Frontend",
    "fullstack": "Fullstack",
    "qa": "QA",
    "devops": "DevOps",
    "data": "Данные и аналитика",
    "mobile": "Мобильная разработка",
    "other": "Другая роль",
}


def render_profile(profile: CandidateSelf) -> bytes:
    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title="Профиль кандидата — ФСП Сигнал",
        author="ФСП Сигнал",
    )
    body = ParagraphStyle(
        "Body", fontName="NotoSans", fontSize=10, leading=15, spaceAfter=7, splitLongWords=True
    )
    title = ParagraphStyle(
        "Title",
        parent=body,
        fontName="NotoSansBold",
        fontSize=22,
        leading=28,
        textColor=colors.HexColor("#541478"),
        spaceAfter=18,
    )
    heading = ParagraphStyle(
        "Heading",
        parent=body,
        fontName="NotoSansBold",
        fontSize=13,
        leading=18,
        spaceBefore=15,
        spaceAfter=9,
        keepWithNext=True,
    )
    story = []

    def text(value, style=body):
        safe = escape(str(value)).replace("\n", "<br/>")
        story.append(Paragraph(safe, style))

    text("ФСП Сигнал", heading)
    text(profile.full_name or "Профиль кандидата", title)
    text("Личный экземпляр профиля. Содержит ваши контактные данные.")
    text("Контакты", heading)
    text(f"Email: {profile.contacts.email or 'не указан'}")
    text(f"Телефон: {profile.contacts.phone or 'не указан'}")
    if profile.contacts.contact_method:
        text(f"Способ связи: {profile.contacts.contact_method}")
    text("Опыт и технологии", heading)
    text("Роли: " + (", ".join(ROLE_LABELS[role] for role in profile.roles) or "не указаны"))
    text(f"Стаж: {profile.experience_months} мес.")
    text("Заявленный стек: " + (", ".join(profile.declared_stack) or "не указан"))
    text("Софт-скиллы: " + (", ".join(profile.soft_skills) or "не указаны"))
    text("Подтверждение навыков", heading)
    category = profile.verified_category
    if category:
        text(f"Категория: {category.category_code}; результат теста: {category.test_score:g}/100")
        text(
            "Подтверждённые навыки: "
            + ", ".join(f"{skill.id}: {skill.score:g}/100" for skill in category.skills)
        )
    else:
        text(
            "Категория пока не подтверждена. Заявленный опыт не является результатом тестирования."
        )
    text("Профиль ФСП", heading)
    text(FSP_LABELS[profile.fsp.status])
    if profile.fsp.status == "linked_with_data":
        text(
            f"Сигнал ФСП: {profile.fsp.signal:g}/100; источник: {'демонстрационные данные' if profile.fsp.source == 'demo' else 'реестр'}"
        )
    if profile.fsp.fsp_id:
        text("Связанный ФСП ID: " + profile.fsp.fsp_id)
    for achievement in profile.fsp.achievements:
        text(f"{achievement.event}: {achievement.result}; {achievement.date or 'дата не указана'}")
    text("О себе и опыте", heading)
    # Bounded chunks let a long unbroken resume safely span pages.
    resume = profile.resume_text or "Описание пока не добавлено."
    for start in range(0, len(resume), 1200):
        text(resume[start : start + 1200])
    story.append(Spacer(1, 8 * mm))

    def footer(canvas, _doc):
        canvas.setFont("NotoSans", 8)
        canvas.setFillColor(colors.HexColor("#666070"))
        canvas.drawString(20 * mm, 10 * mm, "ФСП Сигнал · Личный профиль")
        canvas.drawRightString(A4[0] - 20 * mm, 10 * mm, f"Страница {_doc.page}")

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
