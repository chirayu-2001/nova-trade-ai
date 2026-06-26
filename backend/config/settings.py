import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    database_path: str = "./data/db/nova.db"
    customer_rules_dir: str = "./data/sample_docs/customer_rules"
    sample_docs_dir: str = "./data/sample_docs"
    inbox_dir: str = "./data/inbox"
    log_level: str = "INFO"

    # Model configuration
    extraction_model: str = "claude-haiku-4-5-20251001"
    validation_model: str = "claude-haiku-4-5-20251001"
    routing_model: str = "claude-haiku-4-5-20251001"
    query_model: str = "claude-haiku-4-5-20251001"

    # Thresholds
    confidence_threshold: float = 0.85
    fuzzy_match_threshold: float = 0.85
    max_retries: int = 2
    timeout_per_agent: int = 60

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
