"""应用配置：从环境变量 / .env 加载，密钥绝不写死。"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    app_host: str = "127.0.0.1"
    app_port: int = 8000
    database_url: str = f"sqlite:///{ROOT / 'data' / 'tracker.db'}"

    collect_interval_minutes: int = 60

    filter_min_price: float = 50.0
    filter_max_price: float = 100_000.0
    filter_median_deviation_ratio: float = 0.55
    filter_zscore_threshold: float = 3.5

    force_offline: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
