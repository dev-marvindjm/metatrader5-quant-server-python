import re
import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional, Tuple, Dict, List
from app.core.result import Result, Ok, Err


class IBrokerAdapter(ABC):
    """
    Base asynchronous interface for all broker adapters.
    All operations return a Result monad to guarantee strict typing and safe error handling.
    """

    @abstractmethod
    async def connect(self) -> Result[bool, str]:
        """Establishes connection to the broker."""
        pass

    @abstractmethod
    async def is_connected(self) -> bool:
        """Checks if connection is alive."""
        pass

    @abstractmethod
    async def get_balance(self) -> Result[float, str]:
        """Retrieves account balance."""
        pass

    @abstractmethod
    async def get_current_price(self, symbol: str) -> Result[float, str]:
        """Retrieves latest market price for symbol."""
        pass

    @abstractmethod
    async def close(self) -> Result[None, str]:
        """Closes broker connection and releases resources."""
        pass

    @staticmethod
    def parse_asset_info(asset: str) -> Tuple[str, bool, bool]:
        """
        Parses an asset string into (clean_base, is_otc, is_perp).
        Handles:
            'EURUSD' -> ('EURUSD', False, False)
            'EUR/USD' -> ('EURUSD', False, False)
            'EURUSD_otc' -> ('EURUSD', True, False)
            'EURUSD-OTC' -> ('EURUSD', True, False)
            'EURUSD (OTC)' -> ('EURUSD', True, False)
            'BTCUSDT.P' -> ('BTCUSDT', False, True)
        """
        if not asset:
            return ("", False, False)
        raw = asset.strip()
        is_perp = False
        is_otc = False

        upper = raw.upper()
        if upper.endswith(".P"):
            is_perp = True
            raw = raw[:-2]
        elif upper.endswith("-PERP") or upper.endswith("_PERP"):
            is_perp = True
            raw = raw[:-5]

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
        clean_base = re.sub(r"[\/\-_ \.]", "", raw).strip().upper()
        return (clean_base, is_otc, is_perp)

    def format_broker_asset(self, asset: str, broker_code: str) -> str:
        """
        Formats symbol to match provider conventions:
        - IQ Option: BASE-OTC
        - Quotex / PocketOption: BASE_otc
        - MT5: BASE (clean)
        """
        base, is_otc, _ = self.parse_asset_info(asset)
        b = (broker_code or "").lower()
        if "iq" in b:
            return f"{base}-OTC" if is_otc else base
        elif "quotex" in b or "pocket" in b:
            return f"{base}_otc" if is_otc else base
        elif "mt5" in b or "meta" in b:
            return base
        return f"{base}_otc" if is_otc else base


class IBinaryBrokerAdapter(IBrokerAdapter):
    """Interface for Binary Options brokers (IQ Option, Quotex, Pocket Option)."""

    @abstractmethod
    async def buy(self, symbol: str, amount: float, duration: int) -> Result[str, str]:
        """Places a CALL (BUY / UP) trade. Returns trade ID."""
        pass

    @abstractmethod
    async def sell(self, symbol: str, amount: float, duration: int) -> Result[str, str]:
        """Places a PUT (SELL / DOWN) trade. Returns trade ID."""
        pass

    @abstractmethod
    async def get_trade_result(self, trade_id: str) -> Result[bool, str]:
        """Checks if trade won (True) or lost (False)."""
        pass

    async def execute_martingale(
        self,
        action: str,
        symbol: str,
        amount: float,
        duration: int,
        steps: int = 0,
        multiplier: float = 2.0,
    ) -> Result[Dict[str, Any], str]:
        """
        Executes a martingale sequence until win or step exhaustion.
        """
        current_amount = amount
        action_upper = action.upper()

        for step in range(steps + 1):
            if action_upper in ("BUY", "CALL", "UP"):
                trade_res = await self.buy(symbol, current_amount, duration)
            elif action_upper in ("SELL", "PUT", "DOWN"):
                trade_res = await self.sell(symbol, current_amount, duration)
            else:
                return Err(f"Invalid action: {action}")

            if trade_res.is_err():
                return Err(f"Trade failed at step {step}: {trade_res.unwrap_err()}")

            trade_id = trade_res.unwrap()
            # Wait for option expiry plus small buffer
            await asyncio.sleep(duration + 1)

            result_res = await self.get_trade_result(trade_id)
            is_win = result_res.unwrap_or(False)

            if is_win:
                return Ok({
                    "won": True,
                    "step_won": step,
                    "final_amount": current_amount,
                    "trade_id": trade_id,
                })

            current_amount = round(current_amount * multiplier, 2)

        return Ok({
            "won": False,
            "step_won": None,
            "final_amount": current_amount,
            "trade_id": trade_id,
        })


class IMarketBrokerAdapter(IBrokerAdapter):
    """Interface for Market brokers (MetaTrader 5: Forex, CFDs, Stocks, Crypto)."""

    @abstractmethod
    async def buy_market(
        self,
        symbol: str,
        volume: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        deviation: int = 20,
        comment: str = "",
        magic: int = 0,
        type_filling: str = "ORDER_FILLING_IOC",
    ) -> Result[Dict[str, Any], str]:
        pass

    @abstractmethod
    async def sell_market(
        self,
        symbol: str,
        volume: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        deviation: int = 20,
        comment: str = "",
        magic: int = 0,
        type_filling: str = "ORDER_FILLING_IOC",
    ) -> Result[Dict[str, Any], str]:
        pass

    @abstractmethod
    async def send_pending_order(
        self,
        symbol: str,
        order_type: str,
        volume: float,
        price: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: str = "",
        magic: int = 0,
    ) -> Result[Dict[str, Any], str]:
        pass

    @abstractmethod
    async def close_position(
        self,
        ticket: int,
        symbol: str,
        volume: float,
        deviation: int = 20,
        magic: int = 0,
        comment: str = "Close via API",
    ) -> Result[Dict[str, Any], str]:
        pass

    @abstractmethod
    async def close_all_positions(
        self,
        order_type: str = "all",
        magic: Optional[int] = None,
    ) -> Result[List[Dict[str, Any]], str]:
        pass

    @abstractmethod
    async def get_positions(self) -> Result[List[Dict[str, Any]], str]:
        pass

    @abstractmethod
    async def get_history_deals(
        self,
        date_from: datetime,
        date_to: datetime,
    ) -> Result[List[Dict[str, Any]], str]:
        pass

    @abstractmethod
    async def get_rates(
        self,
        symbol: str,
        timeframe: str,
        count: int,
    ) -> Result[List[Dict[str, Any]], str]:
        pass
