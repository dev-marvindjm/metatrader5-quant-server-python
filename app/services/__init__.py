"""
Services Package with lazy loading to avoid eager import cycles and unnecessary overhead.
"""


def __getattr__(name: str):
    if name in ("BrokerManager", "broker_manager"):
        from app.services.brokers.factory import BrokerManager, broker_manager
        return BrokerManager if name == "BrokerManager" else broker_manager
    if name in ("ExecutionEngine", "execution_engine"):
        from app.services.execution_engine import ExecutionEngine, execution_engine
        return ExecutionEngine if name == "ExecutionEngine" else execution_engine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "BrokerManager",
    "broker_manager",
    "ExecutionEngine",
    "execution_engine",
]
