import asyncio
import logging
import time
from typing import Any, Optional, Tuple
from app.core.result import Result, Ok, Err
from app.services.brokers.base import IBinaryBrokerAdapter

logger = logging.getLogger("quant_server.pocketoption")

try:
    from BinaryOptionsToolsV2 import PocketOptionAsync
    POCKETOPTION_AVAILABLE = True
except ImportError:
    PocketOptionAsync = None
    POCKETOPTION_AVAILABLE = False


class PocketOptionAdapter(IBinaryBrokerAdapter):
    """
    Pocket Option asynchronous broker adapter supporting SSID token authentication,
    OTC active assets validation, and trade outcome polling.
    """

    def __init__(self, ssid: str):
        self.ssid = ssid.strip() if ssid else ""
        self._connected = False
        try:
            self.client = (
                PocketOptionAsync(ssid=self.ssid)
                if POCKETOPTION_AVAILABLE and PocketOptionAsync
                else None
            )
        except Exception as e:
            logger.warning(f"PocketOptionAsync initialization notice: {e}")
            self.client = None

    async def connect(self) -> Result[bool, str]:
        if not POCKETOPTION_AVAILABLE or self.client is None:
            logger.warning("BinaryOptionsToolsV2 not installed. Operating in simulated fallback.")
            self._connected = True
            return Ok(True)

        try:
            await self.client.connect()
            await asyncio.sleep(1.5)
            bal = await self.get_balance()
            if bal.is_ok():
                self._connected = True
                return Ok(True)
            return Err("PocketOption connected but could not retrieve balance.")
        except Exception as e:
            self._connected = False
            return Err(f"PocketOption connection exception: {str(e)}")

    async def is_connected(self) -> bool:
        if not POCKETOPTION_AVAILABLE or self.client is None:
            return self._connected
        try:
            await self.client.balance()
            return True
        except Exception:
            return False

    async def get_balance(self) -> Result[float, str]:
        if not POCKETOPTION_AVAILABLE or self.client is None:
            return Ok(10000.0)
        try:
            bal = await self.client.balance()
            if bal is not None:
                return Ok(float(bal))
            return Err("Pocket Option returned None for balance")
        except Exception as e:
            return Err(f"Error retrieving Pocket Option balance: {str(e)}")

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
            return Err(f"Pocket Option buy rejected: {err}")

        if not POCKETOPTION_AVAILABLE or self.client is None:
            mock_id = f"mock_po_{int(time.time() * 1000)}"
            return Ok(mock_id)

        try:
            trade = await self.client.buy(resolved, amount, duration)
            await asyncio.sleep(1)
            trade_id = (
                trade.get("id") or trade.get("trade_id")
                if isinstance(trade, dict)
                else str(trade)
            )
            return Ok(str(trade_id))
        except Exception as e:
            return Err(f"Pocket Option buy exception: {str(e)}")

    async def sell(self, symbol: str, amount: float, duration: int) -> Result[str, str]:
        resolved, err = await self.verify_and_resolve_symbol(symbol)
        if not resolved:
            return Err(f"Pocket Option sell rejected: {err}")

        if not POCKETOPTION_AVAILABLE or self.client is None:
            mock_id = f"mock_po_{int(time.time() * 1000)}"
            return Ok(mock_id)

        try:
            trade = await self.client.sell(resolved, amount, duration)
            await asyncio.sleep(1)
            trade_id = (
                trade.get("id") or trade.get("trade_id")
                if isinstance(trade, dict)
                else str(trade)
            )
            return Ok(str(trade_id))
        except Exception as e:
            return Err(f"Pocket Option sell exception: {str(e)}")

    async def get_trade_result(self, trade_id: str) -> Result[bool, str]:
        if not POCKETOPTION_AVAILABLE or self.client is None:
            return Ok(True)
        try:
            result = await self.client.check_win(trade_id)
            if isinstance(result, bool):
                return Ok(result)
            if isinstance(result, dict):
                return Ok(result.get("result") == "win")
            return Ok(False)
        except Exception as e:
            return Err(f"Pocket Option check_win error: {str(e)}")

    async def get_current_price(self, symbol: str) -> Result[float, str]:
        resolved, _ = await self.verify_and_resolve_symbol(symbol)
        target = resolved or symbol

        if not POCKETOPTION_AVAILABLE or self.client is None:
            return Ok(1.0850)
        try:
            candles = await self.client.candles(target, 60)
            if candles and isinstance(candles, list) and len(candles) > 0:
                last_c = candles[-1]
                close_p = last_c.get("close") or last_c.get("open")
                if close_p is not None:
                    return Ok(float(close_p))
            return Err(f"No price candles returned for {target}")
        except Exception as e:
            return Err(f"Pocket Option price check error: {str(e)}")

    async def close(self) -> Result[None, str]:
        self._connected = False
        return Ok(None)
