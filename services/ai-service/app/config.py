from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ai-service"
    app_version: str = "0.1.0"
    host: str = "0.0.0.0"
    port: int = 8081
    debug: bool = False

    # LLM
    groq_api_key: str = ""
    mock_mode: bool = False

    database_url: str = "postgresql://agentops:agentops@localhost:5432/agentops"



settings = Settings()
