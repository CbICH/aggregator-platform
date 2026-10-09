# Шрифты PDF

Noto Sans Regular и Bold взяты из проекта [Noto Fonts](https://github.com/notofonts/noto-fonts/tree/main/hinted/ttf/NotoSans). Лицензия SIL Open Font License 1.1 включена в `OFL.txt`. Файлы не изменены.

Шрифты поставляются вместе с приложением и попадают в Docker-образ через COPY `apps/api/`; системные шрифты не используются. ReportLab регистрирует TrueType-шрифты для Unicode: [официальная документация](https://docs.reportlab.com/reportlab/userguide/ch2_graphics/).
