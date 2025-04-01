import logging
import os
from dataclasses import dataclass

logger = logging.getLogger("kompress_cache")


@dataclass
class Config:
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: str = os.getenv("REDIS_PORT", "6379")
    REDIS_REPLICAS_HOST_PORT: str | None = os.getenv("REDIS_REPLICAS_HOST_PORT", "")
    REDIS_TIMEOUT: int = int(os.getenv("REDIS_TIMEOUT", "5"))


CONFIG = Config()
