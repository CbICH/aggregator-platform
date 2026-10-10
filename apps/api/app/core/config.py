from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./signal.db"
    public_app_url: str = "http://localhost:5173"
    cookie_secure: bool = False
    smtp_host: str = "localhost"
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_from: str = "noreply@signal.local"
    smtp_starttls: bool = False
    smtp_ssl: bool = False
    smtp_user: str = ""
    smtp_password: str = ""
    session_hours: int = Field(default=8, ge=1, le=168)
    verification_minutes: int = Field(default=30, ge=1, le=1440)
    password_reset_minutes: int = Field(default=30, ge=1, le=1440)

    @model_validator(mode="after")
    def validate_deployment(self):
        url = urlsplit(self.public_app_url)
        if url.scheme not in {"http", "https"} or not url.netloc or url.path not in {"", "/"}:
            raise ValueError("PUBLIC_APP_URL must be an HTTP(S) origin without a path")
        if url.username or url.password or url.query or url.fragment:
            raise ValueError("PUBLIC_APP_URL must not include credentials, query or fragment")
        self.public_app_url = self.public_app_url.rstrip("/")
        if self.smtp_starttls and self.smtp_ssl:
            raise ValueError("Choose SMTP_STARTTLS or SMTP_SSL, not both")
        if self.app_env == "production":
            if url.scheme != "https" or not self.cookie_secure:
                raise ValueError("Production requires HTTPS and COOKIE_SECURE=true")
            if not self.database_url.startswith("postgresql+psycopg://"):
                raise ValueError("Production requires PostgreSQL")
            if not (self.smtp_starttls or self.smtp_ssl):
                raise ValueError("Production SMTP requires TLS")
        return self
