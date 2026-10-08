"""Build the standalone D handoff PDF from its Markdown source."""

from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate

root = Path(__file__).resolve().parents[1]
fonts = root / "apps/api/app/modules/profiles/assets"
pdfmetrics.registerFont(TTFont("NotoSans", str(fonts / "NotoSans-Regular.ttf")))
pdfmetrics.registerFont(TTFont("NotoSansBold", str(fonts / "NotoSans-Bold.ttf")))
body = ParagraphStyle(
    "body", fontName="NotoSans", fontSize=10, leading=15, spaceAfter=10
)
heading = ParagraphStyle(
    "heading",
    parent=body,
    fontName="NotoSansBold",
    fontSize=14,
    leading=19,
    textColor=colors.HexColor("#541478"),
    spaceBefore=14,
    keepWithNext=True,
)
title = ParagraphStyle("title", parent=heading, fontSize=22, leading=29, spaceAfter=18)
paragraphs = []
for block in (root / "docs/D-report.md").read_text().split("\n\n"):
    style = (
        title
        if block.startswith("# ")
        else heading
        if block.startswith("## ")
        else body
    )
    paragraphs.append(Paragraph(escape(block.lstrip("# ").replace("\n", " ")), style))
output = root / "docs/D-report.pdf"
SimpleDocTemplate(
    str(output),
    pagesize=A4,
    leftMargin=20 * mm,
    rightMargin=20 * mm,
    topMargin=20 * mm,
    bottomMargin=20 * mm,
    title="Сопроводительная документация D — ФСП Сигнал",
).build(paragraphs)
print(output)
