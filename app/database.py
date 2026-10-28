from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND_DIR / ".env"
DEFAULT_DB_FILE = BACKEND_DIR / "medshield.db"


class Settings(BaseSettings):
    database_url: str = f"sqlite:///./medshield.db"
    jwt_secret_key: str | None = None
    cors_origins: str | None = None

    model_config = SettingsConfigDict(
        env_file=[str(ENV_FILE), ".env"],
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def resolved_database_url(self) -> str:
        url = self.database_url
        if url.startswith("sqlite:///./"):
            rel = url.replace("sqlite:///./", "")
            return f"sqlite:///{(BACKEND_DIR / rel).as_posix()}"
        elif (
            url.startswith("sqlite:///")
            and not url.startswith("sqlite:////")
            and ":memory:" not in url
            and not (len(url) > 11 and url[10] == ":")
        ):
            rel = url.replace("sqlite:///", "")
            return f"sqlite:///{(BACKEND_DIR / rel).as_posix()}"
        return url


settings = Settings()

_resolved_url = settings.resolved_database_url
_connect_args = {"check_same_thread": False} if _resolved_url.startswith("sqlite") else {}

engine = create_engine(
    _resolved_url,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
