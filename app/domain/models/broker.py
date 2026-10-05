from typing import Optional
from sqlmodel import SQLModel, Field


class BrokerCatalog(SQLModel, table=True):
    __tablename__ = "broker_catalog"

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(unique=True, index=True, description="mt5 | iqoption | quotex | pocketoption")
    name: str = Field(description="Display name of the broker")
    market_types: str = Field(description="Comma-separated: FOREX,CFD,CRYPTO or BINARY_OPTIONS")
    supports_demo: bool = Field(default=True)
    supports_real: bool = Field(default=True)
    is_active: bool = Field(default=True)
    notes: Optional[str] = Field(default=None)
