import smtplib
import ssl
from email.message import EmailMessage
from typing import Protocol

from app.core.config import Settings


class Mailer(Protocol):
    def send_verification(self, email: str, token: str) -> None: ...


class SmtpMailer:
    def __init__(self, settings: Settings):
        self.settings = settings

    def send_verification(self, email: str, token: str) -> None:
        cfg = self.settings
        # Fragment avoids sending the token to web-server access logs or referrer headers.
        link = f"{cfg.public_app_url}/verify-email#token={token}"
        message = EmailMessage()
        message["Subject"] = "Подтвердите email — ФСП Сигнал"
        message["From"] = cfg.smtp_from
        message["To"] = email
        message.set_content(
            f"Подтвердите адрес для аккаунта ФСП Сигнал:\n\n{link}\n\n"
            f"Ссылка действует {cfg.verification_minutes} минут и используется один раз.\n"
            "Если вы не регистрировались, проигнорируйте письмо."
        )
        connection = (
            smtplib.SMTP_SSL(
                cfg.smtp_host, cfg.smtp_port, timeout=10, context=ssl.create_default_context()
            )
            if cfg.smtp_ssl
            else smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=10)
        )
        with connection as smtp:
            if cfg.smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
            if cfg.smtp_user:
                smtp.login(cfg.smtp_user, cfg.smtp_password)
            smtp.send_message(message)
