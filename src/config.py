from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5"

    max_turns: int = 8
    temperature: float = 0.0

    db_path: str = "data/app.db"

    qweather_api_key: str = ""

    api_host: str = "0.0.0.0"
    api_port: int = 8001


settings = Settings()
