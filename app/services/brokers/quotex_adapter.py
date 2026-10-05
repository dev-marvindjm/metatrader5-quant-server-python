import asyncio
import logging
import platform
import time
from typing import Any, Optional, Tuple
from app.core.result import Result, Ok, Err
from app.services.brokers.base import IBinaryBrokerAdapter

logger = logging.getLogger("quant_server.quotex")

try:
    from pyquotex.stable_api import Quotex
    QUOTEX_AVAILABLE = True
except ImportError:
    Quotex = None
    QUOTEX_AVAILABLE = False


def _apply_safari_impersonation_patch():
    """Patches pyquotex on macOS/Linux to use Safari impersonation, bypassing Turnstile blocks."""
    if not QUOTEX_AVAILABLE:
        return
    try:
        import pyquotex.network.navigator as nav
        from curl_cffi.requests import AsyncSession

        nav.USER_AGENT_DEFAULT = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
        )
        orig_ensure_client = nav.Browser.ensure_client

        async def patched_ensure_client(self):
            if self._client is None or getattr(self._client, "_closed", False) is True:
                client_kwargs = {
                    "headers": self.headers,
                    "timeout": 30.0,
                    "allow_redirects": True,
                    "impersonate": "safari17_0",
                }
                if self.proxies:
                    client_kwargs["proxies"] = (
                        {"http": self.proxies, "https": self.proxies}
                        if isinstance(self.proxies, str)
                        else self.proxies
                    )
                self._client = AsyncSession(**client_kwargs)
            return self._client

        nav.Browser.ensure_client = patched_ensure_client
    except Exception as e:
        logger.debug(f"Could not apply safari patch to pyquotex: {e}")


if QUOTEX_AVAILABLE and platform.system() in ("Darwin", "Linux"):
    _apply_safari_impersonation_patch()


class QuotexAdapter(IBinaryBrokerAdapter):
    """
    Quotex broker adapter supporting dual WebSocket and HTTP authentication,
    live/demo balances, and OTC automatic switching.
    """

    def __init__(self, email: str, password: str, account_mode: str = "PRACTICE"):
        self.email = email.lower().strip() if email else ""
        self.password = password
        self.account_mode = account_mode.upper()
        self._http_authenticated = False
        self._cached_balance = 0.0
        self._connected = False

        if QUOTEX_AVAILABLE and Quotex:
            self.client = Quotex(email=self.email, password=self.password)
            self.client.debug_ws_enable = False
        else:
            self.client = None

    async def connect(self) -> Result[bool, str]:
        if not QUOTEX_AVAILABLE or self.client is None:
            logger.warning("pyquotex not installed or unavailable. Operating in simulated fallback.")
            self._connected = True
            return Ok(True)

        try:
            # 1. Standard WebSocket connect
            res = await self.client.connect()
            connected = res[0] if isinstance(res, tuple) else bool(res)
            if connected:
                self.client.set_account_mode(self.account_mode)
                self._connected = True
                return Ok(True)

            # 2. HTTP REST authentication fallback
            logger.info("Quotex WebSocket attempt unsuccessful, trying HTTP REST auth...")
            if self.client.api:
                self.client.api.session_data["token"] = None
                auth_ok, auth_msg = await self.client.api.authenticate()
                if auth_ok:
                    self._http_authenticated = True
                    self._connected = True
                    self.client.set_account_mode(self.account_mode)
                    return Ok(True)

            return Err("Quotex connection failed via both WebSocket and HTTP REST.")
        except Exception as e:
            self._connected = False
            return Err(f"Quotex connection exception: {str(e)}")

    async def is_connected(self) -> bool:
        if not QUOTEX_AVAILABLE or self.client is None:
            return self._connected
        try:
            if await self.client.check_connect():
                return True
        except Exception:
            pass
        return self._http_authenticated

    async def get_balance(self) -> Result[float, str]:
        if not QUOTEX_AVAILABLE or self.client is None:
            return Ok(10000.0 if self.account_mode == "PRACTICE" else 0.0)
        try:
            if await self.client.check_connect():
                bal = await self.client.get_balance()
                if bal > 0:
                    self._cached_balance = float(bal)
                    return Ok(self._cached_balance)

            if self.client.api:
                async with self.client.api.login as login:
                    prof_res = await login.get_profile()
                    if prof_res.is_success:
                        data = prof_res.json().get("data", {})
                        is_demo = self.account_mode == "PRACTICE"
                        bal = float(data.get("demoBalance" if is_demo else "liveBalance", 0.0))
                        self._cached_balance = bal
                        return Ok(bal)

            return Ok(self._cached_balance)
        except Exception as e:
            return Err(f"Error fetching Quotex balance: {str(e)}")

    async def verify_and_resolve_symbol(self, asset: str) -> Tuple[Optional[str], Optional[str]]:
        if not asset:
            return None, "Asset is empty"

        base, is_otc, _ = self.parse_asset_info(asset)
        if not base:
            return None, f"Invalid symbol '{asset}'"

        target_symbol = f"{base}_otc" if is_otc else base
        return target_symbol, None

    async def buy(self, symbol: str, amount: float, duration: int) -> Result[str, str]:
        resolved, err = await self.verify_and_resolve_symbol(symbol)
        if not resolved:
            return Err(f"Quotex buy rejected: {err}")

        if not QUOTEX_AVAILABLE or self.client is None:
            mock_id = f"mock_qx_{int(time.time() * 1000)}"
            return Ok(mock_id)

        try:
            status, trade_data = await self.client.buy(amount, resolved, "call", duration)
            if status:
                trade_id = (
                    trade_data.get("id")
                    if isinstance(trade_data, dict)
                    else str(trade_data)
                )
                return Ok(str(trade_id))
            return Err(f"Quotex buy failed: {trade_data}")
        except Exception as e:
            return Err(f"Quotex buy exception: {str(e)}")

    async def sell(self, symbol: str, amount: float, duration: int) -> Result[str, str]:
        resolved, err = await self.verify_and_resolve_symbol(symbol)
        if not resolved:
            return Err(f"Quotex sell rejected: {err}")

        if not QUOTEX_AVAILABLE or self.client is None:
            mock_id = f"mock_qx_{int(time.time() * 1000)}"
            return Ok(mock_id)

        try:
            status, trade_data = await self.client.buy(amount, resolved, "put", duration)
            if status:
                trade_id = (
                    trade_data.get("id")
                    if isinstance(trade_data, dict)
                    else str(trade_data)
                )
                return Ok(str(trade_id))
            return Err(f"Quotex sell failed: {trade_data}")
        except Exception as e:
            return Err(f"Quotex sell exception: {str(e)}")

    async def get_trade_result(self, trade_id: str) -> Result[bool, str]:
        if not QUOTEX_AVAILABLE or self.client is None:
            return Ok(True)
        try:
            res = await self.client.check_win(trade_id)
            if isinstance(res, bool):
                return Ok(res)
            if isinstance(res, dict):
                return Ok(res.get("result") == "win" or res.get("win", False))
            return Ok(False)
        except Exception as e:
            return Err(f"Quotex check_win error: {str(e)}")

    async def get_current_price(self, symbol: str) -> Result[float, str]:
        resolved, _ = await self.verify_and_resolve_symbol(symbol)
        target = resolved or symbol

        if not QUOTEX_AVAILABLE or self.client is None:
            return Ok(1.0850)
        try:
            candles = await self.client.get_candles(target, 60)
            if candles and isinstance(candles, list) and len(candles) > 0:
                last_c = candles[-1]
                close_p = last_c.get("close") or last_c.get("open")
                if close_p is not None:
                    return Ok(float(close_p))
            return Err(f"No candles returned for {target}")
        except Exception as e:
            return Err(f"Quotex get_current_price error: {str(e)}")

    async def close(self) -> Result[None, str]:
        if QUOTEX_AVAILABLE and self.client is not None:
            try:
                await self.client.close()
            except Exception:
                pass
        self._connected = False
        return Ok(None)
