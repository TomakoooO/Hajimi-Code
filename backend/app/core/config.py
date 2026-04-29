from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENT_",
        env_file=str(Path(__file__).resolve().parents[1] / ".env"),
        extra="ignore"
    )

    app_name: str = "Coding Agent Backend"
    app_version: str = "0.2.0"
    api_prefix: str = "/api"
    ws_timeline_path: str = "/ws/timeline"
    cors_allow_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    llm_timeout_seconds: float = 8.0
    llm_retry_times: int = 2
    max_read_file_size: int = 256_000
    # default workspace root: project root (parent of backend/)
    workspace_root: str = str(Path(__file__).resolve().parents[3])


settings = Settings()
