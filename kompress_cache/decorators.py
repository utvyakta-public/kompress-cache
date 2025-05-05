import logging
from functools import wraps
from typing import Awaitable, Callable, NoReturn, ParamSpec, TypeVar

from fastapi.exceptions import HTTPException
from redis.exceptions import ConnectionError, TimeoutError

logger = logging.getLogger("kompress_cache")


P = ParamSpec("P")    # Parameters of the decorated function
R = TypeVar("R")      # Return type of the decorated function


def handle_exception(exc: Exception) -> NoReturn:
    """Centralized handler for exceptions raised during Redis operations.

    If the exception is already an HTTPException, it is re-raised.
    Otherwise, logs the error and raises a mapped HTTPException based on the type.

    Args:
        exc (Exception): The caught exception.

    Raises:
        HTTPException: A FastAPI HTTP exception with a relevant status code.
    """
    if isinstance(exc, HTTPException):
        raise exc

    logger.error("Redis Error: %s", exc)
    if logger.isEnabledFor(logging.DEBUG):
        logger.exception(exc)

    if isinstance(exc, ConnectionError):
        logger.error("Unable to connect to the redis server.")
        raise HTTPException(503, "Service Unavailable")
    if isinstance(exc, TimeoutError):
        logger.error("Redis server time out.")
        raise HTTPException(504, "Gateway Timeout")

    raise HTTPException(500, "Internal Server Error")


def redis_exception_handler(fail_over_to: Callable[P, Awaitable[R]] | None = None) -> Callable[[Callable], Callable]:
    """ Decorator that wraps async Redis calls with exception handling logic.

    If the call fails, logs the error and optionally attempts a fallback function
    (typically a call to the primary Redis instance). If the fallback also fails,
    the exception is handled via `handle_exception`.

    Args:
        fail_over_to (Callable[P, Awaitable[R]] | None, optional): Optional fallback callable to invoke on failure. Defaults to None.

    Returns:
        Callable[[Callable], Callable]: The decorated function with failover and error-handling logic.
    """
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
