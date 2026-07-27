import os
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()


class Settings:
    DB_ENGINE: str = os.getenv("DB_ENGINE", "mysql")
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", 3306))
    DB_USER: str = os.getenv("DB_USER", "root")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    DB_NAME: str = os.getenv("DB_NAME", "medical_db")

    SECRET_KEY: str = os.getenv("SECRET_KEY", "mude-esta-chave-em-producao")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 480))

    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"

    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", 587))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "SISGERSA")
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "onboarding@resend.dev")
    EMAIL_HABILITADO: bool = os.getenv("EMAIL_HABILITADO", "false").lower() == "true"
    RESEND_API_KEY: str = os.getenv("RESEND_API_KEY", "")

    def __init__(self):
        database_url = os.getenv("DATABASE_URL", "")
        if database_url:
            if database_url.startswith("postgres"):
                self.DB_ENGINE = "postgresql"
                self.DB_PORT = 5432
            elif database_url.startswith("mysql"):
                self.DB_ENGINE = "mysql"
            self.DATABASE_URL = database_url
            parsed = urlparse(database_url)
            if parsed.hostname:
                self.DB_HOST = parsed.hostname
            if parsed.port:
                self.DB_PORT = parsed.port
            if parsed.username:
                self.DB_USER = parsed.username
            if parsed.password:
                self.DB_PASSWORD = parsed.password
            if parsed.path and len(parsed.path) > 1:
                self.DB_NAME = parsed.path.lstrip("/")
        else:
            self.DATABASE_URL = None

    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        if self.DB_ENGINE == "postgresql":
            return (
                f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}"
                f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            )
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


settings = Settings()
