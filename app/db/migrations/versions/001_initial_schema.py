"""initial_schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-09-27 18:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. broker_catalog
    op.create_table(
        'broker_catalog',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('market_types', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('supports_demo', sa.Boolean(), nullable=False),
        sa.Column('supports_real', sa.Boolean(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('notes', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_broker_catalog_code'), 'broker_catalog', ['code'], unique=True)

    # 2. trading_accounts
    op.create_table(
        'trading_accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('broker', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('account_name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('account_number', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('account_mode', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('encrypted_credentials', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('balance', sa.Float(), nullable=False),
        sa.Column('equity', sa.Float(), nullable=True),
        sa.Column('currency', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('server', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('last_connected_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_trading_accounts_broker'), 'trading_accounts', ['broker'], unique=False)
    op.create_index(op.f('ix_trading_accounts_account_number'), 'trading_accounts', ['account_number'], unique=False)
    op.create_index(op.f('ix_trading_accounts_is_active'), 'trading_accounts', ['is_active'], unique=False)

    # 3. trading_signals
    op.create_table(
        'trading_signals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('symbol', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('action', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('market_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('timeframe', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        sa.Column('entry_price', sa.Float(), nullable=True),
        sa.Column('stop_loss', sa.Float(), nullable=True),
        sa.Column('take_profit', sa.Float(), nullable=True),
        sa.Column('target_broker', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('gale_steps', sa.Integer(), nullable=False),
        sa.Column('gale_multiplier', sa.Float(), nullable=False),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('raw_data', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_trading_signals_source'), 'trading_signals', ['source'], unique=False)
    op.create_index(op.f('ix_trading_signals_symbol'), 'trading_signals', ['symbol'], unique=False)
    op.create_index(op.f('ix_trading_signals_action'), 'trading_signals', ['action'], unique=False)
    op.create_index(op.f('ix_trading_signals_status'), 'trading_signals', ['status'], unique=False)

    # 4. order_executions
    op.create_table(
        'order_executions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('signal_id', sa.Integer(), nullable=True),
        sa.Column('broker', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('broker_order_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('symbol', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('raw_symbol', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('action', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('order_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('executed_amount', sa.Float(), nullable=True),
        sa.Column('entry_price', sa.Float(), nullable=True),
        sa.Column('close_price', sa.Float(), nullable=True),
        sa.Column('stop_loss', sa.Float(), nullable=True),
        sa.Column('take_profit', sa.Float(), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        sa.Column('profit_loss', sa.Float(), nullable=True),
        sa.Column('drawdown', sa.Float(), nullable=True),
        sa.Column('spread', sa.Float(), nullable=True),
        sa.Column('slippage', sa.Float(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('gale_step', sa.Integer(), nullable=False),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('error_log', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['trading_accounts.id'], ),
        sa.ForeignKeyConstraint(['signal_id'], ['trading_signals.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_order_executions_account_id'), 'order_executions', ['account_id'], unique=False)
    op.create_index(op.f('ix_order_executions_signal_id'), 'order_executions', ['signal_id'], unique=False)
    op.create_index(op.f('ix_order_executions_broker'), 'order_executions', ['broker'], unique=False)
    op.create_index(op.f('ix_order_executions_broker_order_id'), 'order_executions', ['broker_order_id'], unique=False)
    op.create_index(op.f('ix_order_executions_symbol'), 'order_executions', ['symbol'], unique=False)
    op.create_index(op.f('ix_order_executions_status'), 'order_executions', ['status'], unique=False)


def downgrade() -> None:
    op.drop_table('order_executions')
    op.drop_table('trading_signals')
    op.drop_table('trading_accounts')
    op.drop_table('broker_catalog')
