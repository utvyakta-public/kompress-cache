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
    """Creates and returns a configured Redis client connected to the specified host and port.

    This function establishes a Redis client with the provided host and port
    and uses further configuration for better stability and reliability,
    like response decoding, handling timeouts, and health checks.

    Args:
        host (str): The hostname or IP address of the Redis server (e.g., 'localhost' or '127.0.0.1').
        port (str | int): The port number on which the Redis server is listening (e.g., 6379).

    Returns:
        Redis: A Redis client instance connected to the specified host and port.

    Configuration:
        - decode_responses=True: Automatically decodes responses from bytes to strings.
        - socket_timeout=CONFIG.REDIS_TIMEOUT: Connection timeout in seconds, from app configuration.
        - health_check_interval=30: Interval in seconds to perform periodic health checks.
        - retry_on_timeout=True: Retries commands if a timeout occurs.
        - socket_keepalive=True: Enables TCP keepalive to maintain long-lived connections.
    """
    return Redis(
        host=host,
        port=port,
        decode_responses=True,
        socket_timeout=CONFIG.REDIS_TIMEOUT,
        health_check_interval=30,
        retry_on_timeout=True,
        socket_keepalive=True
    )


def validate_json(json_data: str, model: type[BaseModel]) -> bool:
    """
    Validates a JSON string against the given Pydantic model.

    Args:
        json_data (str): The JSON string to validate.
        model (type[BaseModel]): A Pydantic model class to validate against.

    Returns:
        bool: True if the JSON is valid according to the model, False otherwise.

    Example:
        >>> class User(BaseModel):
        >>>     name: str
        >>>     age: int
        >>> validate_json('{"name": "Alice", "age": 30}', User)
        True
        >>> validate_json('{"name": "Alice"}', User)
        False
    """
    try:
        model.model_validate_json(json_data)
        return True
    except ValidationError:
        return False


class Loadable(Protocol):
    """
    Protocol for lazy-loading data.

    Implementing classes must define a `load()` method that returns a string
    (e.g., JSON, serialized data, or a resource string).

    Example:
        class UserProfileLoader:
            def load(self) -> str:
                # Fetch from database or external API
                return '{"name": "Alice", "age": 30}'
    """
    def load(self) ->  str:
        ...


class Cache:
    """
    Redis-based cache layer supporting primary and replica Redis instances.

    This class abstracts interaction with Redis by:
    - Using a primary Redis instance for write operations
    - Distributing read operations across replicas
    - Falling back to the primary if replicas are unavailable or fail
    - Handling lazy loading on cache misses via a `Loadable` interface

    Attributes:
        primary (Redis): Redis client used for all write operations and replica fallback.
        replicas (list[Redis]): List of Redis clients used for read operations (optional).
    """

    def __init__(self) -> None:
        """
        Initializes the cache by connecting to the primary Redis and optional replicas.

        Reads replica host/port pairs from a comma-separated config string.
        Logs a warning if no replicas are provided, indicating read/write use of primary.
        """
        self.primary = get_redis(CONFIG.REDIS_HOST, CONFIG.REDIS_PORT)
        self.replicas = [get_redis(*replica_host_port.split(":"))
                         for replica_host_port in CONFIG.REDIS_REPLICAS_HOST_PORT.split(",") if replica_host_port]

        if self.replicas:
            logger.info("Initialized cache with a primary redis and %d replicas", len(self.replicas))
        else:
            logger.warning("Redis replicas not given. Using primary redis for both read and write operations")

    async def aclose(self) -> None:
        """
        Closes all Redis connections (primary and replicas) asynchronously.
        """
        tasks = [cache.aclose() for cache in [self.primary, *self.replicas]]
        await asyncio.gather(*tasks)
        logger.info("Redis cache close completed")

    def _get_primary_attr(self, name: str) -> object:
        """Retrieves an attribute from the primary Redis client.

        If the attribute is callable, wraps it with a Redis exception handler.

        Args:
            name (str): The attribute name to retrieve.

        Raises:
            AttributeError: If the given attribute doesn't exist on the primary.

        Returns:
            object: The resolved attribute from the primary Redis.
        """
        try:
            primary_attr = getattr(self.primary, name)
        except AttributeError:
            raise AttributeError("'Cache' object has no attribute '{}'".format(name)) from None

        if callable(primary_attr):
            primary_attr = redis_exception_handler()(primary_attr)
        return primary_attr

    def _get_attr_from_a_replica(self, name: str, primary_attr: Callable | None = None) -> object:
        """Retrieves an attribute from a random replica with failover to primary.

        Args:
            name (str): The attribute name to retrieve.
            primary_attr (Callable | None, optional): The fallback attribute from primary Redis. Defaults to None.

        Returns:
            object: A callable with built-in failover handling.
        """
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
        """Fallback method for direct attribute access on the primary Redis.

        Args:
            name (str): The attribute name.

        Returns:
            object: Attribute from the primary Redis (with exception handling if callable).
        """
        logger.debug("Accessing attribute '%s' from primary", name)
        return self._get_primary_attr(name)

    async def hset(self, cache_name: str, cache_key: str, value: str) -> None:
        """Stores a value in Redis using the `HSET` command.

        Args:
            cache_name (str): The Redis hash name.
            cache_key (str): The field key inside the hash.
            value (str): The value to store (typically serialized).
        """
        hset = self._get_primary_attr("hset")
        logger.debug("Setting cache %s key %s with value %s", cache_name, cache_key, value)
        await hset(cache_name, cache_key, value)

    async def hget(self, cache_name: str, cache_key: str) -> str | None:
        """Retrieves a value from Redis using the `HGET` command.

        Attempts to read from a replica first, with fallback to primary.

        Args:
            cache_name (str): The Redis hash name.
            cache_key (str): The field key inside the hash.

        Returns:
            str | None: The cached value or None if key is not found.
        """
        hget = self._get_attr_from_a_replica("hget")
        logger.debug("Getting hash value for cache name: %s and key: %s", cache_name, cache_key)
        value: str | None = await hget(cache_name, cache_key)
        logger.debug("Cache hit key: %s, value: %s", cache_key, value)
        return value

    async def hget_l(self, cache_name: str, cache_key: str, loader: Loadable, model: BaseModel | None = None) -> str | BaseModel:
        """Retrieves a value from Redis or lazily loads it on cache miss.

        Validates the value against a Pydantic model if provided. If the cache
        is empty or the data is invalid, the loader is used to generate the data,
        which is then cached and returned.

        Args:
            cache_name (str): Redis hash name.
            cache_key (str): Field key inside the hash.
            loader (Loadable): An instance with method 'load', used to fetch the value if missing.
            model (BaseModel | None, optional): Optional Pydantic model for JSON validation and parsing. Defaults to None.

        Returns:
            str | BaseModel: The cached or loaded data, optionally parsed into a model.
        """
        value = await self.hget(cache_name, cache_key)
        if not value or (model and not validate_json(value, model)):
            logger.warning("Cache: %s, cache miss or invalid for: %s, loader: %s", cache_name, cache_key, loader)
            value = await loader.load()

            logger.debug("Value from loader %s", value)
            await self.hset(cache_name, cache_key, value)

        return model.model_validate_json(value) if model else value
