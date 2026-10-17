import os
from typing import List, Union
from pydantic import AnyHttpUrl, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    FRONTEND_URL: str = "http://localhost:3000"

    # CORS
    CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://localhost",
        "http://127.0.0.1",
    ]

    # Database
    DATABASE_URL: str = "mysql+pymysql://root:@localhost:3306/examind"
    # Optional explicit CA bundle path for TLS MySQL (e.g. TiDB Cloud).
    # Auto-enabled for *.tidbcloud.com hosts using certifi's bundle.
    DB_SSL_CA: str = ""

    # Security / JWT — never ship the dev default to production
    SECRET_KEY: str = "examind_dev_only_change_in_production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # Cloudflare Edge Lock (origin lock, 2-phase rollout)
    EDGE_SECRET: str = ""
    EDGE_ENFORCE: bool = False

    # AI Provider
    AI_PROVIDER: str = "gemini"
    AI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # OpenRouter & Decision Models (Respan Span-01 Lite)
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_DECISION_MODEL: str = "respan/span-01-lite"

    # Resend Email Integration
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = "EXAMIND <noreply@examind.rijal.work>"

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @model_validator(mode="after")
    def _require_production_secrets(self):
        if self.ENVIRONMENT.lower() == "production":
            if not self.SECRET_KEY or self.SECRET_KEY == "examind_dev_only_change_in_production":
                raise ValueError(
                    "SECRET_KEY must be set via environment variable when ENVIRONMENT=production. "
                    "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
                )
        return self

    @property
    def cors_origins_list(self) -> List[str]:
        if isinstance(self.CORS_ORIGINS, list):
            return self.CORS_ORIGINS
        if isinstance(self.CORS_ORIGINS, str):
            import json
            try:
                parsed = json.loads(self.CORS_ORIGINS)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass
            return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]
        return ["*"]


settings = Settings()
