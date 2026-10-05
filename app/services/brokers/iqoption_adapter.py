import asyncio
import logging
import time
from typing import Any, Optional, Tuple
from app.core.result import Result, Ok, Err
from app.services.brokers.base import IBinaryBrokerAdapter

logger = logging.getLogger("quant_server.iqoption")

try:
    from iqoption_async.client import IQOptionClient as Client
    from iqoption_async.constants import ACTIVES
    IQOPTION_AVAILABLE = True
except ImportError:
    Client = None
    ACTIVES = {}
    IQOPTION_AVAILABLE = False


class IQOptionAdapter(IBinaryBrokerAdapter):
    """
    IQ Option asynchronous broker adapter supporting binary and turbo options,
    automatic OTC fallback, and PRACTICE/REAL account switching.
    """

    def __init__(self, email: str, password: str, account_mode: str = "PRACTICE"):
        self.email = email.lower().strip() if email else ""
        self.password = password
        self.account_mode = account_mode.upper()
        self.client = Client(email=self.email, password=self.password) if IQOPTION_AVAILABLE and Client else None
        self._connected = False

    async def connect(self) -> Result[bool, str]:
        if not IQOPTION_AVAILABLE or self.client is None:
            logger.warning("iqoption_async not installed or client unavailable. Operating in simulated fallback.")
            self._connected = True
            return Ok(True)

        try:
            connected, reason = await self.client.connect()
            if not connected:
                self._connected = False
                return Err(f"IQ Option connection failed: {reason}")

            # Switch to requested account mode
            try:
                await self.client.change_balance(self.account_mode)
            except Exception as b_err:
                logger.warning(f"IQ Option change_balance notice: {b_err}")

            self._connected = True
            return Ok(True)
        except Exception as e:
            self._connected = False
            return Err(f"IQ Option connection exception: {str(e)}")

    async def is_connected(self) -> bool:
        if not IQOPTION_AVAILABLE or self.client is None:
            return self._connected
        try:
            return await self.client.check_connect()
        except Exception:
            return False

    async def get_balance(self) -> Result[float, str]:
        if not IQOPTION_AVAILABLE or self.client is None:
            return Ok(10000.0 if self.account_mode == "PRACTICE" else 0.0)
        try:
            bal = await self.client.get_balance()
            return Ok(float(bal))
        except Exception as e:
            return Err(f"Error fetching IQ Option balance: {str(e)}")

    def _convert_duration_to_minutes(self, duration: int) -> int:
        dur_int = int(duration)
        if dur_int >= 60:
            return max(1, round(dur_int / 60))
        return max(1, dur_int)

    def _check_asset_open(self, asset_name: str) -> bool:
        if not hasattr(self.client, "OPEN_TIME") or not self.client.OPEN_TIME:
            return True
        for opt in ["turbo", "binary"]:
            if opt in self.client.OPEN_TIME and asset_name in self.client.OPEN_TIME[opt]:
                return bool(self.client.OPEN_TIME[opt][asset_name].get("open", False))
        return False

    async def verify_and_resolve_symbol(self, asset: str) -> Tuple[Optional[str], Optional[str]]:
        if not asset:
            return None, "Asset is empty"

        base, is_otc, _ = self.parse_asset_info(asset)
        if not base:
            return None, f"Invalid symbol '{asset}'"

        target_symbol = f"{base}-OTC" if is_otc else base

        if not IQOPTION_AVAILABLE or self.client is None or not ACTIVES:
            return target_symbol, None

        if target_symbol in ACTIVES:
            if not is_otc:
                otc_variant = f"{base}-OTC"
                if self._check_asset_open(target_symbol):
                    return target_symbol, None
                elif otc_variant in ACTIVES and self._check_asset_open(otc_variant):
                    logger.info(f"IQ Option: Standard {base} is closed, switching to open OTC {otc_variant}")
                    return otc_variant, None
            return target_symbol, None

        for act in ACTIVES.keys():
            if act.upper() == target_symbol.upper():
                return act, None

        if not is_otc:
            otc_cand = f"{base}-OTC"
            for act in ACTIVES.keys():
                if act.upper() == otc_cand.upper():
                    return act, None

        return target_symbol, None

    async def buy(self, symbol: str, amount: float, duration: int) -> Result[str, str]:
        resolved, err = await self.verify_and_resolve_symbol(symbol)
        if not resolved:
            return Err(f"IQ Option buy rejected: {err}")

        if not IQOPTION_AVAILABLE or self.client is None:
            # Fallback trade ID simulation
            mock_id = f"mock_iq_{int(time.time() * 1000)}"
            return Ok(mock_id)

        exp_minutes = self._convert_duration_to_minutes(duration)
        try:
            res = await self.client.buy(amount, resolved, "call", exp_minutes)
            if isinstance(res, tuple):
                success = res[0]
                if success is True and len(res) >= 2 and res[1] is not None:
                    return Ok(str(res[1]))
                err_msg = res[1] if len(res) >= 2 else "Unknown trade error"
                return Err(f"IQ Option buy failed: {err_msg}")
            elif res:
                return Ok(str(res))
            return Err("IQ Option buy returned empty response")
        except Exception as e:
            return Err(f"IQ Option buy exception: {str(e)}")

    async def sell(self, symbol: str, amount: float, duration: int) -> Result[str, str]:
        resolved, err = await self.verify_and_resolve_symbol(symbol)
        if not resolved:
            return Err(f"IQ Option sell rejected: {err}")

        if not IQOPTION_AVAILABLE or self.client is None:
            mock_id = f"mock_iq_{int(time.time() * 1000)}"
            return Ok(mock_id)

        exp_minutes = self._convert_duration_to_minutes(duration)
        try:
            res = await self.client.buy(amount, resolved, "put", exp_minutes)
            if isinstance(res, tuple):
                success = res[0]
                if success is True and len(res) >= 2 and res[1] is not None:
                    return Ok(str(res[1]))
                err_msg = res[1] if len(res) >= 2 else "Unknown trade error"
                return Err(f"IQ Option sell failed: {err_msg}")
            elif res:
                return Ok(str(res))
            return Err("IQ Option sell returned empty response")
        except Exception as e:
            return Err(f"IQ Option sell exception: {str(e)}")

    async def get_trade_result(self, trade_id: str) -> Result[bool, str]:
        if not IQOPTION_AVAILABLE or self.client is None:
            return Ok(True)
        try:
            clean_id = int(str(trade_id).strip())
            result = await self.client.check_order(clean_id)
            if isinstance(result, bool):
                return Ok(result)
            if isinstance(result, dict):
                is_win = result.get("result") == "win" or result.get("win", False)
                return Ok(bool(is_win))
            return Ok(False)
        except Exception as e:
            return Err(f"Error checking IQ Option trade result: {str(e)}")

    async def get_current_price(self, symbol: str) -> Result[float, str]:
        resolved, _ = await self.verify_and_resolve_symbol(symbol)
        target = resolved or symbol

        if not IQOPTION_AVAILABLE or self.client is None:
            return Ok(1.0850)
        try:
            candles = await self.client.get_candles(target, 1, 1, time.time())
            if candles and isinstance(candles, list) and len(candles) > 0:
                last_candle = candles[-1]
                close_p = last_candle.get("close") or last_candle.get("open")
                if close_p is not None:
                    return Ok(float(close_p))
            return Err(f"No price candles available for {target}")
        except Exception as e:
            return Err(f"IQ Option price fetch error: {str(e)}")

    async def close(self) -> Result[None, str]:
        if IQOPTION_AVAILABLE and self.client is not None:
            try:
                if hasattr(self.client, "close"):
                    res = self.client.close()
                    if asyncio.iscoroutine(res):
                        await res
                elif hasattr(self.client, "disconnect"):
                    res = self.client.disconnect()
                    if asyncio.iscoroutine(res):
                        await res
            except Exception:
                pass
        self._connected = False
        return Ok(None)
