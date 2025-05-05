from redis.asyncio import Redis

from .cache import Cache, Loadable


def get_cache() -> Cache | Redis:
    """Factory method to get an instance of the cache.

    Returns:
        Cache | Redis: A new `Cache` instance configured with primary and replicas.
    """
    return Cache()


__all__ = ["Loadable", "get_cache"]
