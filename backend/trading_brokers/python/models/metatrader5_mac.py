import asyncio
import logging
import os
from typing import Any, Optional

try:
    import mt5_mac_bridge as mt5_mac
    MT5_MAC_AVAILABLE = True
except ImportError:
    mt5_mac = None
    MT5_MAC_AVAILABLE = False

from .base_broker import MarketBaseBroker

logger = logging.getLogger(__name__)

class MetaTrader5MacBroker(MarketBaseBroker):
    """
    MetaTrader 5 broker implementation tailored for macOS and Linux environments
    using the mt5_mac_bridge package (supporting real bridge sockets or mock fallback).
    """
    def __init__(
        self,
        login: int,
        password: str,
        server: str,
        path: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ):
        try:
            self.login = int(login) if login else 0
        except (ValueError, TypeError):
            self.login = 0
        self.password = str(password) if password else ""
        self.server = str(server) if server else ""
        self.path = path
        self.host = host or os.environ.get("MT5_BRIDGE_HOST", "127.0.0.1")
        
        port_env = os.environ.get("MT5_MAC_PORT_API") or os.environ.get("MT5_BRIDGE_PORT") or "18812"
        try:
            self.port = port or int(port_env)
        except (ValueError, TypeError):
            self.port = 18812

        self.handle = None
        self.mt5 = None
        self._connected = False
        self.backend = "unknown"

    async def connect(self) -> bool:
        if not MT5_MAC_AVAILABLE or mt5_mac is None:
            logger.error("mt5_mac_bridge package is not installed. Please install it with: pip install mt5-mac-bridge")
            return False

        def _do_connect():
            try:
                # Preflight check if bridge is accepting connections
                bridge_up = mt5_mac.is_bridge_up(host=self.host, port=self.port, timeout=1.0)
                logger.info(
                    f"[MT5-Mac] Preflight bridge check on {self.host}:{self.port} -> "
                    f"{'BRIDGE DETECTED' if bridge_up else 'NO BRIDGE LISTENING (falling back to mock)'}"
                )

                self.handle = mt5_mac.init(
                    host=self.host,
                    port=self.port,
                    login=str(self.login) if self.login else None,
                    password=self.password,
                    server=self.server,
                    path=self.path,
                    register=True,
                )
                self.mt5 = self.handle.mt5
                self.backend = getattr(self.handle, "backend", "mock")

                if self.backend in ("bridge", "native"):
                    acc = self.mt5.account_info()
                    term = self.mt5.terminal_info()
                    logger.info(
                        f"[MT5-Mac] Connected to real MT5 {self.backend} backend. "
                        f"Account: {getattr(acc, 'login', self.login)} | Server: {getattr(acc, 'server', self.server)}"
                    )
                    return True
                else:
                    # Backend is mock: adapt mock attributes to match target account
                    acc = self.mt5.account_info()
                    if acc is not None and hasattr(acc, "login"):
                        acc.login = self.login
                    term = self.mt5.terminal_info()
                    if term is not None:
                        setattr(term, "connected", True)
                    logger.info(
                        f"[MT5-Mac] Connected to MT5 mock backend (offline simulation) for account {self.login}."
                    )
                    return True

            except Exception as e:
                logger.error(f"[MT5-Mac] Error initializing mt5_mac_bridge: {e}")
                return False

        try:
            res = await asyncio.to_thread(_do_connect)
            self._connected = bool(res)
            return self._connected
        except Exception as e:
            logger.exception(f"[MT5-Mac] Exception during connect: {e}")
            self._connected = False
            return False

    async def is_connected(self) -> bool:
        if not self._connected or self.mt5 is None or mt5_mac is None:
            return False

        def _check():
            try:
                if self.backend in ("bridge", "native"):
                    # Check if TCP bridge socket is still answering
                    if not mt5_mac.is_bridge_up(host=self.host, port=self.port, timeout=1.0):
                        logger.warning(f"[MT5-Mac] Bridge TCP socket is unreachable at {self.host}:{self.port}")
                        return False

                    term = self.mt5.terminal_info()
                    if not term or not getattr(term, "connected", False):
                        logger.warning("[MT5-Mac] Terminal info indicates connection lost")
                        return False

                    if self.login:
                        acc = self.mt5.account_info()
                        if not acc or getattr(acc, "login", None) != self.login:
                            logger.warning(
                                f"[MT5-Mac] Account login mismatch: {getattr(acc, 'login', None)} != {self.login}"
                            )
                            return False

                    return True

                elif self.backend == "mock":
                    # Mock backend check: verify mock account and in-memory flag
                    acc = self.mt5.account_info()
                    return acc is not None and self._connected

                return self._connected
            except Exception as e:
                logger.warning(f"[MT5-Mac] is_connected check error: {e}")
                return False

        try:
            return await asyncio.to_thread(_check)
        except Exception:
            return False

    async def get_balance(self) -> float:
        if not self.mt5:
            return 0.0

        def _balance():
            try:
                acc = self.mt5.account_info()
                if acc and hasattr(acc, "balance"):
                    return float(acc.balance)
                return 0.0
            except Exception as e:
                logger.warning(f"[MT5-Mac] Error fetching balance: {e}")
                return 0.0

        try:
            return await asyncio.to_thread(_balance)
        except Exception:
            return 0.0

    async def buy(self, asset: str, amount: float, duration: Optional[int] = None) -> Any:
        return await self.buy_market(asset, volume=amount)

    async def sell(self, asset: str, amount: float, duration: Optional[int] = None) -> Any:
        return await self.sell_market(asset, volume=amount)

    async def close(self):
        if self.mt5 and hasattr(self.mt5, "shutdown"):
            try:
                await asyncio.to_thread(self.mt5.shutdown)
            except Exception:
                pass
        self._connected = False

    async def get_trade_result(self, trade_id: Any) -> bool:
        if not self.mt5:
            return False

        def _check_result():
            try:
                ticket_num = int(trade_id)
            except (ValueError, TypeError):
                return False
            try:
                if hasattr(self.mt5, "history_deals_get"):
                    history = self.mt5.history_deals_get(ticket=ticket_num)
                    if history and len(history) > 0:
                        return history[0].profit > 0
                return False
            except Exception:
                return False

        try:
            return await asyncio.to_thread(_check_result)
        except Exception:
            return False

    async def get_order_status(self, trade_id: Any) -> dict:
        """Consulta si la posición de mercado sigue abierta o si cerró con ganancia/pérdida."""
        if not self.mt5 or not self._connected:
            return {"status": "unknown", "result": "unknown", "profit": 0.0}

        def _check_status():
            try:
                ticket_num = int(trade_id)
            except (ValueError, TypeError):
                return {"status": "unknown", "result": "unknown", "profit": 0.0}

            try:
                if hasattr(self.mt5, "positions_get"):
                    positions = self.mt5.positions_get(ticket=ticket_num)
                    if positions and len(positions) > 0:
                        pos = positions[0]
                        return {
                            "status": "open",
                            "result": "open",
                            "profit": float(getattr(pos, 'profit', 0.0)),
                            "current_price": float(getattr(pos, 'price_current', 0.0)),
                            "open_price": float(getattr(pos, 'price_open', 0.0))
                        }
            except Exception as e:
                logger.warning(f"[MT5-Mac] Error checking open positions: {e}")

            try:
                if hasattr(self.mt5, "history_deals_get"):
                    deals = self.mt5.history_deals_get(position=ticket_num)
                    if not deals or len(deals) == 0:
                        deals = self.mt5.history_deals_get(ticket=ticket_num)
                    if deals and len(deals) > 0:
                        total_profit = sum(float(getattr(d, 'profit', 0.0) + getattr(d, 'swap', 0.0) + getattr(d, 'commission', 0.0)) for d in deals)
                        res = "profit" if total_profit > 0 else "sl loss"
                        return {
                            "status": "closed",
                            "result": res,
                            "profit": round(total_profit, 2)
                        }
            except Exception as e:
                logger.warning(f"[MT5-Mac] Error checking history deals: {e}")

            return {"status": "open", "result": "open", "profit": 0.0}

        try:
            return await asyncio.to_thread(_check_status)
        except Exception as e:
            logger.warning(f"[MT5-Mac] Exception checking MT5 order status: {e}")
            return {"status": "open", "result": "open", "profit": 0.0}

    def _resolve_symbol(self, asset: str) -> Optional[str]:
        if not self.mt5:
            return asset
        clean = asset.replace("/", "").replace("_", "").replace("-", "").strip().upper()
        try:
            if hasattr(self.mt5, "symbol_info"):
                info = self.mt5.symbol_info(asset)
                if info:
                    if hasattr(self.mt5, "symbol_select") and not getattr(info, "visible", True):
                        self.mt5.symbol_select(asset, True)
                    return asset

                info = self.mt5.symbol_info(clean)
                if info:
                    if hasattr(self.mt5, "symbol_select") and not getattr(info, "visible", True):
                        self.mt5.symbol_select(clean, True)
                    return clean
        except Exception:
            pass
        return clean

    async def buy_market(self, symbol: str, volume: float, sl: Optional[float] = None, tp: Optional[float] = None) -> Any:
        return await self._send_order(symbol, "buy", volume, price=None, sl=sl, tp=tp)

    async def sell_market(self, symbol: str, volume: float, sl: Optional[float] = None, tp: Optional[float] = None) -> Any:
        return await self._send_order(symbol, "sell", volume, price=None, sl=sl, tp=tp)

    async def buy_limit(self, symbol: str, volume: float, price: float, sl: Optional[float] = None, tp: Optional[float] = None) -> Any:
        return await self._send_order(symbol, "buy_limit", volume, price=price, sl=sl, tp=tp)

    async def sell_limit(self, symbol: str, volume: float, price: float, sl: Optional[float] = None, tp: Optional[float] = None) -> Any:
        return await self._send_order(symbol, "sell_limit", volume, price=price, sl=sl, tp=tp)

    async def buy_stop(self, symbol: str, volume: float, price: float, sl: Optional[float] = None, tp: Optional[float] = None) -> Any:
        return await self._send_order(symbol, "buy_stop", volume, price=price, sl=sl, tp=tp)

    async def sell_stop(self, symbol: str, volume: float, price: float, sl: Optional[float] = None, tp: Optional[float] = None) -> Any:
        return await self._send_order(symbol, "sell_stop", volume, price=price, sl=sl, tp=tp)

    async def _send_order(
        self,
        symbol: str,
        order_type_str: str,
        volume: float,
        price: Optional[float] = None,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
    ) -> Any:
        if not self.mt5:
            return {"success": False, "error": "MT5 Mac not initialized"}

        resolved_sym = self._resolve_symbol(symbol) or symbol

        def _execute():
            # Standard MT5 action constants
            TRADE_ACTION_DEAL = getattr(self.mt5, "TRADE_ACTION_DEAL", 1)
            TRADE_ACTION_PENDING = getattr(self.mt5, "TRADE_ACTION_PENDING", 5)
            ORDER_TYPE_BUY = getattr(self.mt5, "ORDER_TYPE_BUY", 0)
            ORDER_TYPE_SELL = getattr(self.mt5, "ORDER_TYPE_SELL", 1)
            ORDER_TYPE_BUY_LIMIT = getattr(self.mt5, "ORDER_TYPE_BUY_LIMIT", 2)
            ORDER_TYPE_SELL_LIMIT = getattr(self.mt5, "ORDER_TYPE_SELL_LIMIT", 3)
            ORDER_TYPE_BUY_STOP = getattr(self.mt5, "ORDER_TYPE_BUY_STOP", 4)
            ORDER_TYPE_SELL_STOP = getattr(self.mt5, "ORDER_TYPE_SELL_STOP", 5)
            ORDER_TIME_GTC = getattr(self.mt5, "ORDER_TIME_GTC", 0)
            ORDER_FILLING_IOC = getattr(self.mt5, "ORDER_FILLING_IOC", 1)

            type_map = {
                "buy": (ORDER_TYPE_BUY, TRADE_ACTION_DEAL),
                "sell": (ORDER_TYPE_SELL, TRADE_ACTION_DEAL),
                "buy_limit": (ORDER_TYPE_BUY_LIMIT, TRADE_ACTION_PENDING),
                "sell_limit": (ORDER_TYPE_SELL_LIMIT, TRADE_ACTION_PENDING),
                "buy_stop": (ORDER_TYPE_BUY_STOP, TRADE_ACTION_PENDING),
                "sell_stop": (ORDER_TYPE_SELL_STOP, TRADE_ACTION_PENDING),
            }

            mt5_type, mt5_action = type_map.get(order_type_str.lower(), (ORDER_TYPE_BUY, TRADE_ACTION_DEAL))

            exec_price = price
            if exec_price is None:
                tick = self.mt5.symbol_info_tick(resolved_sym) if hasattr(self.mt5, "symbol_info_tick") else None
                if tick:
                    exec_price = tick.ask if mt5_type == ORDER_TYPE_BUY else tick.bid
                else:
                    exec_price = 0.0

            request = {
                "action": mt5_action,
                "symbol": resolved_sym,
                "volume": float(volume),
                "type": mt5_type,
                "price": float(exec_price or 0.0),
                "type_time": ORDER_TIME_GTC,
                "type_filling": ORDER_FILLING_IOC,
            }
            if sl is not None:
                request["sl"] = float(sl)
            if tp is not None:
                request["tp"] = float(tp)

            result = self.mt5.order_send(request)
            if result and getattr(result, "retcode", 0) in (10008, 10009):
                return {
                    "success": True,
                    "order_id": getattr(result, "order", getattr(result, "deal", 0)),
                    "price": getattr(result, "price", exec_price),
                    "retcode": getattr(result, "retcode", 0),
                }
            else:
                retcode = getattr(result, "retcode", -1) if result else -1
                comment = getattr(result, "comment", "Order rejected") if result else "No result from order_send"
                return {
                    "success": False,
                    "retcode": retcode,
                    "error": comment,
                }

        try:
            return await asyncio.to_thread(_execute)
        except Exception as e:
            logger.exception(f"[MT5-Mac] Exception sending order: {e}")
            return {"success": False, "error": str(e)}

    async def get_current_price(self, asset: str) -> Optional[float]:
        if not self.mt5:
            return None

        resolved = self._resolve_symbol(asset) or asset

        def _price():
            try:
                if hasattr(self.mt5, "symbol_info_tick"):
                    tick = self.mt5.symbol_info_tick(resolved)
                    if tick and (getattr(tick, "bid", 0.0) > 0 or getattr(tick, "ask", 0.0) > 0):
                        return float(tick.bid or tick.ask)

                if hasattr(self.mt5, "symbol_info"):
                    info = self.mt5.symbol_info(resolved)
                    if info and getattr(info, "bid", 0.0) > 0:
                        return float(info.bid)

                if hasattr(self.mt5, "copy_rates_from_pos"):
                    rates = self.mt5.copy_rates_from_pos(resolved, 1, 0, 1)
                    if rates is not None and len(rates) > 0:
                        return float(rates[-1]["close"])
            except Exception as e:
                logger.warning(f"[MT5-Mac] Error retrieving price for {resolved}: {e}")
            return None

        try:
            return await asyncio.to_thread(_price)
        except Exception:
            return None

__all__ = ["MetaTrader5MacBroker"]
