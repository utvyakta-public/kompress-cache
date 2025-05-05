import importlib
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from redis.exceptions import ConnectionError, TimeoutError

from kompress_cache import config
from kompress_cache.decorators import handle_exception, redis_exception_handler

ENV_OVERRIDES = {"REDIS_HOST": "127.0.0.1", "REDIS_PORT": "6378", "REDIS_TIMEOUT": "10",
                 "REDIS_REPLICAS_HOST_PORT": "localhost:6380,localhost:6381"}


class ConfigTestCase(TestCase):
    @patch.dict("os.environ", {}, clear=True)
    def test_config_with_default(self) -> None:
        conf = config.Config()
        self.assertEqual(conf.REDIS_HOST, "localhost")
        self.assertEqual(conf.REDIS_PORT, 6379)
        self.assertEqual(conf.REDIS_REPLICAS_HOST_PORT, "")
        self.assertEqual(conf.REDIS_TIMEOUT, 5)

    @patch.dict("os.environ", ENV_OVERRIDES)
    def test_config_with_env_variable(self) -> None:
        importlib.reload(config)
        from kompress_cache.config import Config

        conf = Config()
        self.assertEqual(conf.REDIS_HOST, "127.0.0.1")
        self.assertEqual(conf.REDIS_PORT, 6378)
        self.assertEqual(conf.REDIS_REPLICAS_HOST_PORT, "localhost:6380,localhost:6381")
        self.assertEqual(conf.REDIS_TIMEOUT, 10)


class HandleExceptionTestCase(TestCase):
    def test_on_connection_error(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            handle_exception(ConnectionError("Test connection error"))
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(ctx.exception.detail, "Service Unavailable")

    def test_on_timeout_error(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            handle_exception(TimeoutError("Test timeout error"))
        self.assertEqual(ctx.exception.status_code, 504)
        self.assertEqual(ctx.exception.detail, "Gateway Timeout")

    def test_on_other_exception(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            handle_exception(ValueError("Test value error"))
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertEqual(ctx.exception.detail, "Internal Server Error")


class RedisExceptionHandlerTestCase(IsolatedAsyncioTestCase):
    async def test_decorator_without_failover(self) -> None:
        mock_main = AsyncMock()
        decorated_func = redis_exception_handler()(mock_main)
        await decorated_func("test")
        mock_main.assert_awaited_with("test")

    async def test_decorator_without_failover_when_exception_occurs(self) -> None:
        mock_main = AsyncMock()
        mock_main.side_effect = ValueError("Test error")
        decorated_func = redis_exception_handler()(mock_main)
        with self.assertRaises(HTTPException) as ctx:
            await decorated_func("test")
        mock_main.assert_awaited_with("test")
        self.assertIsInstance(ctx.exception.__context__, ValueError)

    async def test_decorator_with_failover_when_there_is_no_exception_in_main_func(self) -> None:
        mock_main = AsyncMock()
        mock_fail_over = AsyncMock()
        decorated_func = redis_exception_handler(mock_fail_over)(mock_main)
        await decorated_func("test")

        mock_main.assert_awaited_with("test")
        mock_fail_over.assert_not_awaited()

    async def test_decorator_with_failover_when_there_is_an_exception_in_main_func(self) -> None:
        mock_main = AsyncMock()
        mock_main.side_effect = ValueError("test error")
        mock_fail_over = AsyncMock()
        decorated_func = redis_exception_handler(mock_fail_over)(mock_main)
        await decorated_func("test")

        mock_main.assert_awaited_with("test")
        mock_fail_over.assert_awaited_with("test")

    async def test_decorator_with_failover_when_there_exceptions_in_both_main_and_failover(self) -> None:
        mock_main = AsyncMock()
        mock_main.side_effect = ConnectionError("main test error")
        mock_fail_over = AsyncMock()
        mock_fail_over.side_effect = TimeoutError("fail over test error")
        decorated_func = redis_exception_handler(mock_fail_over)(mock_main)

        with self.assertRaises(HTTPException) as ctx:
            await decorated_func("test")

        mock_main.assert_awaited_with("test")
        mock_fail_over.assert_awaited_with("test")
        self.assertIsInstance(ctx.exception.__context__, TimeoutError)
