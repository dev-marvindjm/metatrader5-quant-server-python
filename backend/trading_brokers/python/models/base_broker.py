import asyncio
import re
from abc import ABC, abstractmethod
from typing import Any, Optional, Final

class BaseBroker(ABC):
    ACTION_UP: Final[bool] = True
    ACTION_DOWN: Final[bool] = False

    @abstractmethod
    async def connect(self) -> bool:
        """Establishes connection with the broker."""
        pass

    @abstractmethod
    async def is_connected(self) -> bool:
        """Checks if the client is connected."""
        pass

    @abstractmethod
    async def get_balance(self) -> float:
        """Returns the current balance."""
        pass

    @abstractmethod
    async def buy(self, asset: str, amount: float, duration: int) -> Any:
        """Places a buy (call) trade."""
        pass

    @abstractmethod
    async def sell(self, asset: str, amount: float, duration: int) -> Any:
        """Places a sell (put) trade."""
        pass

    @abstractmethod
    async def close(self):
        """Closes the connection."""
        pass

    @abstractmethod
    async def get_trade_result(self, trade_id: Any) -> bool:
        """
        Checks the result of a trade.
        Returns True if win, False if loss.
        """
        pass

    @abstractmethod
    async def get_current_price(self, asset: str) -> Optional[float]:
        """
        Retrieves the current market price for an asset/symbol.
        """
        pass

    async def martingale(self, action: bool, asset: str, amount: float, steps: int, multiplier: float, duration: int) -> bool:
        """
        Executes a martingale sequence.
        :param action: 'buy' or 'sell' (or bool True/False)
        :param asset: Asset to trade
        :param amount: Initial investment amount
        :param steps: Number of martingale steps (0 = only initial trade)
        :param multiplier: Multiplier for next amount on loss
        :param duration: Trade duration in seconds
        :return: True if any trade in the sequence won, False if all lost
        """
        current_amount = amount
        for step in range(steps + 1):
            if action == self.ACTION_UP:
                trade_id = await self.buy(asset, current_amount, duration)
            elif action == self.ACTION_DOWN:
                trade_id = await self.sell(asset, current_amount, duration)
            else:
                return False

            if not trade_id:
                return False

            await asyncio.sleep(duration + 1)
            
            win = await self.get_trade_result(trade_id)
            if win:
                return True
                
            current_amount *= multiplier
            
        return False

    @staticmethod
    def parse_asset_info(asset: str) -> tuple[str, bool, bool]:
        """
        Parses an asset string into (base_symbol, is_otc, is_perp).
        Examples:
            'EURUSD' -> ('EURUSD', False, False)
            'EUR/USD' -> ('EURUSD', False, False)
            'EURUSD_otc' -> ('EURUSD', True, False)
            'EUR/USD-OTC' -> ('EURUSD', True, False)
            'EURUSD (OTC)' -> ('EURUSD', True, False)
            'BTCUSDT.P' -> ('BTCUSDT', False, True)
            'BTC-PERP' -> ('BTC', False, True)
        """
        if not asset:
            return ("", False, False)
        raw = asset.strip()
        is_perp = False
        is_otc = False

        # Detect perp
        upper = raw.upper()
        if upper.endswith(".P"):
            is_perp = True
            raw = raw[:-2]
        elif upper.endswith("-PERP") or upper.endswith("_PERP"):
            is_perp = True
            raw = raw[:-5]

        # Detect OTC patterns
        upper = raw.upper()
        otc_patterns = [
            r"[\s\-_/\.\[\(]OTC[\)\]]?",
            r"\(OTC\)",
            r"\[OTC\]",
            r"_OTC",
            r"-OTC",
            r"/OTC",
        ]
        matched_otc = False
        for pat in otc_patterns:
            if re.search(pat, upper):
                matched_otc = True
                raw = re.sub(pat, "", raw, flags=re.IGNORECASE)
                break
        
        if not matched_otc and upper.endswith("OTC") and len(upper) > 3:
            matched_otc = True
            raw = raw[:-3]

        is_otc = matched_otc

        # Clean punctuation from base symbol: /, -, _, space, dot
        clean_base = re.sub(r"[\/\-_ \.]", "", raw).strip().upper()
        return (clean_base, is_otc, is_perp)

    @staticmethod
    def format_broker_asset(asset: str, broker_code: str) -> str:
        """
        Formats symbol according to broker specific conventions.
        - IQ Option: SYMBOL-OTC (hyphen, uppercase)
        - Quotex / PocketOption: SYMBOL_otc (underscore, lowercase)
        - MetaTrader 5: SYMBOL (clean base, no OTC suffix)
        """
        base, is_otc, _ = BaseBroker.parse_asset_info(asset)
        b = (broker_code or "").lower()
        if "iq" in b:
            return f"{base}-OTC" if is_otc else base
        elif "quotex" in b or "pocket" in b:
            return f"{base}_otc" if is_otc else base
        elif "mt5" in b or "metatrader" in b:
            return base
        return f"{base}_otc" if is_otc else base

    @staticmethod
    def clean_asset(asset: str, asset_separator: str = None, asset_upper: bool = True, remove: str | tuple[str] = None, otc_separator: str = None, otc_lower: bool = None) -> str:
        symbol = asset
        if isinstance(remove, tuple):
            for c in remove:
                asset = asset.replace(c, "")
        else:
            if remove:
                asset = asset.replace(remove, "")
        if asset_upper:
            symbol = symbol.upper()
        has_otc = asset.endswith(('OTC', '(OTC)')) and not asset[-4].isalnum()
        
        if has_otc:
            otc_sep = "otc"
            if otc_separator:
                otc_sep = otc_sep + otc_separator

            if otc_lower:
                partes = symbol.rsplit("OTC", 1)
                symbol = otc_sep.join(partes) if len(partes) > 1 else symbol
        
            if otc_separator:
                symbol = symbol[:-4] + symbol[-4] + otc_sep
        return symbol

class MarketBaseBroker(BaseBroker):
    """
    Base class for market brokers (Forex, CFD, Stocks) that support 
    market, limit, and stop orders.
    """
    
    @abstractmethod
    async def buy_market(self, symbol: str, volume: float, sl: Optional[float] = None, tp: Optional[float] = None) -> Any:
        """Places a market buy order."""
        pass

    @abstractmethod
    async def sell_market(self, symbol: str, volume: float, sl: Optional[float] = None, tp: Optional[float] = None) -> Any:
        """Places a market sell order."""
        pass

    @abstractmethod
    async def buy_limit(self, symbol: str, volume: float, price: float, sl: Optional[float] = None, tp: Optional[float] = None) -> Any:
        """Places a buy limit order."""
        pass

    @abstractmethod
    async def sell_limit(self, symbol: str, volume: float, price: float, sl: Optional[float] = None, tp: Optional[float] = None) -> Any:
        """Places a sell limit order."""
        pass

    @abstractmethod
    async def buy_stop(self, symbol: str, volume: float, price: float, sl: Optional[float] = None, tp: Optional[float] = None) -> Any:
        """Places a buy stop order."""
        pass

    @abstractmethod
    async def sell_stop(self, symbol: str, volume: float, price: float, sl: Optional[float] = None, tp: Optional[float] = None) -> Any:
        """Places a sell stop order."""
        pass

__all__ = ["BaseBroker", "MarketBaseBroker"]
