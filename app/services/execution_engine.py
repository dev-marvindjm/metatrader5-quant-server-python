import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from app.core.result import Result, Ok, Err
from app.core.exceptions import AccountNotFoundError, AccountInactiveError, BrokerExecutionError
from app.domain.enums import TradeOutcome
from app.domain.models.account import TradingAccount
from app.domain.models.order import OrderExecution
from app.domain.models.signal import TradingSignal
from app.domain.schemas.order import BinaryOrderCreate, MarketOrderCreate
from app.domain.schemas.signal import SignalCreate, SignalExecuteRequest, SignalExecutionSummary
from app.services.brokers.factory import broker_manager
from app.services.brokers.base import IBinaryBrokerAdapter, IMarketBrokerAdapter
from app.services.progress_evaluator import evaluate_trade_progress, TradeSettledPayload

logger = logging.getLogger("quant_server.execution_engine")


class ExecutionEngine:
    """
    Core quant execution engine.
    Orchestrates order routing, latency measurement, state persistence,
    account balance synchronisation and audit logs.
    """

    def __init__(self, manager=broker_manager):
        self.manager = manager

    async def _get_validated_account(self, account_id: int, db: AsyncSession) -> TradingAccount:
        result = await db.exec(select(TradingAccount).where(TradingAccount.id == account_id))
        account = result.first()
        if not account:
            raise AccountNotFoundError(account_id)
        if not account.is_active:
            raise AccountInactiveError(account_id)
        return account

    async def execute_binary_order(
        self,
        order_in: BinaryOrderCreate,
        db: AsyncSession,
        signal_id: Optional[int] = None,
    ) -> Result[OrderExecution, str]:
        account = await self._get_validated_account(order_in.account_id, db)
        adapter_res = await self.manager.get_or_create_adapter(account)
        if adapter_res.is_err():
            return Err(adapter_res.unwrap_err())

        adapter = adapter_res.unwrap()
        if not isinstance(adapter, IBinaryBrokerAdapter):
            return Err(f"Broker '{account.broker}' does not support binary options execution.")

        # Create persistent audit record in DB
        db_order = OrderExecution(
            user_id=account.user_id,
            account_id=account.id,
            signal_id=signal_id,
            broker=account.broker,
            symbol=adapter.format_broker_asset(order_in.symbol, account.broker),
            raw_symbol=order_in.symbol,
            action=order_in.action.value,
            order_type="BINARY",
            amount=order_in.amount,
            duration_seconds=order_in.duration_seconds,
            gale_step=0,
            status="PENDING",
        )
        db.add(db_order)
        await db.commit()
        await db.refresh(db_order)

        start_time = time.perf_counter()

        try:
            # Query current price for audit
            price_res = await adapter.get_current_price(order_in.symbol)
            if price_res.is_ok():
                db_order.entry_price = price_res.unwrap()

            # Execute trade or martingale
            if order_in.gale_steps > 0:
                trade_res = await adapter.execute_martingale(
                    action=order_in.action.value,
                    symbol=order_in.symbol,
                    amount=order_in.amount,
                    duration=order_in.duration_seconds,
                    steps=order_in.gale_steps,
                    multiplier=order_in.gale_multiplier,
                )
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                db_order.latency_ms = latency_ms

                if trade_res.is_ok():
                    m_data = trade_res.unwrap()
                    db_order.broker_order_id = str(m_data.get("trade_id"))
                    db_order.gale_step = m_data.get("step_won", 0) or 0
                    db_order.executed_amount = m_data.get("final_amount")
                    db_order.status = "WON" if m_data.get("won") else "LOST"
                    db_order.closed_at = datetime.now(timezone.utc)
                else:
                    db_order.status = "FAILED"
                    db_order.error_log = trade_res.unwrap_err()
            else:
                if order_in.action.value in ("BUY", "CALL", "UP"):
                    trade_res = await adapter.buy(order_in.symbol, order_in.amount, order_in.duration_seconds)
                else:
                    trade_res = await adapter.sell(order_in.symbol, order_in.amount, order_in.duration_seconds)

                latency_ms = int((time.perf_counter() - start_time) * 1000)
                db_order.latency_ms = latency_ms

                if trade_res.is_ok():
                    trade_id = trade_res.unwrap()
                    db_order.broker_order_id = str(trade_id)
                    db_order.status = "SUBMITTED"
                    db_order.executed_amount = order_in.amount
                else:
                    db_order.status = "REJECTED"
                    db_order.error_log = trade_res.unwrap_err()

            # Sync balance
            bal_res = await adapter.get_balance()
            if bal_res.is_ok():
                account.balance = bal_res.unwrap()
                account.last_connected_at = datetime.now(timezone.utc)
                db.add(account)

            if db_order.status in ("WON", "LOST"):
                pnl = (float(db_order.executed_amount or order_in.amount) * 0.85) if db_order.status == "WON" else -float(db_order.executed_amount or order_in.amount)
                db_order.profit_loss = pnl
                db.add(db_order)
                await db.commit()
                try:
                    await evaluate_trade_progress(
                        TradeSettledPayload(
                            order_id=db_order.id,
                            user_id=db_order.user_id,
                            broker=db_order.broker,
                            symbol=db_order.symbol,
                            broker_ticket=db_order.broker_order_id,
                            sender_id=db_order.sender_id,
                            template_id=db_order.template_id,
                            profit_loss=pnl,
                            action=db_order.action,
                            outcome=TradeOutcome.WIN if db_order.status == "WON" else TradeOutcome.LOSS,
                        ),
                        db,
                    )
                except Exception as eval_err:
                    logger.error(f"Error evaluating trade progress for order {db_order.id}: {eval_err}")

            if db_order.status in ("REJECTED", "FAILED"):
                return Err(db_order.error_log or "Binary trade execution failed.")
            return Ok(db_order)

        except Exception as ex:
            db_order.status = "FAILED"
            db_order.error_log = str(ex)
            db_order.latency_ms = int((time.perf_counter() - start_time) * 1000)
            db.add(db_order)
            await db.commit()
            return Err(f"Execution exception: {str(ex)}")

    async def execute_market_order(
        self,
        order_in: MarketOrderCreate,
        db: AsyncSession,
        signal_id: Optional[int] = None,
    ) -> Result[OrderExecution, str]:
        account = await self._get_validated_account(order_in.account_id, db)
        adapter_res = await self.manager.get_or_create_adapter(account)
        if adapter_res.is_err():
            return Err(adapter_res.unwrap_err())

        adapter = adapter_res.unwrap()
        if not isinstance(adapter, IMarketBrokerAdapter):
            return Err(f"Broker '{account.broker}' does not support market/forex operations.")

        # Create persistent audit record
        db_order = OrderExecution(
            user_id=account.user_id,
            account_id=account.id,
            signal_id=signal_id,
            broker=account.broker,
            symbol=adapter.format_broker_asset(order_in.symbol, account.broker),
            raw_symbol=order_in.symbol,
            action=order_in.action.value,
            order_type="MARKET",
            amount=order_in.volume,
            stop_loss=order_in.sl,
            take_profit=order_in.tp,
            status="PENDING",
        )
        db.add(db_order)
        await db.commit()
        await db.refresh(db_order)

        start_time = time.perf_counter()

        try:
            if order_in.action.value == "BUY":
                trade_res = await adapter.buy_market(
                    symbol=order_in.symbol,
                    volume=order_in.volume,
                    sl=order_in.sl,
                    tp=order_in.tp,
                    deviation=order_in.deviation,
                    comment=order_in.comment,
                    magic=order_in.magic,
                    type_filling=order_in.type_filling,
                )
            else:
                trade_res = await adapter.sell_market(
                    symbol=order_in.symbol,
                    volume=order_in.volume,
                    sl=order_in.sl,
                    tp=order_in.tp,
                    deviation=order_in.deviation,
                    comment=order_in.comment,
                    magic=order_in.magic,
                    type_filling=order_in.type_filling,
                )

            latency_ms = int((time.perf_counter() - start_time) * 1000)
            db_order.latency_ms = latency_ms

            if trade_res.is_ok():
                result_data = trade_res.unwrap()
                db_order.broker_order_id = str(result_data.get("order") or result_data.get("deal") or "")
                db_order.entry_price = result_data.get("price")
                db_order.executed_amount = result_data.get("volume", order_in.volume)
                db_order.status = "FILLED"
            else:
                db_order.status = "REJECTED"
                db_order.error_log = trade_res.unwrap_err()

            # Refresh balance
            bal_res = await adapter.get_balance()
            if bal_res.is_ok():
                account.balance = bal_res.unwrap()
                account.last_connected_at = datetime.now(timezone.utc)
                db.add(account)

            db.add(db_order)
            await db.commit()
            await db.refresh(db_order)

            if db_order.status == "REJECTED":
                return Err(db_order.error_log or "Market order rejected.")
            return Ok(db_order)

        except Exception as ex:
            db_order.status = "FAILED"
            db_order.error_log = str(ex)
            db_order.latency_ms = int((time.perf_counter() - start_time) * 1000)
            db.add(db_order)
            await db.commit()
            return Err(f"Market execution exception: {str(ex)}")

    async def execute_signal(
        self,
        request: SignalExecuteRequest,
        db: AsyncSession,
        user_id: Optional[int] = None,
    ) -> Result[SignalExecutionSummary, str]:
        """
        Executes a trading signal across multiple target accounts concurrently.
        """
        # Resolve or create signal
        if request.signal_id:
            sig_query = await db.exec(select(TradingSignal).where(TradingSignal.id == request.signal_id))
            signal = sig_query.first()
            if not signal:
                return Err(f"Signal with ID {request.signal_id} not found.")
        elif request.signal_data:
            s_in = request.signal_data
            signal = TradingSignal(
                user_id=user_id,
                source=s_in.source,
                symbol=s_in.symbol,
                action=s_in.action.value,
                market_type=s_in.market_type,
                timeframe=s_in.timeframe,
                duration_seconds=s_in.duration_seconds,
                entry_price=s_in.entry_price,
                stop_loss=s_in.stop_loss,
                take_profit=s_in.take_profit,
                target_broker=s_in.target_broker,
                gale_steps=s_in.gale_steps,
                gale_multiplier=s_in.gale_multiplier,
                raw_data=str(s_in.raw_data) if s_in.raw_data else None,
                status="EXECUTING",
            )
            db.add(signal)
            await db.commit()
            await db.refresh(signal)
        else:
            return Err("Must provide either signal_id or signal_data.")

        executed_order_ids: List[int] = []
        success_count = 0
        failure_count = 0

        # Execute on all target accounts
        for acc_id in request.target_account_ids:
            try:
                acc = await self._get_validated_account(acc_id, db)
                if acc.broker in ("mt5", "metatrader", "metatrader5"):
                    # Market order
                    m_order = MarketOrderCreate(
                        account_id=acc.id,
                        symbol=signal.symbol,
                        action=signal.action,
                        volume=request.amount,
                        sl=signal.stop_loss,
                        tp=signal.take_profit,
                        comment=f"Signal #{signal.id}",
                    )
                    res = await self.execute_market_order(m_order, db, signal_id=signal.id)
                else:
                    # Binary order
                    duration = signal.duration_seconds or 60
                    g_steps = request.gale_steps if request.gale_steps is not None else signal.gale_steps
                    g_mult = request.gale_multiplier if request.gale_multiplier is not None else signal.gale_multiplier
                    b_order = BinaryOrderCreate(
                        account_id=acc.id,
                        symbol=signal.symbol,
                        action=signal.action,
                        amount=request.amount,
                        duration_seconds=duration,
                        gale_steps=g_steps,
                        gale_multiplier=g_mult,
                    )
                    res = await self.execute_binary_order(b_order, db, signal_id=signal.id)

                if res.is_ok():
                    success_count += 1
                    executed_order_ids.append(res.unwrap().id)
                else:
                    failure_count += 1
            except Exception as e:
                logger.error(f"Error executing signal #{signal.id} on account {acc_id}: {e}")
                failure_count += 1

        signal.status = "EXECUTED" if success_count > 0 else "FAILED"
        db.add(signal)
        await db.commit()

        return Ok(SignalExecutionSummary(
            signal_id=signal.id,
            total_accounts=len(request.target_account_ids),
            successful_executions=success_count,
            failed_executions=failure_count,
            execution_order_ids=executed_order_ids,
        ))

    async def settle_and_evaluate_trade(
        self,
        order_id: int,
        profit_loss: float,
        outcome: TradeOutcome,
        db: AsyncSession,
    ) -> Result[OrderExecution, str]:
        """
        Manually or webhook-driven settlement of an order execution with real-time progress evaluation.
        """
        stmt = select(OrderExecution).where(OrderExecution.id == order_id)
        res = await db.exec(stmt)
        order = res.first()
        if not order:
            return Err(f"Order #{order_id} not found.")

        order.profit_loss = profit_loss
        order.status = "WON" if outcome == TradeOutcome.WIN else ("LOST" if outcome == TradeOutcome.LOSS else "CLOSED")
        order.closed_at = datetime.now(timezone.utc)
        db.add(order)
        await db.commit()
        await db.refresh(order)

        try:
            await evaluate_trade_progress(
                TradeSettledPayload(
                    order_id=order.id,
                    user_id=order.user_id,
                    broker=order.broker,
                    symbol=order.symbol,
                    broker_ticket=order.broker_order_id,
                    sender_id=order.sender_id,
                    template_id=order.template_id,
                    profit_loss=profit_loss,
                    action=order.action,
                    outcome=outcome,
                ),
                db,
            )
        except Exception as eval_err:
            logger.error(f"Error evaluating trade progress for settled order {order_id}: {eval_err}")

        return Ok(order)


execution_engine = ExecutionEngine()

