from datetime import datetime
from typing import Optional, Dict, Any, Union
from pydantic import BaseModel, Field
from app.domain.schemas.common import BrokerEnum, AccountModeEnum


class MT5Credentials(BaseModel):
    login: int = Field(description="MT5 Account Login Number")
    password: str = Field(description="MT5 Account Password")
    server: str = Field(description="Broker Server Name (e.g. MetaQuotes-Demo)")
    path: Optional[str] = Field(default=None, description="Path to terminal64.exe if local")
    host: Optional[str] = Field(default="127.0.0.1", description="Bridge host if running under macOS/Linux bridge")
    port: Optional[int] = Field(default=18812, description="Bridge port")


class UserPassCredentials(BaseModel):
    email: str = Field(description="Broker account login email")
    password: str = Field(description="Broker account password")
    account_mode: AccountModeEnum = Field(default=AccountModeEnum.PRACTICE)


class PocketOptionCredentials(BaseModel):
    ssid: str = Field(description="PocketOption session SSID token")


class AccountCreate(BaseModel):
    broker: BrokerEnum
    account_name: str = Field(min_length=2, max_length=100)
    account_mode: AccountModeEnum = Field(default=AccountModeEnum.PRACTICE)
    credentials: Dict[str, Any] = Field(description="Dictionary with broker-specific credentials")
    server: Optional[str] = Field(default=None)


class AccountUpdate(BaseModel):
    account_name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    account_mode: Optional[AccountModeEnum] = Field(default=None)
    credentials: Optional[Dict[str, Any]] = Field(default=None)
    is_active: Optional[bool] = Field(default=None)
    server: Optional[str] = Field(default=None)


class AccountResponse(BaseModel):
    id: int
    user_id: int
    broker: str
    account_name: str
    account_number: Optional[str] = None
    account_mode: str
    is_active: bool
    balance: float
    equity: Optional[float] = None
    currency: str
    server: Optional[str] = None
    last_connected_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class AccountConnectResponse(BaseModel):
    account_id: int
    broker: str
    connected: bool
    balance: float
    account_mode: str
    message: Optional[str] = None


class AccountBalanceResponse(BaseModel):
    account_id: int
    broker: str
    account_name: str
    balance: float
    equity: Optional[float] = None
    currency: str
    account_mode: str
    last_updated: datetime
