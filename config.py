import os
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Strict configuration validation using Pydantic Settings."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    REDIS_HOST: str = Field(default="localhost", description="Redis host address")
    REDIS_PORT: int = Field(default=6379, ge=1, le=65535, description="Redis port")
    ENVIRONMENT: str = Field(default="production", description="App environment mode")
    LOG_LEVEL: str = Field(default="INFO", description="Logging verbosity level")
    MAX_WORKER_STEPS: int = Field(default=4, ge=1, le=10, description="Maximum allowed worker execution steps")
    REDIS_CONNECT_TIMEOUT: float = Field(default=0.5, ge=0.1, le=10.0, description="Redis socket connection timeout in seconds")

settings = Settings()
