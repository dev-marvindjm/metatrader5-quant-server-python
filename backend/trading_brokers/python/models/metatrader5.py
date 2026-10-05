import asyncio
import logging
from typing import Any, Optional

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    MT5_AVAILABLE = False

# pyrefly: ignore [missing-import]
from .base_broker import MarketBaseBroker

logger = logging.getLogger(__name__)

class MetaTrader5Broker(MarketBaseBroker):
    def __init__(self, login: int, password: str, server: str, path: Optional[str] = None):
        try:
            self.login = int(login) if login else 0
        except (ValueError, TypeError):
            self.login = 0
        self.password = str(password) if password else ""
        self.server = str(server) if server else ""
        self.path = path
        self._connected = False

    async def connect(self) -> bool:
        if not MT5_AVAILABLE or mt5 is None:
            logger.error("MetaTrader5 package is not available on this platform.")
            return False
        def _initialize_and_login():
            init_kwargs = {}
            if self.path:
                init_kwargs["path"] = self.path
            if self.login:
                init_kwargs["login"] = self.login
            if self.password:
                init_kwargs["password"] = self.password
            if self.server:
                init_kwargs["server"] = self.server

            initialized = mt5.initialize(**init_kwargs) if init_kwargs else mt5.initialize()
            if initialized:
                acc = mt5.account_info()
                if acc and (not self.login or acc.login == self.login):
                    logger.info(f"MT5 connected and logged into account {acc.login} ({acc.server})")
                    return True

            if not initialized:
                if self.path:
                    initialized = mt5.initialize(path=self.path)
                else:
                    initialized = mt5.initialize()

            if initialized and self.login and self.password:
                login_kwargs = {
                    "login": self.login,
                    "password": self.password,
                }
                if self.server:
                    login_kwargs["server"] = self.server
                
                logged_in = mt5.login(**login_kwargs)
                if logged_in:
                    acc = mt5.account_info()
                    logger.info(f"MT5 explicit login success for account {acc.login if acc else self.login}")
                    return True
                else:
                    logger.error(f"MT5 login failed, error: {mt5.last_error()}")
                    return False
            
            if not initialized:
                logger.error(f"MT5 initialize failed, error: {mt5.last_error()}")
                return False
                
            return True

        try:
            res = await asyncio.to_thread(_initialize_and_login)
            self._connected = bool(res)
            return self._connected
        except Exception as e:
            logger.exception(f"Exception connecting to MT5: {e}")
            self._connected = False
            return False

    async def is_connected(self) -> bool:
        if not MT5_AVAILABLE or mt5 is None or not self._connected:
            return False
        
        def _check():
            term = mt5.terminal_info()
            if not term or not term.connected:
                return False
            if self.login:
                acc = mt5.account_info()
                return acc is not None and acc.login == self.login
            return True

        try:
            return await asyncio.to_thread(_check)
        except Exception:
            return False

    async def get_balance(self) -> float:
        def _balance():
            acc = mt5.account_info()
            if acc:
                return float(acc.balance)
            return 0.0
            
        try:
            return await asyncio.to_thread(_balance)
        except Exception as e:
            logger.warning(f"Error fetching MT5 balance: {e}")
            return 0.0

    async def buy(self, asset: str, amount: float, duration: Optional[int] = None) -> Any:
        return await self.buy_market(asset, volume=amount)

    async def sell(self, asset: str, amount: float, duration: Optional[int] = None) -> Any:
        return await self.sell_market(asset, volume=amount)

    async def close(self):
        try:
            await asyncio.to_thread(mt5.shutdown)
        except Exception:
            pass
        self._connected = False

    async def get_trade_result(self, trade_id: Any) -> bool:
        def _check_result():
            try:
                ticket_num = int(trade_id)
            except (ValueError, TypeError):
                return False
            history = mt5.history_deals_get(ticket=ticket_num)
            if history and len(history) > 0:
                return history[0].profit > 0
            return False
            
        try:
            return await asyncio.to_thread(_check_result)
        except Exception:
            return False

    async def get_order_status(self, trade_id: Any) -> dict:
        """Consulta si la posición de mercado sigue abierta o si cerró con ganancia/pérdida."""
        if not MT5_AVAILABLE or mt5 is None or not self._connected:
            return {"status": "unknown", "result": "unknown", "profit": 0.0}

        def _check_status():
            try:
                ticket_num = int(trade_id)
            except (ValueError, TypeError):
                return {"status": "unknown", "result": "unknown", "profit": 0.0}

            try:
                positions = mt5.positions_get(ticket=ticket_num)
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
                logger.warning(f"Error checking MT5 open positions: {e}")

            try:
                deals = mt5.history_deals_get(position=ticket_num)
                if not deals or len(deals) == 0:
                    deals = mt5.history_deals_get(ticket=ticket_num)
                    
                if deals and len(deals) > 0:
                    total_profit = sum(float(getattr(d, 'profit', 0.0) + getattr(d, 'swap', 0.0) + getattr(d, 'commission', 0.0)) for d in deals)
                    res = "profit" if total_profit > 0 else "sl loss"
                    return {
                        "status": "closed",
                        "result": res,
                        "profit": round(total_profit, 2)
                    }
            except Exception as e:
                logger.warning(f"Error checking MT5 history deals: {e}")

            return {"status": "open", "result": "open", "profit": 0.0}

        try:
            return await asyncio.to_thread(_check_status)
        except Exception as e:
            logger.warning(f"Exception checking MT5 order status: {e}")
            return {"status": "open", "result": "open", "profit": 0.0}

    def _resolve_symbol(self, asset: str) -> Optional[str]:
        base, _, _ = self.parse_asset_info(asset)
        clean = base if base else asset.replace("/", "").replace("_", "").replace("-", "").strip().upper()
        
        info = mt5.symbol_info(asset)
        if info:
            if not info.visible:
                mt5.symbol_select(asset, True)
            return asset
            
        info = mt5.symbol_info(clean)
        if info:
            if not info.visible:
                mt5.symbol_select(clean, True)
            return clean

        symbols = mt5.symbols_get()
        if symbols:
            # 1. Look for exact clean match
            for s in symbols:
                s_clean = s.name.replace(".", "").replace("_", "").replace("-", "").strip().upper()
                if s.name == clean or s_clean == clean:
                    if not s.visible:
                        mt5.symbol_select(s.name, True)
                    return s.name

            # 2. Look for broker suffix match (e.g. EURUSDm, EURUSD.pro, EURUSD_i)
            for s in symbols:
                s_clean = s.name.replace(".", "").replace("_", "").replace("-", "").strip().upper()
                if s_clean.startswith(clean) and len(s_clean) - len(clean) <= 5:
                    if not s.visible:
                        mt5.symbol_select(s.name, True)
                    return s.name
        return None

    async def verify_and_resolve_symbol(self, asset: str) -> tuple[Optional[str], Optional[str]]:
        if not asset:
            return None, "Asset is empty"

        base, _, _ = self.parse_asset_info(asset)
        if not base:
            return None, f"Invalid symbol '{asset}'"

        if not MT5_AVAILABLE or mt5 is None or not self._connected:
            return base, None

        def _resolve():
            return self._resolve_symbol(asset)

        try:
            resolved = await asyncio.to_thread(_resolve)
            if resolved:
                return resolved, None
            return None, f"Symbol '{asset}' (clean: '{base}') not found in MetaTrader 5 market watch"
        except Exception as e:
            return None, f"MT5 symbol resolution error: {str(e)}"

    async def get_current_price(self, asset: str) -> Optional[float]:
        def _get_tick():
            symbol = self._resolve_symbol(asset)
            if not symbol:
                logger.warning(f"Símbolo {asset} no encontrado en MT5.")
                return None
                
            tick = mt5.symbol_info_tick(symbol)
            if tick is not None:
                if hasattr(tick, 'last') and tick.last > 0:
                    return float(tick.last)
                if hasattr(tick, 'ask') and hasattr(tick, 'bid') and tick.ask > 0 and tick.bid > 0:
                    return float((tick.ask + tick.bid) / 2.0)
                if hasattr(tick, 'bid') and tick.bid > 0:
                    return float(tick.bid)
                if hasattr(tick, 'ask') and tick.ask > 0:
                    return float(tick.ask)
            
            # Fallback: consultar última barra de 1 minuto si el tick es 0 o no ha transmitido aún
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 1)
            if rates is not None and len(rates) > 0:
                try:
                    close_p = rates[0]['close']
                    return float(close_p)
                except Exception:
                    try:
                        return float(rates[0][4])
                    except Exception:
                        pass
            return None
            
        try:
            return await asyncio.to_thread(_get_tick)
        except Exception as e:
            logger.warning(f"Error fetching MT5 price for {asset}: {e}")
            return None

    # Implementación de MarketBaseBroker
    
    async def buy_market(self, symbol: str, volume: float, sl: Optional[float] = None, tp: Optional[float] = None) -> Any:
        return await self._execute_order(symbol, mt5.ORDER_TYPE_BUY, volume, sl=sl, tp=tp)

    async def sell_market(self, symbol: str, volume: float, sl: Optional[float] = None, tp: Optional[float] = None) -> Any:
        return await self._execute_order(symbol, mt5.ORDER_TYPE_SELL, volume, sl=sl, tp=tp)

    async def buy_limit(self, symbol: str, volume: float, price: float, sl: Optional[float] = None, tp: Optional[float] = None) -> Any:
        return await self._execute_order(symbol, mt5.ORDER_TYPE_BUY_LIMIT, volume, price=price, sl=sl, tp=tp)

    async def sell_limit(self, symbol: str, volume: float, price: float, sl: Optional[float] = None, tp: Optional[float] = None) -> Any:
        return await self._execute_order(symbol, mt5.ORDER_TYPE_SELL_LIMIT, volume, price=price, sl=sl, tp=tp)

    async def buy_stop(self, symbol: str, volume: float, price: float, sl: Optional[float] = None, tp: Optional[float] = None) -> Any:
        return await self._execute_order(symbol, mt5.ORDER_TYPE_BUY_STOP, volume, price=price, sl=sl, tp=tp)

    async def sell_stop(self, symbol: str, volume: float, price: float, sl: Optional[float] = None, tp: Optional[float] = None) -> Any:
        return await self._execute_order(symbol, mt5.ORDER_TYPE_SELL_STOP, volume, price=price, sl=sl, tp=tp)

    async def _execute_order(self, symbol: str, order_type: int, volume: float, price: Optional[float] = None, sl: Optional[float] = None, tp: Optional[float] = None) -> Any:
        def _send_request():
            resolved_symbol = self._resolve_symbol(symbol)
            if not resolved_symbol:
                logger.error(f"Símbolo {symbol} no encontrado en terminal MT5.")
                return None

            symbol_info = mt5.symbol_info(resolved_symbol)
            if symbol_info is None:
                logger.error(f"No se pudo obtener información del símbolo {resolved_symbol}.")
                return None
            
            if not symbol_info.visible:
                if not mt5.symbol_select(resolved_symbol, True):
                    logger.error(f"Fallo al seleccionar símbolo {resolved_symbol}.")
                    return None

            if price is None:
                tick = mt5.symbol_info_tick(resolved_symbol)
                if tick is None:
                    logger.error(f"No se pudo obtener tick para {resolved_symbol}.")
                    return None
                if order_type in [mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_BUY_STOP]:
                    exec_price = tick.ask
                else:
                    exec_price = tick.bid
            else:
                exec_price = price

            is_pending = order_type in [
                mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_SELL_LIMIT,
                mt5.ORDER_TYPE_BUY_STOP, mt5.ORDER_TYPE_SELL_STOP
            ]
            
            action = mt5.TRADE_ACTION_PENDING if is_pending else mt5.TRADE_ACTION_DEAL

            request = {
                "action": action,
                "symbol": resolved_symbol,
                "volume": float(volume),
                "type": order_type,
                "price": float(exec_price),
                "magic": 234000,
                "comment": "Antigravity Bot Order",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            if sl is not None:
                request["sl"] = float(sl)
            if tp is not None:
                request["tp"] = float(tp)

            result = mt5.order_send(request)
            if result is None:
                logger.error(f"order_send retornó None para {resolved_symbol}, error: {mt5.last_error()}")
                return None
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                logger.error(f"order_send falló para {resolved_symbol}, retcode={result.retcode} ({result.comment})")
                return None
                
            return result.order

        return await asyncio.to_thread(_send_request)

__all__ = ["MetaTrader5Broker"]
