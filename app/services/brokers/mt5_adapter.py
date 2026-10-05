import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx

from app.core.config import settings
from app.core.result import Result, Ok, Err
from app.services.brokers.base import IMarketBrokerAdapter

logger = logging.getLogger("quant_server.mt5_adapter")


class MT5Adapter(IMarketBrokerAdapter):
    """
    MetaTrader 5 broker adapter.
    Communicates via high-speed async HTTP with the MT5 Wine Gateway service (app.py)
    or directly via Python bindings if running locally.
    """

    def __init__(
        self,
        login: int,
        password: str,
        server: str,
        api_url: Optional[str] = None,
        path: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ):
        self.login = int(login) if login else 0
        self.password = str(password) if password else ""
        self.server = str(server) if server else ""
        self.api_url = (api_url or settings.MT5_API_URL).rstrip("/")
        self.path = path
        self.host = host or settings.MT5_BRIDGE_HOST
        self.port = port or settings.MT5_BRIDGE_PORT
        self._connected = False
        self._client = httpx.AsyncClient(base_url=self.api_url, timeout=15.0)

    async def connect(self) -> Result[bool, str]:
        """Verifies MT5 gateway health and account connectivity."""
        try:
            # Check gateway health
            resp = await self._client.get("/health")
            if resp.status_code == 200:
                data = resp.json()
                self._connected = True
                logger.info(f"MT5 Gateway connected successfully at {self.api_url}. Status: {data}")
                return Ok(True)
            else:
                msg = f"MT5 Gateway returned status {resp.status_code}: {resp.text}"
                logger.error(msg)
                return Err(msg)
        except httpx.RequestError as e:
            # Check if native MT5 or bridge is available locally as fallback
            try:
                import MetaTrader5 as mt5
                init_res = await asyncio.to_thread(mt5.initialize)
                if init_res:
                    self._connected = True
                    return Ok(True)
            except Exception:
                pass
            return Err(f"Could not connect to MT5 Gateway at {self.api_url}: {str(e)}")

    async def is_connected(self) -> bool:
        if not self._connected:
            return False
        try:
            resp = await self._client.get("/health", timeout=3.0)
            return resp.status_code == 200
        except Exception:
            return False

    async def get_balance(self) -> Result[float, str]:
        try:
            resp = await self._client.get("/health")
            if resp.status_code == 200:
                data = resp.json()
                acc_info = data.get("account_info", {})
                bal = float(acc_info.get("balance", 0.0))
                return Ok(bal)
            return Err(f"Failed to fetch MT5 balance. Status: {resp.status_code}")
        except Exception as e:
            return Err(f"Error retrieving MT5 balance: {str(e)}")

    async def get_current_price(self, symbol: str) -> Result[float, str]:
        clean_symbol, _, _ = self.parse_asset_info(symbol)
        try:
            resp = await self._client.get(f"/symbol/tick", params={"symbol": clean_symbol})
            if resp.status_code == 200:
                tick = resp.json().get("tick", {})
                price = tick.get("ask") or tick.get("bid") or tick.get("last")
                if price:
                    return Ok(float(price))
                return Err(f"Empty price data in tick response for {clean_symbol}")
            return Err(f"Error fetching tick for {clean_symbol}: {resp.text}")
        except Exception as e:
            return Err(f"Exception fetching tick for {clean_symbol}: {str(e)}")

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
        clean_symbol, _, _ = self.parse_asset_info(symbol)
        payload = {
            "symbol": clean_symbol,
            "volume": float(volume),
            "type": "BUY",
            "deviation": int(deviation),
            "comment": comment,
            "magic": int(magic),
            "type_filling": type_filling,
        }
        if sl is not None:
            payload["sl"] = float(sl)
        if tp is not None:
            payload["tp"] = float(tp)

        try:
            resp = await self._client.post("/order", json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return Ok(data.get("result", data))
            return Err(f"MT5 Buy Order rejected ({resp.status_code}): {resp.text}")
        except Exception as e:
            return Err(f"MT5 Buy Order error: {str(e)}")

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
        clean_symbol, _, _ = self.parse_asset_info(symbol)
        payload = {
            "symbol": clean_symbol,
            "volume": float(volume),
            "type": "SELL",
            "deviation": int(deviation),
            "comment": comment,
            "magic": int(magic),
            "type_filling": type_filling,
        }
        if sl is not None:
            payload["sl"] = float(sl)
        if tp is not None:
            payload["tp"] = float(tp)

        try:
            resp = await self._client.post("/order", json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return Ok(data.get("result", data))
            return Err(f"MT5 Sell Order rejected ({resp.status_code}): {resp.text}")
        except Exception as e:
            return Err(f"MT5 Sell Order error: {str(e)}")

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
        clean_symbol, _, _ = self.parse_asset_info(symbol)
        payload = {
            "symbol": clean_symbol,
            "volume": float(volume),
            "type": order_type.upper(),
            "price": float(price),
            "comment": comment,
            "magic": int(magic),
        }
        if sl is not None:
            payload["sl"] = float(sl)
        if tp is not None:
            payload["tp"] = float(tp)

        try:
            resp = await self._client.post("/order", json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return Ok(data.get("result", data))
            return Err(f"MT5 Pending Order rejected: {resp.text}")
        except Exception as e:
            return Err(f"MT5 Pending Order exception: {str(e)}")

    async def close_position(
        self,
        ticket: int,
        symbol: str,
        volume: float,
        deviation: int = 20,
        magic: int = 0,
        comment: str = "Close via API",
    ) -> Result[Dict[str, Any], str]:
        payload = {
            "position": {
                "ticket": int(ticket),
                "symbol": symbol,
                "volume": float(volume),
                "type": 0,  # Auto-resolved by gateway lib.py
            }
        }
        try:
            resp = await self._client.post("/close_position", json=payload)
            if resp.status_code == 200:
                return Ok(resp.json())
            return Err(f"Close position failed ({resp.status_code}): {resp.text}")
        except Exception as e:
            return Err(f"Close position exception: {str(e)}")

    async def close_all_positions(
        self,
        order_type: str = "all",
        magic: Optional[int] = None,
    ) -> Result[List[Dict[str, Any]], str]:
        payload: Dict[str, Any] = {"order_type": order_type}
        if magic is not None:
            payload["magic"] = int(magic)
        try:
            resp = await self._client.post("/close_all_positions", json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return Ok(data.get("result", []))
            return Err(f"Close all positions failed: {resp.text}")
        except Exception as e:
            return Err(f"Close all positions exception: {str(e)}")

    async def get_positions(self) -> Result[List[Dict[str, Any]], str]:
        try:
            resp = await self._client.get("/positions")
            if resp.status_code == 200:
                return Ok(resp.json().get("positions", []))
            return Err(f"Get positions failed: {resp.text}")
        except Exception as e:
            return Err(f"Get positions exception: {str(e)}")

    async def get_history_deals(
        self,
        date_from: datetime,
        date_to: datetime,
    ) -> Result[List[Dict[str, Any]], str]:
        params = {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
        }
        try:
            resp = await self._client.get("/history/deals", params=params)
            if resp.status_code == 200:
                return Ok(resp.json().get("deals", []))
            return Err(f"Get history deals failed: {resp.text}")
        except Exception as e:
            return Err(f"Get history deals exception: {str(e)}")

    async def get_rates(
        self,
        symbol: str,
        timeframe: str,
        count: int,
    ) -> Result[List[Dict[str, Any]], str]:
        clean_symbol, _, _ = self.parse_asset_info(symbol)
        params = {
            "symbol": clean_symbol,
            "timeframe": timeframe.upper(),
            "count": int(count),
        }
        try:
            resp = await self._client.get("/data/rates_from_pos", params=params)
            if resp.status_code == 200:
                return Ok(resp.json().get("rates", []))
            return Err(f"Get rates failed: {resp.text}")
        except Exception as e:
            return Err(f"Get rates exception: {str(e)}")

    async def close(self) -> Result[None, str]:
        try:
            await self._client.aclose()
            self._connected = False
            return Ok(None)
        except Exception as e:
            return Err(f"Error closing MT5 adapter client: {str(e)}")
