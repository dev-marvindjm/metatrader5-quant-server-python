import asyncio
import logging
from typing import Any, Optional
# pyrefly: ignore [missing-import]
from .base_broker import BaseBroker

logger = logging.getLogger(__name__)

try:
    from iqoption_async.client import IQOptionClient as Client
    from iqoption_async.constants import ACTIVES
    IQOPTION_AVAILABLE = True
    IQOPTION_IMPORT_ERROR = None
except ImportError as e:
    Client = None
    ACTIVES = {}
    IQOPTION_AVAILABLE = False
    IQOPTION_IMPORT_ERROR = str(e)

class IQOptionBroker(BaseBroker):
    def __init__(self, email: str, password: str, account_mode: str = "PRACTICE"):
        self.email = email.lower().strip() if email else ""
        self.password = password
        self.account_mode = account_mode
        self.client = Client(email=self.email, password=self.password) if IQOPTION_AVAILABLE and Client else None

    async def connect(self) -> bool:
        """Conecta al broker de IQ Option y establece el modo de cuenta (PRACTICE/REAL)."""
        if not IQOPTION_AVAILABLE or self.client is None:
            logger.error(f"iqoption_async import error: {IQOPTION_IMPORT_ERROR}")
            raise ImportError(IQOPTION_IMPORT_ERROR or "iqoption_async")
        try:
            connected, reason = await self.client.connect()
            if not connected:
                logger.error(f"IQOption connection failed: {reason}")
                return False

            is_conn = await self.is_connected()
            if is_conn:
                try:
                    await self.client.change_balance(self.account_mode)
                except Exception as b_err:
                    logger.warning(f"IQOption change_balance notice: {b_err}")
                return True
            return False
        except Exception as e:
            logger.error(f"IQOption connect error: {e}")
            return False

    async def is_connected(self) -> bool:
        if not IQOPTION_AVAILABLE or self.client is None:
            return False
        try:
            return await self.client.check_connect()
        except Exception:
            return False

    async def get_balance(self) -> float:
        if not IQOPTION_AVAILABLE or self.client is None:
            return 0.0
        try:
            return await self.client.get_balance()
        except Exception:
            return 0.0

    async def verify_and_resolve_symbol(self, asset: str) -> tuple[Optional[str], Optional[str]]:
        """
        Normaliza y valida el símbolo en IQ Option.
        Soporta formato ordinario (EURUSD) y formato OTC (EURUSD-OTC con guion medio).
        Si el activo normal está cerrado, verifica si la variante OTC está abierta.
        """
        if not asset:
            return None, "Asset is empty"

        base, is_otc, _ = self.parse_asset_info(asset)
        if not base:
            return None, f"Invalid symbol '{asset}'"

        target_symbol = f"{base}-OTC" if is_otc else base

        if not IQOPTION_AVAILABLE or self.client is None or not ACTIVES:
            return target_symbol, None

        # 1. Verificar si target_symbol está directamente en ACTIVES
        if target_symbol in ACTIVES:
            if not is_otc:
                otc_variant = f"{base}-OTC"
                if self._check_asset_open(target_symbol):
                    return target_symbol, None
                elif otc_variant in ACTIVES and self._check_asset_open(otc_variant):
                    logger.info(f"IQOption: Standard {base} is closed, switching to open OTC variant {otc_variant}")
                    return otc_variant, None
            return target_symbol, None

        # 2. Búsqueda insensible a mayúsculas en ACTIVES
        for act in ACTIVES.keys():
            if act.upper() == target_symbol.upper():
                return act, None

        # 3. Si era estándar pero no está en ACTIVES, intentar OTC
        if not is_otc:
            otc_cand = f"{base}-OTC"
            for act in ACTIVES.keys():
                if act.upper() == otc_cand.upper():
                    return act, None

        # 4. Si era OTC con otra puntuación, intentar encontrar equivalente
        hyphen_cand = asset.upper().replace("_OTC", "-OTC").replace("/OTC", "-OTC").replace(" (OTC)", "-OTC")
        for act in ACTIVES.keys():
            if act.upper() == hyphen_cand:
                return act, None

        return None, f"Symbol '{asset}' not found in IQ Option active assets"

    def _check_asset_open(self, asset_name: str) -> bool:
        """Verifica si el activo está habilitado en OPEN_TIME."""
        if not hasattr(self.client, 'OPEN_TIME') or not self.client.OPEN_TIME:
            return True
        for opt in ["turbo", "binary"]:
            if opt in self.client.OPEN_TIME and asset_name in self.client.OPEN_TIME[opt]:
                return bool(self.client.OPEN_TIME[opt][asset_name].get("open", False))
        return False

    def _convert_duration_to_minutes(self, duration: int) -> int:
        """IQ Option espera expiración en MINUTOS (1-5 para turbo). Convierte segundos a minutos."""
        dur_int = int(duration)
        if dur_int >= 60:
            return max(1, round(dur_int / 60))
        return max(1, dur_int)

    async def buy(self, asset: str, amount: float, duration: int) -> Any:
        if not IQOPTION_AVAILABLE or self.client is None:
            return None
        resolved, err = await self.verify_and_resolve_symbol(asset)
        if not resolved:
            logger.error(f"IQOption buy aborted: {err}")
            return None

        exp_minutes = self._convert_duration_to_minutes(duration)
        try:
            res = await self.client.buy(amount, resolved, "call", exp_minutes)
            if isinstance(res, tuple):
                success = res[0]
                if success is True and len(res) >= 2 and res[1] is not None:
                    return str(res[1])
                err_msg = res[1] if len(res) >= 2 else "Unknown error"
                logger.error(f"IQOption buy failed: {err_msg}")
                return None
            elif res:
                return str(res)
            return None
        except Exception as e:
            logger.error(f"IQOption buy exception: {e}")
            return None

    async def sell(self, asset: str, amount: float, duration: int) -> Any:
        if not IQOPTION_AVAILABLE or self.client is None:
            return None
        resolved, err = await self.verify_and_resolve_symbol(asset)
        if not resolved:
            logger.error(f"IQOption sell aborted: {err}")
            return None

        exp_minutes = self._convert_duration_to_minutes(duration)
        try:
            res = await self.client.buy(amount, resolved, "put", exp_minutes)
            if isinstance(res, tuple):
                success = res[0]
                if success is True and len(res) >= 2 and res[1] is not None:
                    return str(res[1])
                err_msg = res[1] if len(res) >= 2 else "Unknown error"
                logger.error(f"IQOption sell failed: {err_msg}")
                return None
            elif res:
                return str(res)
            return None
        except Exception as e:
            logger.error(f"IQOption sell exception: {e}")
            return None

    async def close(self):
        if IQOPTION_AVAILABLE and self.client is not None:
            try:
                if hasattr(self.client, 'close'):
                    res = self.client.close()
                    if asyncio.iscoroutine(res):
                        await res
                elif hasattr(self.client, 'disconnect'):
                    res = self.client.disconnect()
                    if asyncio.iscoroutine(res):
                        await res
            except Exception:
                pass

    async def get_trade_result(self, trade_id: Any) -> bool:
        if not IQOPTION_AVAILABLE or self.client is None:
            return False
        try:
            if isinstance(trade_id, (tuple, list)):
                trade_id = trade_id[1] if len(trade_id) > 1 else trade_id[0]
            clean_id = int(str(trade_id).strip())
            result = await self.client.check_order(clean_id)
            if isinstance(result, bool):
                return result
            if isinstance(result, dict):
                return result.get("result") == "win" or result.get("win", False)
        except Exception as e:
            logger.warning(f"Error checking IQOption trade result: {e}")
        return False

    async def get_current_price(self, asset: str) -> Optional[float]:
        if not IQOPTION_AVAILABLE or self.client is None:
            return None
        import time
        resolved, _ = await self.verify_and_resolve_symbol(asset)
        target = resolved or asset
        try:
            candles = await self.client.get_candles(target, 1, 1, time.time())
            if candles and isinstance(candles, list) and len(candles) > 0:
                last_candle = candles[-1]
                close_p = last_candle.get("close") or last_candle.get("open")
                if close_p is not None:
                    return float(close_p)
        except Exception as e:
            logger.warning(f"Error fetching IQOption price for {target}: {e}")
        return None

__all__ = ["IQOptionBroker"]
