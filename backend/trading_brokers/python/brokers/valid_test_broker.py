from models.base_broker import BaseBroker
import asyncio

class ValidTestBroker(BaseBroker):
    def __init__(self, username=None, password=None, account_mode="PRACTICE"):
        self.username = username
        self.password = password
        self.account_mode = account_mode
        self._connected = False
        
    async def connect(self) -> bool:
        self._connected = True
        return True
        
    async def is_connected(self) -> bool:
        return self._connected
        
    async def get_balance(self) -> float:
        return 1234.56
        
    async def buy(self, asset: str, amount: float, duration: int):
        return "trade_12345"
        
    async def sell(self, asset: str, amount: float, duration: int):
        return "trade_12345"
        
    async def close(self):
        self._connected = False
        
    async def get_trade_result(self, trade_id) -> bool:
        return True
