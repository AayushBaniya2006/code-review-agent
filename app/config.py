"""Application configuration."""
from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import Optional, List
import logging
import sys

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application configuration from environment variables."""

    # AkashML API
    akashml_api_key: str = ""
    akashml_base_url: str = "https://api.akashml.com/v1"
    default_model: str = "meta-llama/Llama-3.3-70B-Instruct"

    # Application
    environment: str = "development"
    log_level: str = "INFO"
    max_diff_size: int = 500000  # 500KB max diff size
    rate_limit_per_minute: int = 60
    trust_proxy_headers: bool = False
    chunk_size_chars: int = 120000
    cache_ttl_seconds: int = 300
    cache_max_entries: int = 256

    # Security: CORS configuration
    # Use comma-separated origins or "*" for development only
    cors_allowed_origins: str = "http://localhost:8000,http://127.0.0.1:8000"

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins into a list."""
        if self.cors_allowed_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @field_validator('cors_allowed_origins')
    @classmethod
    def validate_cors_origins(cls, v: str, info) -> str:
        """Warn about wildcard CORS - actual blocking happens at runtime based on environment."""
        if v == "*":
            logger.warning(
                "CORS_ALLOWED_ORIGINS is set to '*' (wildcard). "
                "This should only be used in development. "
                "For production, specify explicit origins."
            )
        return v

    @field_validator('akashml_api_key')
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """Validate that the API key is present and has valid format."""
        if not v or not v.strip():
            logger.error("AKASHML_API_KEY environment variable is not set")
            # Don't raise during module load - let routes.py check at request time
            return v
        v = v.strip()
        if not v.startswith('akml-'):
            logger.warning(
                f"AKASHML_API_KEY has unexpected format (expected 'akml-' prefix). "
                "Key may not work with AkashML API."
            )
        return v

    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is valid."""
        valid_levels = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
        if v.upper() not in valid_levels:
            logger.warning(f"Invalid LOG_LEVEL '{v}', defaulting to INFO")
            return 'INFO'
        return v.upper()

    @field_validator('rate_limit_per_minute')
    @classmethod
    def validate_rate_limit(cls, v: int) -> int:
        if v < 0:
            logger.warning("RATE_LIMIT_PER_MINUTE cannot be negative, defaulting to 0")
            return 0
        return v

    @field_validator('cache_ttl_seconds')
    @classmethod
    def validate_cache_ttl(cls, v: int) -> int:
        if v < 0:
            logger.warning("CACHE_TTL_SECONDS cannot be negative, defaulting to 0")
            return 0
        return v

    @field_validator('cache_max_entries')
    @classmethod
    def validate_cache_size(cls, v: int) -> int:
        if v < 0:
            logger.warning("CACHE_MAX_ENTRIES cannot be negative, defaulting to 0")
            return 0
        return v

    @field_validator('chunk_size_chars')
    @classmethod
    def validate_chunk_size(cls, v: int) -> int:
        if v < 0:
            logger.warning("CHUNK_SIZE_CHARS cannot be negative, defaulting to 0")
            return 0
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


def get_settings() -> Settings:
    """Get application settings with validation logging."""
    try:
        return Settings()
    except Exception as e:
        logger.critical(f"Failed to load settings: {e}")
        raise


settings = get_settings()
