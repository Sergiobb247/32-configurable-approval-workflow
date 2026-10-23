"""Application configuration — the ONLY place environment variables are read.

Owner: Person A — Identity & Access (Gogo Frank).
Contract: docs/technical-spec.md §9.

    No `os.getenv` anywhere else in the codebase.

All six configuration variables live on `settings`. Both SCREAMING_SNAKE_CASE
(matching the table in technical-spec.md §9) and snake_case properties are
exposed so callers across layers (`main.py`, `database.py`, `auth/security.py`)
never trip over attribute casing during integration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

_DEV_FALLBACK_SECRET = "dev-only-insecure-jwt-secret-do-not-use-in-prod-32b"
_BACKEND_DIR = Path(__file__).resolve().parents[1]


def _load_dotenv_file(dotenv_path: Path) -> dict[str, str]:
    """Read key=value pairs from `backend/.env` without requiring third-party
    packages at import time. Real OS environment variables always win."""
    loaded: dict[str, str] = {}
    if not dotenv_path.is_file():
        return loaded
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key:
            loaded[key] = value
    return loaded


def normalize_database_url(raw_url: str) -> str:
    """Normalize Heroku/Render `postgres://` URLs to `postgresql://` for
    SQLAlchemy 2.x (technical-spec.md §9)."""
    cleaned = raw_url.strip()
    if cleaned.startswith("postgres://"):
        return "postgresql://" + cleaned[len("postgres://") :]
    return cleaned


def parse_cors_origins(raw_origins: str) -> list[str]:
    """Parse comma-separated CORS origins and forbid wildcard `*` (§9)."""
    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    if not origins:
        raise ValueError("CORS_ORIGINS must specify at least one allowed origin")
    if "*" in origins:
        raise ValueError("CORS_ORIGINS must never contain '*'")
    return origins


@dataclass(frozen=True)
class Settings:
    """Validated runtime settings loaded once at startup."""

    ENV: str
    DATABASE_URL: str
    JWT_SECRET: str
    ACCESS_TOKEN_MINUTES: int
    REFRESH_TOKEN_DAYS: int
    CORS_ORIGINS: list[str]

    # Snake-case aliases for seamless integration with `main.py` / services
    @property
    def env(self) -> str:
        return self.ENV

    @property
    def database_url(self) -> str:
        return self.DATABASE_URL

    @property
    def jwt_secret(self) -> str:
        return self.JWT_SECRET

    @property
    def access_token_minutes(self) -> int:
        return self.ACCESS_TOKEN_MINUTES

    @property
    def refresh_token_days(self) -> int:
        return self.REFRESH_TOKEN_DAYS

    @property
    def cors_origins(self) -> list[str]:
        return self.CORS_ORIGINS

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        dotenv_path: Path | None = _BACKEND_DIR / ".env",
    ) -> "Settings":
        merged: dict[str, str] = {}
        if environ is None and dotenv_path is not None:
            merged.update(_load_dotenv_file(dotenv_path))
        source = environ if environ is not None else os.environ
        merged.update(source)

        env = merged.get("ENV", "development").strip() or "development"
        raw_db_url = merged.get("DATABASE_URL", "sqlite:///./app.db")
        database_url = normalize_database_url(raw_db_url)

        raw_secret = merged.get("JWT_SECRET", "").strip()
        if not raw_secret:
            if env.lower() in {"development", "dev", "test", "testing"}:
                raw_secret = _DEV_FALLBACK_SECRET
            else:
                raise RuntimeError(
                    "JWT_SECRET environment variable is required outside development"
                )

        access_minutes = int(merged.get("ACCESS_TOKEN_MINUTES", "15"))
        refresh_days = int(merged.get("REFRESH_TOKEN_DAYS", "7"))
        if access_minutes <= 0:
            raise ValueError("ACCESS_TOKEN_MINUTES must be greater than 0")
        if refresh_days <= 0:
            raise ValueError("REFRESH_TOKEN_DAYS must be greater than 0")

        cors_origins = parse_cors_origins(
            merged.get("CORS_ORIGINS", "http://localhost:5173")
        )

        return cls(
            ENV=env,
            DATABASE_URL=database_url,
            JWT_SECRET=raw_secret,
            ACCESS_TOKEN_MINUTES=access_minutes,
            REFRESH_TOKEN_DAYS=refresh_days,
            CORS_ORIGINS=cors_origins,
        )


settings = Settings.from_env()
