import asyncio
import logging
from typing import Any, Optional
# pyrefly: ignore [missing-import]
from .base_broker import BaseBroker

logger = logging.getLogger(__name__)

try:
    from BinaryOptionsToolsV2 import PocketOptionAsync
    POCKETOPTION_AVAILABLE = True
except ImportError:
    PocketOptionAsync = None
    POCKETOPTION_AVAILABLE = False

class PocketOptionBroker(BaseBroker):
    def __init__(self, ssid: str):
        self.ssid = ssid
        try:
            self.client = PocketOptionAsync(ssid=self.ssid) if POCKETOPTION_AVAILABLE and PocketOptionAsync else None
        except Exception as e:
            logger.warning(f"PocketOptionAsync initialization notice: {e}")
            self.client = None

    async def connect(self) -> bool:
        if not POCKETOPTION_AVAILABLE or self.client is None:
            logger.error("BinaryOptionsToolsV2 package is not installed.")
            return False
        try:
            await self.client.connect()
            await asyncio.sleep(2)
            balance = await self.get_balance()
            return balance is not None
        except Exception as e:
            logger.error(f"PocketOption connect error: {e}")
            return False

    async def is_connected(self) -> bool:
        if not POCKETOPTION_AVAILABLE or self.client is None:
            return False
        try:
            await self.client.balance()
            return True
        except Exception:
            return False

    async def get_balance(self) -> float:
        if not POCKETOPTION_AVAILABLE or self.client is None:
            return 0.0
        try:
            return await self.client.balance()
        except Exception:
            return 0.0

    async def verify_and_resolve_symbol(self, asset: str) -> tuple[Optional[str], Optional[str]]:
        if not asset:
            return None, "Asset is empty"

        base, is_otc, _ = self.parse_asset_info(asset)
        if not base:
            return None, f"Invalid symbol '{asset}'"

        target_symbol = f"{base}_otc" if is_otc else base

        if POCKETOPTION_AVAILABLE and self.client is not None:
            try:
                active_list = await self.client.active_assets()
                if active_list and isinstance(active_list, list):
                    symbols = [item.get("symbol") for item in active_list if isinstance(item, dict) and item.get("symbol")]

                    if target_symbol in symbols:
                        return target_symbol, None

                    for s in symbols:
                        if s.lower() == target_symbol.lower():
                            return s, None

                    if not is_otc and f"{base}_otc" in symbols:
                        logger.info(f"PocketOption: Standard {base} not in open assets, using open OTC variant {base}_otc")
                        return f"{base}_otc", None

                    if is_otc and base in symbols:
                        logger.info(f"PocketOption: OTC {target_symbol} not open, standard {base} is available")
                        return base, None

                    matching = [s for s in symbols if base[:3].lower() in s.lower()]
                    return None, f"Symbol '{asset}' (resolved: '{target_symbol}') not found in Pocket Option active assets. Close matches: {matching[:5]}"
            except Exception as e:
                logger.debug(f"PocketOption active_assets check error: {e}")

        return target_symbol, None

    async def buy(self, asset: str, amount: float, duration: int) -> Any:
        if not POCKETOPTION_AVAILABLE or self.client is None:
            return None
        resolved, err = await self.verify_and_resolve_symbol(asset)
        if not resolved:
            logger.error(f"PocketOption buy aborted: {err}")
            return None
        trade = await self.client.buy(resolved, amount, duration)
        await asyncio.sleep(2)
        return trade

    async def sell(self, asset: str, amount: float, duration: int) -> Any:
        if not POCKETOPTION_AVAILABLE or self.client is None:
            return None
        resolved, err = await self.verify_and_resolve_symbol(asset)
        if not resolved:
            logger.error(f"PocketOption sell aborted: {err}")
            return None
        trade = await self.client.sell(resolved, amount, duration)
        await asyncio.sleep(2)
        return trade

    async def close(self):
        pass

    async def get_trade_result(self, trade_id: Any) -> bool:
        if not POCKETOPTION_AVAILABLE or self.client is None:
            return False
        try:
            result = await self.client.check_win(trade_id)
            if isinstance(result, bool):
                return result
            if isinstance(result, dict):
                return result.get("result") == "win"
        except Exception:
            pass
        return False

    async def get_current_price(self, asset: str) -> Optional[float]:
        if not POCKETOPTION_AVAILABLE or self.client is None:
            return None
        resolved, err = await self.verify_and_resolve_symbol(asset)
        if not resolved:
            logger.warning(f"PocketOption get_current_price aborted: {err}")
            return None
        try:
            candles = await self.client.candles(resolved, 60)
            if candles and isinstance(candles, list) and len(candles) > 0:
                last_candle = candles[-1]
                close_p = last_candle.get("close") or last_candle.get("open")
                if close_p is not None:
                    return float(close_p)
        except Exception as e:
            logger.warning(f"Error fetching PocketOption price for {resolved}: {e}")
        return None

__all__ = ["PocketOptionBroker"]
