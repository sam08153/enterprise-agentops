from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AI_SERVICE_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    app_name: str = "ai-service"
    app_version: str = "0.1.0"
    host: str = "0.0.0.0"
    port: int = 8081
    debug: bool = False


settings = Settings()
