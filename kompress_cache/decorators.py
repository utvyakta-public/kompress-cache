import logging
from functools import wraps
from typing import Awaitable, Callable, NoReturn, ParamSpec, TypeVar

from fastapi.exceptions import HTTPException
from redis.exceptions import ConnectionError, TimeoutError

logger = logging.getLogger("kompress_cache")


P = ParamSpec("P")    # Parameter Types
R = TypeVar("R")      # Return Type


def handle_exception(exc: Exception) -> NoReturn:
    logger.error("Redis Error: %s", exc)
    if logger.isEnabledFor(logging.DEBUG):
        logger.exception(exc)

    if isinstance(exc, ConnectionError):
        logger.error("Unable to connect with redis server")
        raise HTTPException(503, "Service Unavailable")
    if isinstance(exc, TimeoutError):
        logger.error("Redis server timeout")
        raise HTTPException(504, "Gateway Timeout")

    raise HTTPException(500, "Internal Server Error")


def redis_exception_handler(fail_over_to: Callable[P, Awaitable[R]] | None = None) -> Callable[[Callable], Callable]:
    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                return await func(*args, **kwargs)
            except Exception as exc:
                if fail_over_to:
                    logger.error("Replica failed when accessing %s: %s. Using primary", func.__name__, exc)
                    try:
                        return await fail_over_to(*args, **kwargs)
                    except Exception as fail_over_exc:
                        handle_exception(fail_over_exc)
                handle_exception(exc)
        return wrapper
    return decorator
