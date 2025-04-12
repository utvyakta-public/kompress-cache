import asyncio
import logging
import random
from typing import Callable, Protocol

from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis

from .config import CONFIG
from .decorators import redis_exception_handler

logger = logging.getLogger("kompress_cache")


def get_redis(host: str, port: str | int) -> Redis:
    return Redis(
        host=host,
        port=port,
        decode_responses=True,
        socket_timeout=CONFIG.REDIS_TIMEOUT,
        health_check_interval=30,
        retry_on_timeout=True,
        socket_keepalive=True
    )


def validate_json(json_data: str, model: BaseModel) -> bool:
    try:
        model.model_validate_json(json_data)
        return True
    except ValidationError:
        return False


class Loadable(Protocol):
    def load(self) ->  str:
        ...


class Cache:
    def __init__(self) -> None:
        self.primary = get_redis(CONFIG.REDIS_HOST, CONFIG.REDIS_PORT)
        self.replicas = [get_redis(*replica_host_port.split(":"))
                         for replica_host_port in CONFIG.REDIS_REPLICAS_HOST_PORT.split(",") if replica_host_port]

        if self.replicas:
            logger.info("Initialized cache with a primary redis and %d replicas", len(self.replicas))
        else:
            logger.warning("Redis replicas not given. Using primary redis for both read and write operations")

    async def aclose(self) -> None:
        tasks = [cache.aclose() for cache in [self.primary, *self.replicas]]
        await asyncio.gather(*tasks)
        logger.info("Redis cache close completed")

    def _get_primary_attr(self, name: str) -> object:
        try:
            primary_attr = getattr(self.primary, name)
        except AttributeError:
            raise AttributeError("'Cache' object has no attribute '{}'".format(name)) from None

        if callable(primary_attr):
            primary_attr = redis_exception_handler()(primary_attr)
        return primary_attr

    def _get_attr_from_a_replica(self, name: str, primary_attr: Callable | None = None) -> object:
        logger.debug("Accessing attribute '%s' from replica with an failover to primary redis", name)
        if not primary_attr:
            primary_attr = self._get_primary_attr(name)

        if not self.replicas:
            logger.debug("No replicas were given. Using primary attribute")
            return primary_attr

        replica = random.choice(self.replicas)
        replica_attr = getattr(replica, name)

        return redis_exception_handler(fail_over_to=primary_attr)(replica_attr)

    def __getattr__(self, name: str) -> object:
        logger.debug("Accessing attribute '%s' from primary", name)
        return self._get_primary_attr(name)

    async def hset(self, cache_name: str, cache_key: str, value: str) -> None:
        hset = self._get_primary_attr("hset")
        logger.debug("Setting cache %s key %s with value %s", cache_name, cache_key, value)
        await hset(cache_name, cache_key, value)

    async def hget(self, cache_name: str, cache_key: str) -> str | None:
        hget = self._get_attr_from_a_replica("hget")
        logger.debug("Getting hash value for cache name: %s and key: %s", cache_name, cache_key)
        value: str | None = await hget(cache_name, cache_key)
        logger.debug("Cache hit key: %s, value: %s", cache_key, value)
        return value

    async def hget_l(self, cache_name: str, cache_key: str, loader: Loadable, model: BaseModel | None = None) -> str | BaseModel:
        value = await self.hget(cache_name, cache_key)
        if not value or (model and not validate_json(value, model)):
            logger.warning("Cache: %s, cache miss or invalid for: %s, loader: %s", cache_name, cache_key, loader)
            value = await loader.load()

            logger.debug("Value from loader %s", value)
            await self.hset(cache_name, cache_key, value)

        return model.model_validate_json(value) if model else value
