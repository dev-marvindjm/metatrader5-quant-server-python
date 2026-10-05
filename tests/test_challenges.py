import asyncio
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.testclient import TestClient

from app.main import create_app
from app.core.dependencies import get_db
from app.core.auth import get_current_user, get_current_active_user
from app.domain.enums import GoalType, FundStatus, ChallengeStatus, TradeOutcome, RankingMetric
from app.domain.models import (
    User,
    Fund,
    FundContributionAudit,
    Challenge,
    ChallengeParticipant,
    SignalTemplate,
    SenderRule,
)
from app.services.progress_evaluator import (
    evaluate_trade_progress,
    TradeSettledPayload,
    recalculate_challenge_leaderboard,
    matches_filters,
)


class TestChallengesAndFunds(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Create an isolated async in-memory SQLite database
        self.engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            echo=False,
            future=True,
        )
        self.session_maker = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

        # Seed test users
        async with self.session_maker() as session:
            self.user1 = User(
                id=1,
                email="trader1@quant.com",
                username="trader1",
                hashed_password="hash",
                role="trader",
                is_active=True,
            )
            self.user2 = User(
                id=2,
                email="trader2@quant.com",
                username="trader2",
                hashed_password="hash",
                role="trader",
                is_active=True,
            )
            session.add_all([self.user1, self.user2])
            await session.commit()

    async def asyncTearDown(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
        await self.engine.dispose()

    async def test_single_user_challenge_completion(self):
        """
        Tests elastic participation for 1 single user (time-trial / self-overcoming challenge).
        Validates target capital achievement, automatic podium, and challenge conclusion.
        """
        async with self.session_maker() as session:
            challenge = Challenge(
                creator_user_id=1,
                title="Solo Sprint $500",
                goal_type=GoalType.TARGET_CAPITAL,
                goal_target_value=500.0,
                status=ChallengeStatus.RUNNING,
            )
            session.add(challenge)
            await session.commit()
            await session.refresh(challenge)

            participant = ChallengeParticipant(
                challenge_id=challenge.id,
                user_id=1,
                current_progress_value=0.0,
            )
            session.add(participant)
            await session.commit()
            await session.refresh(participant)

            # Trade 1: Win $300
            res1 = await evaluate_trade_progress(
                TradeSettledPayload(
                    order_id=101,
                    user_id=1,
                    broker="quotex",
                    symbol="EURUSD-OTC",
                    profit_loss=300.0,
                    action="BUY",
                    outcome=TradeOutcome.WIN,
                ),
                session,
            )
            self.assertEqual(len(res1.challenges_updated), 1)
            self.assertEqual(len(res1.participants_completed), 0)

            # Refresh participant
            await session.refresh(participant)
            self.assertEqual(participant.current_progress_value, 300.0)
            self.assertIsNone(participant.completed_at)

            # Trade 2: Win $250 -> Total $550 (Goal reached >= 500.0)
            res2 = await evaluate_trade_progress(
                TradeSettledPayload(
                    order_id=102,
                    user_id=1,
                    broker="quotex",
                    symbol="EURUSD-OTC",
                    profit_loss=250.0,
                    action="BUY",
                    outcome=TradeOutcome.WIN,
                ),
                session,
            )
            self.assertIn(1, res2.participants_completed)

            await session.refresh(participant)
            await session.refresh(challenge)

            # Assert participant completed & ranked 1
            self.assertIsNotNone(participant.completed_at)
            self.assertEqual(participant.rank_position, 1)
            self.assertEqual(participant.current_progress_value, 550.0)

            # Single-user challenge automatically concludes when finished
            self.assertEqual(challenge.status, ChallengeStatus.CONCLUDED)
            self.assertIsNotNone(challenge.concluded_at)

    async def test_multiplayer_challenge_and_leaderboard(self):
        """
        Tests multi-user competition: User 1 and User 2 compete to reach 2 trades.
        User 2 reaches the goal first and claims Rank 1. User 1 finishes later and claims Rank 2.
        """
        async with self.session_maker() as session:
            challenge = Challenge(
                creator_user_id=1,
                title="Binary Speed Duel",
                goal_type=GoalType.TRADE_COUNT,
                goal_target_value=2.0,
                status=ChallengeStatus.RUNNING,
            )
            session.add(challenge)
            await session.commit()
            await session.refresh(challenge)

            p1 = ChallengeParticipant(challenge_id=challenge.id, user_id=1)
            p2 = ChallengeParticipant(challenge_id=challenge.id, user_id=2)
            session.add_all([p1, p2])
            await session.commit()

            # User 2 trades twice rapidly
            await evaluate_trade_progress(
                TradeSettledPayload(user_id=2, broker="mt5", symbol="GBPUSD", profit_loss=50.0, outcome=TradeOutcome.WIN),
                session,
            )
            await asyncio.sleep(0.01)
            await evaluate_trade_progress(
                TradeSettledPayload(user_id=2, broker="mt5", symbol="GBPUSD", profit_loss=40.0, outcome=TradeOutcome.WIN),
                session,
            )

            await session.refresh(p2)
            self.assertIsNotNone(p2.completed_at)
            self.assertEqual(p2.rank_position, 1)

            # User 1 executes trade 1
            await evaluate_trade_progress(
                TradeSettledPayload(user_id=1, broker="mt5", symbol="EURUSD", profit_loss=20.0, outcome=TradeOutcome.WIN),
                session,
            )
            await session.refresh(p1)
            self.assertEqual(p1.total_trades, 1)
            self.assertEqual(p1.rank_position, 2)

            # User 1 executes trade 2 and completes
            await asyncio.sleep(0.01)
            await evaluate_trade_progress(
                TradeSettledPayload(user_id=1, broker="mt5", symbol="EURUSD", profit_loss=30.0, outcome=TradeOutcome.WIN),
                session,
            )
            await session.refresh(p1)
            await session.refresh(p2)
            await session.refresh(challenge)

            # Verify final leaderboard standings
            self.assertEqual(p2.rank_position, 1)
            self.assertEqual(p1.rank_position, 2)
            self.assertTrue(p2.completed_at < p1.completed_at)
            self.assertEqual(challenge.status, ChallengeStatus.CONCLUDED)

    async def test_drawdown_disqualification_and_elastic_survival(self):
        """
        Tests risk parameters: Max Drawdown Limit breach disqualifies a participant.
        Crucially verifies that the Challenge is NOT cancelled and continues actively
        for the surviving participant.
        """
        async with self.session_maker() as session:
            challenge = Challenge(
                creator_user_id=1,
                title="Strict Risk Arena",
                goal_type=GoalType.TARGET_CAPITAL,
                goal_target_value=300.0,
                max_drawdown_limit=Decimal("150.0"),  # $150 max loss from peak
                status=ChallengeStatus.RUNNING,
            )
            session.add(challenge)
            await session.commit()
            await session.refresh(challenge)

            p1 = ChallengeParticipant(challenge_id=challenge.id, user_id=1)
            p2 = ChallengeParticipant(challenge_id=challenge.id, user_id=2)
            session.add_all([p1, p2])
            await session.commit()

            # User 2 experiences heavy loss of $200 (> 150 limit)
            res = await evaluate_trade_progress(
                TradeSettledPayload(
                    user_id=2,
                    broker="pocketoption",
                    symbol="BTCUSD",
                    profit_loss=-200.0,
                    outcome=TradeOutcome.LOSS,
                ),
                session,
            )
            self.assertIn(2, res.participants_disqualified)

            await session.refresh(p2)
            await session.refresh(challenge)

            self.assertTrue(p2.is_disqualified)
            self.assertIn("Drawdown breach", p2.disqualification_reason)
            # Challenge MUST remain RUNNING for User 1 (elastic survival)
            self.assertEqual(challenge.status, ChallengeStatus.RUNNING)

            # User 1 successfully trades and reaches target
            await evaluate_trade_progress(
                TradeSettledPayload(
                    user_id=1,
                    broker="pocketoption",
                    symbol="BTCUSD",
                    profit_loss=350.0,
                    outcome=TradeOutcome.WIN,
                ),
                session,
            )
            await session.refresh(p1)
            await session.refresh(challenge)

            self.assertFalse(p1.is_disqualified)
            self.assertIsNotNone(p1.completed_at)
            self.assertEqual(p1.rank_position, 1)
            self.assertEqual(p2.rank_position, 2)
            self.assertEqual(challenge.status, ChallengeStatus.CONCLUDED)

    async def test_win_rate_and_profit_factor_goal_types(self):
        """
        Tests GoalType.WIN_RATE_PERCENTAGE and GoalType.PROFIT_FACTOR_RATIO with minimum sample trades.
        """
        async with self.session_maker() as session:
            # 1. Fund with WIN_RATE_PERCENTAGE >= 75.0%, min_sample_trades = 4
            wr_fund = Fund(
                user_id=1,
                title="High Win Rate Fund",
                goal_type=GoalType.WIN_RATE_PERCENTAGE,
                goal_target_value=75.0,
                min_sample_trades=4,
                status=FundStatus.ACTIVE,
            )
            session.add(wr_fund)
            await session.commit()
            await session.refresh(wr_fund)

            # Trade 1-3: 3 wins (100% win rate, but min_sample_trades is 4, so not completed yet)
            for i in range(3):
                await evaluate_trade_progress(
                    TradeSettledPayload(user_id=1, broker="mt5", symbol="EURUSD", profit_loss=50.0, outcome=TradeOutcome.WIN),
                    session,
                )
            await session.refresh(wr_fund)
            self.assertEqual(wr_fund.total_trades, 3)
            self.assertEqual(wr_fund.status, FundStatus.ACTIVE)

            # Trade 4: 1 loss (3 wins / 4 trades = 75.0% win rate == target -> Completed!)
            await evaluate_trade_progress(
                TradeSettledPayload(user_id=1, broker="mt5", symbol="EURUSD", profit_loss=-50.0, outcome=TradeOutcome.LOSS),
                session,
            )
            await session.refresh(wr_fund)
            self.assertEqual(wr_fund.total_trades, 4)
            self.assertEqual(wr_fund.current_progress_value, 75.0)
            self.assertEqual(wr_fund.status, FundStatus.COMPLETED)

            # 2. Fund with PROFIT_FACTOR_RATIO >= 2.0, min_sample_trades = 3
            pf_fund = Fund(
                user_id=2,
                title="Profit Factor Fund",
                goal_type=GoalType.PROFIT_FACTOR_RATIO,
                goal_target_value=2.0,
                min_sample_trades=3,
                status=FundStatus.ACTIVE,
            )
            session.add(pf_fund)
            await session.commit()
            await session.refresh(pf_fund)

            # Gross profit = 300, gross loss = 100 -> PF = 3.0 (>= 2.0)
            await evaluate_trade_progress(
                TradeSettledPayload(user_id=2, broker="iqoption", symbol="EURUSD", profit_loss=200.0, outcome=TradeOutcome.WIN),
                session,
            )
            await evaluate_trade_progress(
                TradeSettledPayload(user_id=2, broker="iqoption", symbol="EURUSD", profit_loss=-100.0, outcome=TradeOutcome.LOSS),
                session,
            )
            await evaluate_trade_progress(
                TradeSettledPayload(user_id=2, broker="iqoption", symbol="EURUSD", profit_loss=100.0, outcome=TradeOutcome.WIN),
                session,
            )
            await session.refresh(pf_fund)
            self.assertEqual(pf_fund.total_trades, 3)
            self.assertEqual(pf_fund.current_progress_value, 3.0)
            self.assertEqual(pf_fund.status, FundStatus.COMPLETED)

    async def test_filters_exclusion_logic(self):
        """
        Tests that broker, sender_id, and template_id filters accurately isolate qualifying trades.
        """
        async with self.session_maker() as session:
            fund = Fund(
                user_id=1,
                title="Restricted VIP Fund",
                goal_type=GoalType.TRADE_COUNT,
                goal_target_value=5.0,
                allowed_brokers=["mt5", "quotex"],
                allowed_sender_ids=["telegram_vip_channel"],
                allowed_template_ids=[42],
                status=FundStatus.ACTIVE,
            )
            session.add(fund)
            await session.commit()
            await session.refresh(fund)

            # Disallowed broker: pocketoption
            await evaluate_trade_progress(
                TradeSettledPayload(
                    user_id=1,
                    broker="pocketoption",
                    symbol="EURUSD",
                    sender_id="telegram_vip_channel",
                    template_id=42,
                    profit_loss=10.0,
                    outcome=TradeOutcome.WIN,
                ),
                session,
            )
            await session.refresh(fund)
            self.assertEqual(fund.total_trades, 0)

            # Disallowed sender: random_group
            await evaluate_trade_progress(
                TradeSettledPayload(
                    user_id=1,
                    broker="mt5",
                    symbol="EURUSD",
                    sender_id="random_group",
                    template_id=42,
                    profit_loss=10.0,
                    outcome=TradeOutcome.WIN,
                ),
                session,
            )
            await session.refresh(fund)
            self.assertEqual(fund.total_trades, 0)

            # Disallowed template: 99
            await evaluate_trade_progress(
                TradeSettledPayload(
                    user_id=1,
                    broker="mt5",
                    symbol="EURUSD",
                    sender_id="telegram_vip_channel",
                    template_id=99,
                    profit_loss=10.0,
                    outcome=TradeOutcome.WIN,
                ),
                session,
            )
            await session.refresh(fund)
            self.assertEqual(fund.total_trades, 0)

            # Qualifying trade matching ALL filters
            await evaluate_trade_progress(
                TradeSettledPayload(
                    user_id=1,
                    broker="mt5",
                    symbol="EURUSD",
                    sender_id="telegram_vip_channel",
                    template_id=42,
                    profit_loss=25.0,
                    outcome=TradeOutcome.WIN,
                ),
                session,
            )
            await session.refresh(fund)
            self.assertEqual(fund.total_trades, 1)
            self.assertEqual(fund.current_progress_value, 1.0)

    async def test_fund_contribution_audit_trail(self):
        """
        Validates that each qualifying trade generates a persistent 1:N FundContributionAudit record
        with mathematical traceability of progression and drawdown.
        """
        async with self.session_maker() as session:
            fund = Fund(
                user_id=1,
                title="Audit Trail Test Fund",
                goal_type=GoalType.TARGET_CAPITAL,
                goal_target_value=1000.0,
                status=FundStatus.ACTIVE,
            )
            session.add(fund)
            await session.commit()
            await session.refresh(fund)

            res = await evaluate_trade_progress(
                TradeSettledPayload(
                    order_id=555,
                    user_id=1,
                    broker="quotex",
                    symbol="USDJPY-OTC",
                    broker_ticket="ticket-9988",
                    sender_id="vip_signals",
                    template_id=7,
                    profit_loss=150.0,
                    action="CALL",
                    outcome=TradeOutcome.WIN,
                ),
                session,
            )
            self.assertEqual(res.audits_created, 1)

            # Query audit record
            audit_stmt = select(FundContributionAudit).where(FundContributionAudit.fund_id == fund.id)
            audit_res = await session.exec(audit_stmt)
            audit = audit_res.first()

            self.assertIsNotNone(audit)
            self.assertEqual(audit.order_execution_id, 555)
            self.assertEqual(audit.broker, "quotex")
            self.assertEqual(audit.symbol, "USDJPY-OTC")
            self.assertEqual(audit.broker_ticket, "ticket-9988")
            self.assertEqual(audit.sender_id, "vip_signals")
            self.assertEqual(audit.template_id, 7)
            self.assertEqual(audit.trade_action, "CALL")
            self.assertEqual(audit.profit_loss, Decimal("150.0"))
            self.assertEqual(audit.previous_progress_value, 0.0)
            self.assertEqual(audit.new_progress_value, 150.0)


class TestChallengesAndFundsApiEndpoints(unittest.TestCase):
    """
    HTTP API tests for Funds and Challenges routes.
    """
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = TestClient(cls.app)

        cls.engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            echo=False,
            future=True,
        )
        cls.session_maker = async_sessionmaker(
            bind=cls.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        async def init_tables():
            async with cls.engine.begin() as conn:
                await conn.run_sync(SQLModel.metadata.create_all)

        asyncio.run(init_tables())

        cls.mock_user = User(
            id=1,
            email="test_api_trader@quant.com",
            username="api_trader",
            hashed_password="hash",
            role="trader",
            is_active=True,
        )

        async def seed_user():
            async with cls.session_maker() as session:
                session.add(cls.mock_user)
                await session.commit()

        asyncio.run(seed_user())

    @classmethod
    def tearDownClass(cls):
        async def drop():
            await cls.engine.dispose()
        asyncio.run(drop())

    def setUp(self):
        async def override_get_db():
            async with self.session_maker() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise
                finally:
                    await session.close()

        self.app.dependency_overrides[get_db] = override_get_db
        self.app.dependency_overrides[get_current_user] = lambda: self.mock_user
        self.app.dependency_overrides[get_current_active_user] = lambda: self.mock_user

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def test_funds_lifecycle_api(self):
        # 1. Create fund
        fund_payload = {
            "title": "API Test Fund $1000",
            "description": "Accumulation fund created via REST",
            "goal_type": "TARGET_CAPITAL",
            "goal_target_value": 1000.0,
            "max_drawdown_limit": 200.0,
            "allowed_brokers": ["mt5", "quotex"],
        }
        res_create = self.client.post("/api/v1/funds", json=fund_payload)
        self.assertEqual(res_create.status_code, 201)
        data = res_create.json()["data"]
        fund_id = data["id"]
        self.assertEqual(data["title"], "API Test Fund $1000")
        self.assertEqual(data["status"], "ACTIVE")

        # 2. List funds
        res_list = self.client.get("/api/v1/funds")
        self.assertEqual(res_list.status_code, 200)
        self.assertGreaterEqual(len(res_list.json()["data"]), 1)

        # 3. Get metrics
        res_metrics = self.client.get(f"/api/v1/funds/{fund_id}/metrics")
        self.assertEqual(res_metrics.status_code, 200)
        m_data = res_metrics.json()["data"]
        self.assertIn("fund", m_data)
        self.assertIn("audits", m_data)

        # 4. Pause fund
        res_pause = self.client.post(f"/api/v1/funds/{fund_id}/pause")
        self.assertEqual(res_pause.status_code, 200)
        self.assertEqual(res_pause.json()["data"]["status"], "PAUSED")

        # 5. Resume fund
        res_resume = self.client.post(f"/api/v1/funds/{fund_id}/resume")
        self.assertEqual(res_resume.status_code, 200)
        self.assertEqual(res_resume.json()["data"]["status"], "ACTIVE")

    def test_challenges_lifecycle_api(self):
        # 1. Create challenge
        ch_payload = {
            "title": "Championship 50 Trades",
            "description": "Volume trading championship",
            "goal_type": "TRADE_COUNT",
            "goal_target_value": 50.0,
            "is_public": True,
            "ranking_metric": "PROGRESS",
        }
        res_create = self.client.post("/api/v1/challenges", json=ch_payload)
        self.assertEqual(res_create.status_code, 201)
        ch_data = res_create.json()["data"]
        ch_id = ch_data["id"]
        self.assertEqual(ch_data["title"], "Championship 50 Trades")

        # 2. Join challenge
        res_join = self.client.post(f"/api/v1/challenges/{ch_id}/join")
        self.assertEqual(res_join.status_code, 200)
        p_data = res_join.json()["data"]
        self.assertEqual(p_data["user_id"], 1)

        # 3. Get leaderboard
        res_lb = self.client.get(f"/api/v1/challenges/{ch_id}/leaderboard")
        self.assertEqual(res_lb.status_code, 200)
        lb_data = res_lb.json()["data"]
        self.assertEqual(lb_data["total_participants"], 1)
        self.assertEqual(len(lb_data["leaderboard"]), 1)

        # 4. History / winners wall
        res_win = self.client.get("/api/v1/challenges/history/winners")
        self.assertEqual(res_win.status_code, 200)
        self.assertIsInstance(res_win.json()["data"], list)

        # 5. Evaluate trade webhook endpoint
        trade_payload = {
            "user_id": 1,
            "broker": "mt5",
            "symbol": "EURUSD",
            "profit_loss": 50.0,
            "action": "BUY",
            "outcome": "WIN",
        }
        res_eval = self.client.post("/api/v1/challenges/evaluate-trade", json=trade_payload)
        self.assertEqual(res_eval.status_code, 200)
        self.assertTrue(res_eval.json()["success"])
