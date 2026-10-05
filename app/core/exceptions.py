from typing import Any, Optional, Dict


class AppException(Exception):
    """Base application exception."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: str = "INTERNAL_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}


class BrokerConnectionError(AppException):
    def __init__(self, message: str, broker: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=502,
            error_code="BROKER_CONNECTION_ERROR",
            details={"broker": broker, **(details or {})},
        )


class BrokerExecutionError(AppException):
    def __init__(self, message: str, broker: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=400,
            error_code="BROKER_EXECUTION_ERROR",
            details={"broker": broker, **(details or {})},
        )


class AccountNotFoundError(AppException):
    def __init__(self, account_id: int):
        super().__init__(
            message=f"Trading account with ID {account_id} was not found.",
            status_code=404,
            error_code="ACCOUNT_NOT_FOUND",
            details={"account_id": account_id},
        )


class AccountInactiveError(AppException):
    def __init__(self, account_id: int):
        super().__init__(
            message=f"Trading account {account_id} is marked inactive.",
            status_code=403,
            error_code="ACCOUNT_INACTIVE",
            details={"account_id": account_id},
        )


class SymbolNotSupportedError(AppException):
    def __init__(self, symbol: str, broker: str, hint: Optional[str] = None):
        details: Dict[str, Any] = {"symbol": symbol, "broker": broker}
        if hint:
            details["hint"] = hint
        super().__init__(
            message=f"Symbol '{symbol}' is not supported or currently closed on {broker}.",
            status_code=422,
            error_code="SYMBOL_NOT_SUPPORTED",
            details=details,
        )


class AuthenticationFailedError(AppException):
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(
            message=message,
            status_code=401,
            error_code="AUTH_FAILED",
        )
