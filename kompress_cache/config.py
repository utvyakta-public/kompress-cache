import logging
import os
from dataclasses import dataclass

logger = logging.getLogger("kompress_cache")


@dataclass
class Config:
    """Configuration class for Redis-related settings.

    This class loads configuration values from environment variables with default fallbacks.

    Attributes:
        REDIS_HOST (str): Host address for the primary Redis instance.
        REDIS_PORT (int): Port for the primary Redis instance.
        REDIS_REPLICAS_HOST_PORT (Optional[str]): Comma-separated list of replica Redis host:port pairs.
        REDIS_TIMEOUT (int): Timeout for Redis connections in seconds.
    """
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_REPLICAS_HOST_PORT: str | None = os.getenv("REDIS_REPLICAS_HOST_PORT", "")
    REDIS_TIMEOUT: int = int(os.getenv("REDIS_TIMEOUT", "5"))


CONFIG = Config()
