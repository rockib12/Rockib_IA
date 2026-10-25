from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Core app configs
    APP_NAME: str = "Rockib AI"
    APP_ENV: str = "development"
    DEBUG: bool = False
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # Database postgres config
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_DB: str = "rockib_ai"

    DATABASE_URL: str = "postgresql://postgres:password@localhost:5432/rockib_ai"
    ASYNC_DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/rockib_ai"
    REDIS_URL: str = "redis://localhost:6379/0"

    # Security
    JWT_SECRET_KEY: str = "supersecretkeythatisatleast32characterslongforsecurity"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    CREDENTIAL_VAULT_KEY: Optional[str] = None
    PUBLIC_API_URL: str = "https://dion-beaverlike-preceptively.ngrok-free.dev"
    CONCIERGE_WIDGET_URL: str = "https://rockib-quenum.netlify.app/rockib-concierge.js"
    CORS_ORIGINS: list[str] = [
        "http://localhost",
        "http://localhost:80",
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1",
        "http://127.0.0.1:8080",
        "https://rockib-quenum.netlify.app",
    ]

    # WhatsApp (VPS Web)
    WHATSAPP_API_URL: Optional[str] = None
    WHATSAPP_SESSION_ID: str = "rockib_session"
    WHATSAPP_API_KEY: Optional[str] = None

    # Twilio (Escalade)
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_PHONE_NUMBER: Optional[str] = None
    OWNER_PHONE_NUMBER: Optional[str] = None

    # Telegram (Bot & Escalade Interactive)
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_ADMIN_CHAT_ID: Optional[str] = None
    TELEGRAM_WEBHOOK_SECRET: Optional[str] = None

    # LLM keys
    OPENAI_API_KEY: Optional[str] = None
    DEEPSEEK_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    DEFAULT_MODEL_NAME: str = "openai/gpt-oss-120b"
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    ANALYTICAL_MODEL_NAME: str = "deepseek-coder"
    CONCIERGE_LEAD_RETENTION_DAYS: int = 90
    TRUSTED_PROXY_CIDRS: list[str] = ["127.0.0.0/8", "::1/128"]

    # ElevenLabs Scribe v2 Realtime Voice (Controlled via TRUE/FALSE flag)
    ENABLE_ELEVENLABS_REALTIME: bool = False
    ELEVENLABS_API_KEY: Optional[str] = None
    ELEVENLABS_VOICE_ID: str = "21m00Tcm4TlvDq8ikWAM"
    ELEVENLABS_MODEL_ID: str = "scribe_v2_realtime"
    ELEVENLABS_TTS_MODEL_ID: str = "eleven_turbo_v2_5"

    # Execution / Sandboxing
    WORKSPACES_ROOT: str = "/tmp/rockib_workspaces"

    # Chargement depuis le fichier .env si présent
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
