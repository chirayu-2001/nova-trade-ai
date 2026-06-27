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
    extraction_model: str = "anthropic/claude-3-5-sonnet-20241022"
    validation_model: str = "anthropic/claude-3-5-sonnet-20241022"
    routing_model: str = "anthropic/claude-3-5-sonnet-20241022"
    query_model: str = "anthropic/claude-3-5-sonnet-20241022"

    extraction_temperature: float = 0.0
    validation_temperature: float = 0.0
    routing_temperature: float = 0.2
    query_temperature: float = 0.0

    # Thresholds
    confidence_threshold: float = 0.85
    fuzzy_match_threshold: float = 0.85
    max_retries: int = 2
    timeout_per_agent: int = 60

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
