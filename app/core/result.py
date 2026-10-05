"""
Rust-inspired Result/Either pattern for strict typing, safe functional error handling,
and avoiding unhandled exceptions across the trading core and broker adapters.
"""

from typing import TypeVar, Generic, Union, Callable, Any, Optional

T = TypeVar("T")
E = TypeVar("E")
U = TypeVar("U")
F = TypeVar("F")


class Ok(Generic[T]):
    __slots__ = ("_value",)

    def __init__(self, value: T):
        self._value = value

    @property
    def value(self) -> T:
        return self._value

    def is_ok(self) -> bool:
        return True

    def is_err(self) -> bool:
        return False

    def unwrap(self) -> T:
        return self._value

    def unwrap_or(self, default: Any) -> T:
        return self._value

    def unwrap_err(self) -> Any:
        raise ValueError("Called unwrap_err on an Ok value")

    def map(self, fn: Callable[[T], U]) -> "Result[U, Any]":
        try:
            return Ok(fn(self._value))
        except Exception as ex:
            return Err(ex)

    def map_err(self, fn: Callable[[Any], Any]) -> "Result[T, Any]":
        return self

    def and_then(self, fn: Callable[[T], "Result[U, Any]"]) -> "Result[U, Any]":
        return fn(self._value)

    def __repr__(self) -> str:
        return f"Ok({self._value!r})"

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Ok) and self._value == other._value


class Err(Generic[E]):
    __slots__ = ("_error",)

    def __init__(self, error: E):
        self._error = error

    @property
    def error(self) -> E:
        return self._error

    def is_ok(self) -> bool:
        return False

    def is_err(self) -> bool:
        return True

    def unwrap(self) -> Any:
        if isinstance(self._error, Exception):
            raise self._error
        raise ValueError(f"Called unwrap on an Err value: {self._error!r}")

    def unwrap_or(self, default: U) -> U:
        return default

    def unwrap_err(self) -> E:
        return self._error

    def map(self, fn: Callable[[Any], Any]) -> "Result[Any, E]":
        return self

    def map_err(self, fn: Callable[[E], F]) -> "Result[Any, F]":
        try:
            return Err(fn(self._error))
        except Exception as ex:
            return Err(ex)  # type: ignore

    def and_then(self, fn: Callable[[Any], Any]) -> "Result[Any, E]":
        return self

    def __repr__(self) -> str:
        return f"Err({self._error!r})"

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Err) and self._error == other._error


Result = Union[Ok[T], Err[E]]


def safe_exec(fn: Callable[..., T], *args: Any, **kwargs: Any) -> Result[T, Exception]:
    """Wraps a synchronous callable in a Result monad."""
    try:
        return Ok(fn(*args, **kwargs))
    except Exception as exc:
        return Err(exc)


async def safe_async_exec(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Result[Any, Exception]:
    """Wraps an asynchronous coroutine in a Result monad."""
    try:
        res = await fn(*args, **kwargs)
        return Ok(res)
    except Exception as exc:
        return Err(exc)
