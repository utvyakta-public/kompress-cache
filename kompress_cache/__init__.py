from redis.asyncio import Redis

from .cache import Cache


def get_cache() -> Cache | Redis:
    return Cache()
