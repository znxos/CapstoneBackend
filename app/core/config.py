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
    PUSHER_ENCRYPTION_KEY: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    
    @property
    def get_database_url(self) -> str:
        url = self.DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        # fix asyncpg ssl parameter
        url = url.replace("sslmode=require", "ssl=require")
        # asyncpg doesn't use pgbouncer=true in the url
        url = url.replace("&pgbouncer=true", "")
        url = url.replace("?pgbouncer=true&", "?")
        url = url.replace("?pgbouncer=true", "")
        return url

settings = Settings()
