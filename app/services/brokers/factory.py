import asyncio
import logging
from typing import Dict, Optional, Any
from app.core.result import Result, Ok, Err
from app.core.security import cipher
from app.domain.models.account import TradingAccount
from app.services.brokers.base import IBrokerAdapter
from app.services.brokers.mt5_adapter import MT5Adapter
from app.services.brokers.iqoption_adapter import IQOptionAdapter
from app.services.brokers.quotex_adapter import QuotexAdapter
from app.services.brokers.pocketoption_adapter import PocketOptionAdapter

logger = logging.getLogger("quant_server.broker_manager")


class BrokerManager:
    """
    Thread-safe broker connection manager and factory.
    Caches active broker sessions, manages credential decryption,
    and controls per-account execution locks to prevent race conditions.
    """

    def __init__(self):
        self._adapters: Dict[int, IBrokerAdapter] = {}
        self._locks: Dict[int, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def get_lock_for_account(self, account_id: int) -> asyncio.Lock:
        async with self._global_lock:
            if account_id not in self._locks:
                self._locks[account_id] = asyncio.Lock()
            return self._locks[account_id]

    def create_adapter(self, account: TradingAccount) -> Result[IBrokerAdapter, str]:
        """
        Decrypts account credentials and instantiates the proper broker adapter.
        """
        try:
            creds = cipher.decrypt(account.encrypted_credentials)
        except Exception as e:
            return Err(f"Failed to decrypt credentials for account {account.id}: {str(e)}")

        broker_code = account.broker.lower().strip()

        try:
            if broker_code in ("mt5", "metatrader", "metatrader5"):
                login_val = creds.get("login") or account.account_number or 0
                password = creds.get("password", "")
                server = creds.get("server") or account.server or ""
                api_url = creds.get("api_url")
                path = creds.get("path")
                host = creds.get("host")
                port = creds.get("port")
                adapter = MT5Adapter(
                    login=int(login_val),
                    password=str(password),
                    server=str(server),
                    api_url=api_url,
                    path=path,
                    host=host,
                    port=port,
                )
                return Ok(adapter)

            elif broker_code == "iqoption":
                email = creds.get("email") or creds.get("login") or creds.get("username", "")
                password = creds.get("password", "")
                mode = account.account_mode or creds.get("account_mode", "PRACTICE")
                adapter = IQOptionAdapter(
                    email=email,
                    password=password,
                    account_mode=mode,
                )
                return Ok(adapter)

            elif broker_code == "quotex":
                email = creds.get("email") or creds.get("login") or creds.get("username", "")
                password = creds.get("password", "")
                mode = account.account_mode or creds.get("account_mode", "PRACTICE")
                adapter = QuotexAdapter(
                    email=email,
                    password=password,
                    account_mode=mode,
                )
                return Ok(adapter)

            elif broker_code == "pocketoption":
                ssid = creds.get("ssid", "")
                adapter = PocketOptionAdapter(ssid=ssid)
                return Ok(adapter)

            else:
                return Err(f"Unsupported broker provider: '{account.broker}'")

        except Exception as exc:
            logger.exception(f"Error instantiating adapter for account {account.id}: {exc}")
            return Err(f"Failed to instantiate broker adapter: {str(exc)}")

    async def get_or_create_adapter(self, account: TradingAccount) -> Result[IBrokerAdapter, str]:
        """
        Retrieves existing live adapter or creates and connects a new one.
        """
        lock = await self.get_lock_for_account(account.id)
        async with lock:
            if account.id in self._adapters:
                adapter = self._adapters[account.id]
                if await adapter.is_connected():
                    return Ok(adapter)

            # Create new adapter
            adapter_res = self.create_adapter(account)
            if adapter_res.is_err():
                return adapter_res

            adapter = adapter_res.unwrap()
            conn_res = await adapter.connect()
            if conn_res.is_err():
                return Err(f"Failed to connect account {account.id} ({account.broker}): {conn_res.unwrap_err()}")

            self._adapters[account.id] = adapter
            return Ok(adapter)

    async def connect_account(self, account: TradingAccount) -> Result[Dict[str, Any], str]:
        """
        Explicitly connects an account, validates balance and updates active cache.
        """
        adapter_res = await self.get_or_create_adapter(account)
        if adapter_res.is_err():
            return Err(adapter_res.unwrap_err())

        adapter = adapter_res.unwrap()
        bal_res = await adapter.get_balance()
        balance = bal_res.unwrap_or(0.0)

        return Ok({
            "account_id": account.id,
            "broker": account.broker,
            "connected": True,
            "balance": balance,
            "account_mode": account.account_mode,
        })

    async def disconnect_account(self, account_id: int) -> Result[bool, str]:
        """
        Disconnects an active adapter and removes it from cache.
        """
        lock = await self.get_lock_for_account(account_id)
        async with lock:
            if account_id in self._adapters:
                adapter = self._adapters.pop(account_id)
                await adapter.close()
                return Ok(True)
            return Ok(False)

    async def get_balance(self, account: TradingAccount) -> Result[float, str]:
        adapter_res = await self.get_or_create_adapter(account)
        if adapter_res.is_err():
            return Err(adapter_res.unwrap_err())
        return await adapter_res.unwrap().get_balance()

    async def close_all(self):
        """Closes all active broker adapters gracefully."""
        async with self._global_lock:
            for acc_id, adapter in list(self._adapters.items()):
                try:
                    await adapter.close()
                except Exception as e:
                    logger.warning(f"Error closing adapter for account {acc_id}: {e}")
            self._adapters.clear()


broker_manager = BrokerManager()
