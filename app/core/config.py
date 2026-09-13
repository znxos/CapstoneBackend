from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    
    RESEND_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None
    
    NEXT_PUBLIC_PUSHER_APP_ID: str | None = None
    NEXT_PUBLIC_PUSHER_KEY: str | None = None
    PUSHER_SECRET: str | None = None
    NEXT_PUBLIC_PUSHER_CLUSTER: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
