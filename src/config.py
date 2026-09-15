from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5"

    max_turns: int = 8
    temperature: float = 0.0
    ollama_think: bool = False
    # 模型驻留内存时长，防止空闲 5 分钟后被 Ollama 卸载，下次请求冷加载 10s+。
    # "30m" / "1h"；"-1" = 常驻不卸载（占用显存）
    ollama_keep_alive: str = "30m"

    db_path: str = "data/app.db"

    qweather_api_key: str = ""
    qweather_base_url: str = ""

    api_host: str = "0.0.0.0"
    api_port: int = 8001


settings = Settings()
