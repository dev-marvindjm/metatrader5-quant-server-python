from typing import Optional
from pydantic import BaseModel


class BrokerInfoResponse(BaseModel):
    id: int
    code: str
    name: str
    market_types: str
    supports_demo: bool
    supports_real: bool
    is_active: bool
    notes: Optional[str] = None
