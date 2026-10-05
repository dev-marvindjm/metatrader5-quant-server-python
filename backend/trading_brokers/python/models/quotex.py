import asyncio
import logging
from typing import Any, Optional
# pyrefly: ignore [missing-import]
from .base_broker import BaseBroker

logger = logging.getLogger(__name__)

try:
    from pyquotex.stable_api import Quotex
    QUOTEX_AVAILABLE = True
except ImportError:
    Quotex = None
    QUOTEX_AVAILABLE = False

def _patch_pyquotex_for_macos():
    """Patches pyquotex on macOS to use safari impersonation, bypassing Cloudflare Turnstile bot blocks."""
    import platform
    if platform.system() != "Darwin":
        return
    try:
        import pyquotex.network.navigator as nav
        import pyquotex.network.login as login_mod
        # pyrefly: ignore [missing-import]
        from curl_cffi.requests import AsyncSession

        nav.USER_AGENT_DEFAULT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"

        orig_ensure_client = nav.Browser.ensure_client
        async def patched_ensure_client(self):
            if self._client is None or getattr(self._client, "_closed", False) is True or getattr(self._client, "is_closed", False) is True:
                client_kwargs = {
                    "headers": self.headers,
                    "timeout": 30.0,
                    "allow_redirects": True,
                    "impersonate": "safari17_0",
                }
                if self.proxies:
                    client_kwargs["proxies"] = {"http": self.proxies, "https": self.proxies} if isinstance(self.proxies, str) else self.proxies
                cookie_header = self.headers.get("Cookie")
                if cookie_header:
                    cookies_dict = {}
                    for item in cookie_header.split(";"):
                        if "=" in item:
                            k, v = item.strip().split("=", 1)
                            if k.strip():
                                cookies_dict[k.strip()] = v.strip()
                    client_kwargs["cookies"] = cookies_dict
                self._client = AsyncSession(**client_kwargs)
            return self._client

        nav.Browser.ensure_client = patched_ensure_client

        async def patched_post(self, data):
            post_headers = {
                "Referer": f"{self.full_url}/sign-in/modal/",
                "Origin": self.https_base_url,
            }
            self.response = await self.send_request(
                method="POST",
                url=f"{self.full_url}/sign-in/",
                data=data,
                headers=post_headers
            )
            required_keep_code = self.get_soup().find("input", {"name": "keep_code"})
            if required_keep_code:
                auth_body = self.get_soup().find("main", {"class": "auth__body"})
                input_message = (
                    f'{auth_body.find("p").text}: '
                    if auth_body and auth_body.find("p")
                    else "Insira o código PIN que acabamos de enviar para o seu e-mail: "
                )
                await self.awaiting_pin(data, input_message)
            from pyquotex._api._waits import backoff_sleep
            await backoff_sleep(0)
            return await self.success_login()

        login_mod.Login._post = patched_post
    except Exception as e:
        logger.warning(f"Could not apply macOS patch to pyquotex: {e}")

if QUOTEX_AVAILABLE:
    _patch_pyquotex_for_macos()

class QuotexBroker(BaseBroker):
    def __init__(self, email: str, password: str, account_mode: str = "PRACTICE"):
        self.email = email.lower().strip() if email else ""
        self.password = password
        self.account_mode = account_mode
        self._http_authenticated = False
        self._cached_balance = 0.0
        if QUOTEX_AVAILABLE and Quotex:
            self.client = Quotex(email=self.email, password=self.password)
            self.client.debug_ws_enable = False
        else:
            self.client = None

    async def connect(self) -> bool:
        if not QUOTEX_AVAILABLE or self.client is None:
            logger.error("pyquotex package is not installed.")
            return False
        try:
            # 1. Intentar conexión estándar por WebSocket
            res = await self.client.connect()
            connected = res[0] if isinstance(res, tuple) else bool(res)
            
            if connected:
                self.client.set_account_mode(self.account_mode)
                return True

            # 2. Si falló, reintentar autenticación HTTPS limpia
            logger.info("Primer intento de conexión a Quotex falló, reintentando autenticación HTTPS...")
            if self.client.api:
                self.client.api.session_data["token"] = None
                auth_ok, auth_msg = await self.client.api.authenticate()
                if auth_ok:
                    self._http_authenticated = True
                    try:
                        res = await self.client.connect()
                        connected = res[0] if isinstance(res, tuple) else bool(res)
                        if connected:
                            self.client.set_account_mode(self.account_mode)
                            return True
                    except Exception:
                        pass

                    try:
                        async with self.client.api.login as login:
                            prof_res = await login.get_profile()
                            if prof_res.is_success:
                                data = prof_res.json().get("data", {})
                                is_demo = self.account_mode.upper() == "PRACTICE"
                                self._cached_balance = float(data.get("demoBalance" if is_demo else "liveBalance", 0.0))
                                logger.info(f"Quotex autenticado por HTTP REST (Balance: ${self._cached_balance:.2f})")
                                return True
                    except Exception as pe:
                        logger.warning(f"Error leyendo perfil Quotex vía HTTP: {pe}")

                    return True

            is_conn = await self.is_connected()
            if is_conn:
                self.client.set_account_mode(self.account_mode)
                return True
            return False
        except Exception as e:
            logger.error(f"Quotex connect error: {e}")
            return False

    async def is_connected(self) -> bool:
        if not QUOTEX_AVAILABLE or self.client is None:
            return False
        try:
            if await self.client.check_connect():
                return True
        except Exception:
            pass
        return self._http_authenticated or bool(
            self.client.api and self.client.api.session_data and self.client.api.session_data.get("token")
        )

    async def get_balance(self) -> float:
        if not QUOTEX_AVAILABLE or self.client is None:
            return 0.0
        try:
            if await self.client.check_connect():
                bal = await self.client.get_balance()
                if bal > 0:
                    self._cached_balance = bal
                    return bal
        except Exception:
            pass

        if self.client.api:
            try:
                async with self.client.api.login as login:
                    prof_res = await login.get_profile()
                    if prof_res.is_success:
                        data = prof_res.json().get("data", {})
                        is_demo = self.account_mode.upper() == "PRACTICE"
                        bal = float(data.get("demoBalance" if is_demo else "liveBalance", 0.0))
                        self._cached_balance = bal
                        return bal
            except Exception as pe:
                logger.warning(f"Error consultando balance HTTP Quotex: {pe}")

        return self._cached_balance

    async def verify_and_resolve_symbol(self, asset: str) -> tuple[Optional[str], Optional[str]]:
        if not asset:
            return None, "Asset is empty"

        base, is_otc, _ = self.parse_asset_info(asset)
        if not base:
            return None, f"Invalid symbol '{asset}'"

        target_symbol = f"{base}_otc" if is_otc else base

        if QUOTEX_AVAILABLE and self.client is not None:
            try:
                instruments = await self.client.get_instruments()
                if instruments and isinstance(instruments, list):
                    symbol_status = {}
                    for inst in instruments:
                        if len(inst) > 14:
                            sym = inst[1]
                            is_open = bool(inst[14])
                            symbol_status[sym.lower()] = (sym, is_open)

                    target_lower = target_symbol.lower()
                    otc_lower = f"{base}_otc".lower()
                    std_lower = base.lower()

                    # 1. Si se pidió OTC
                    if is_otc:
                        if otc_lower in symbol_status and symbol_status[otc_lower][1]:
                            return symbol_status[otc_lower][0], None
                        if std_lower in symbol_status and symbol_status[std_lower][1]:
                            logger.info(f"Quotex: OTC {target_symbol} is closed, switching to open standard {symbol_status[std_lower][0]}")
                            return symbol_status[std_lower][0], None

                    # 2. Si se pidió estándar
                    else:
                        if std_lower in symbol_status and symbol_status[std_lower][1]:
                            return symbol_status[std_lower][0], None
                        if otc_lower in symbol_status and symbol_status[otc_lower][1]:
                            logger.info(f"Quotex: Standard {base} is closed, switching to open OTC variant {symbol_status[otc_lower][0]}")
                            return symbol_status[otc_lower][0], None

                    # 3. Si existe aunque figure cerrado, usar el símbolo con su casing exacto
                    if target_lower in symbol_status:
                        return symbol_status[target_lower][0], None
                    if otc_lower in symbol_status:
                        return symbol_status[otc_lower][0], None

                    matching = [s for s in symbol_status.keys() if base[:3].lower() in s]
                    return None, f"Symbol '{asset}' (resolved: '{target_symbol}') not found in Quotex active assets. Close matches: {matching[:5]}"
            except Exception as e:
                logger.debug(f"Quotex instruments check error: {e}")

        return target_symbol, None

    async def buy(self, asset: str, amount: float, duration: int) -> Any:
        if not QUOTEX_AVAILABLE or self.client is None:
            return None
        resolved, err = await self.verify_and_resolve_symbol(asset)
        if not resolved:
            logger.error(f"Quotex buy aborted: {err}")
            return None
        try:
            res = await self.client.buy(amount, resolved, "call", int(duration))
            if isinstance(res, tuple):
                success, trade_info = res
                if success:
                    if isinstance(trade_info, dict):
                        return str(trade_info.get("id") or trade_info.get("ticket") or "")
                    return str(trade_info)
                else:
                    logger.error(f"Quotex buy failed: {trade_info}")
                    return None
            elif res:
                return str(res)
            return None
        except Exception as e:
            logger.error(f"Quotex buy exception: {e}")
            return None

    async def sell(self, asset: str, amount: float, duration: int) -> Any:
        if not QUOTEX_AVAILABLE or self.client is None:
            return None
        resolved, err = await self.verify_and_resolve_symbol(asset)
        if not resolved:
            logger.error(f"Quotex sell aborted: {err}")
            return None
        try:
            res = await self.client.buy(amount, resolved, "put", int(duration))
            if isinstance(res, tuple):
                success, trade_info = res
                if success:
                    if isinstance(trade_info, dict):
                        return str(trade_info.get("id") or trade_info.get("ticket") or "")
                    return str(trade_info)
                else:
                    logger.error(f"Quotex sell failed: {trade_info}")
                    return None
            elif res:
                return str(res)
            return None
        except Exception as e:
            logger.error(f"Quotex sell exception: {e}")
            return None

    async def close(self):
        if QUOTEX_AVAILABLE and self.client is not None:
            try:
                await self.client.close()
            except Exception:
                pass

    async def get_trade_result(self, trade_id: Any) -> bool:
        if not QUOTEX_AVAILABLE or self.client is None:
            return False
        try:
            if isinstance(trade_id, (tuple, list)):
                trade_id = trade_id[1] if len(trade_id) > 1 else trade_id[0]
            if isinstance(trade_id, dict):
                trade_id = trade_id.get("id") or trade_id.get("ticket")
            clean_id = str(trade_id).strip()
            result = await self.client.check_win(clean_id)
            if isinstance(result, bool):
                return result
            if isinstance(result, tuple) and len(result) >= 1:
                return result[0] == "win"
            if isinstance(result, dict):
                return result.get("result") == "win" or result.get("win", False)
        except Exception as e:
            logger.warning(f"Error checking Quotex trade result: {e}")
        return False

    async def get_current_price(self, asset: str) -> Optional[float]:
        if not QUOTEX_AVAILABLE or self.client is None:
            return None
        resolved, err = await self.verify_and_resolve_symbol(asset)
        target = resolved or asset
        try:
            prices = await self.client.get_realtime_price(target)
            if prices and len(prices) > 0:
                last_p = prices[-1].get("price")
                if last_p is not None:
                    return float(last_p)
            
            import time
            candles = await self.client.get_candles(target, time.time(), 10, 60, timeout=10)
            if candles and len(candles) > 0:
                last_candle = candles[-1]
                close_p = last_candle.get("close")
                if close_p is not None:
                    return float(close_p)
        except Exception as e:
            logger.warning(f"Error fetching Quotex price for {target}: {e}")
        return None

__all__ = ["QuotexBroker"]
