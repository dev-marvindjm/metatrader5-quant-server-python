"""
Broker adapters package with lazy loading.
"""
from app.services.brokers.base import IBrokerAdapter, IBinaryBrokerAdapter, IMarketBrokerAdapter


def __getattr__(name: str):
    if name == "MT5Adapter":
        from app.services.brokers.mt5_adapter import MT5Adapter
        return MT5Adapter
    elif name == "IQOptionAdapter":
        from app.services.brokers.iqoption_adapter import IQOptionAdapter
        return IQOptionAdapter
    elif name == "QuotexAdapter":
        from app.services.brokers.quotex_adapter import QuotexAdapter
        return QuotexAdapter
    elif name == "PocketOptionAdapter":
        from app.services.brokers.pocketoption_adapter import PocketOptionAdapter
        return PocketOptionAdapter
    elif name in ("BrokerManager", "broker_manager"):
        from app.services.brokers.factory import BrokerManager, broker_manager
        return BrokerManager if name == "BrokerManager" else broker_manager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "IBrokerAdapter",
    "IBinaryBrokerAdapter",
    "IMarketBrokerAdapter",
    "MT5Adapter",
    "IQOptionAdapter",
    "QuotexAdapter",
    "PocketOptionAdapter",
    "BrokerManager",
    "broker_manager",
]
