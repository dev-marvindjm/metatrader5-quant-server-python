"""add_templates_rules_funds_challenges

Revision ID: 003_add_templates_rules_funds_challenges
Revises: 002_add_multitenancy_users
Create Date: 2026-09-30 22:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = '003_add_funds_and_templates'
down_revision: Union[str, None] = '002_add_multitenancy_users'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. signal_templates
    op.create_table(
        'signal_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('pattern', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('target_broker', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('market_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='BINARY'),
        sa.Column('default_amount', sa.Float(), nullable=False, server_default='10.0'),
        sa.Column('default_duration_seconds', sa.Integer(), nullable=True, server_default='60'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_signal_templates_name'), 'signal_templates', ['name'], unique=False)
    op.create_index(op.f('ix_signal_templates_is_active'), 'signal_templates', ['is_active'], unique=False)

    # 2. sender_rules
    op.create_table(
        'sender_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sender_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('channel_name', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('default_template_id', sa.Integer(), nullable=True),
        sa.Column('is_trusted', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['default_template_id'], ['signal_templates.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sender_rules_sender_id'), 'sender_rules', ['sender_id'], unique=True)
    op.create_index(op.f('ix_sender_rules_is_trusted'), 'sender_rules', ['is_trusted'], unique=False)
    op.create_index(op.f('ix_sender_rules_default_template_id'), 'sender_rules', ['default_template_id'], unique=False)

    # 3. Add sender_id and template_id to trading_signals
    op.add_column('trading_signals', sa.Column('sender_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('trading_signals', sa.Column('template_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_trading_signals_sender_id'), 'trading_signals', ['sender_id'], unique=False)
    op.create_index(op.f('ix_trading_signals_template_id'), 'trading_signals', ['template_id'], unique=False)
    op.create_foreign_key('fk_trading_signals_template_id', 'trading_signals', 'signal_templates', ['template_id'], ['id'])

    # 3.1. Add sender_id and template_id to order_executions
    op.add_column('order_executions', sa.Column('sender_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('order_executions', sa.Column('template_id', sa.Integer(), nullable=True))

    # 4. funds
    op.create_table(
        'funds',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('target_amount', sa.Numeric(14, 4), nullable=True),
        sa.Column('current_amount', sa.Numeric(14, 4), nullable=False, server_default='0.0'),
        sa.Column('goal_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('goal_target_value', sa.Float(), nullable=False),
        sa.Column('current_progress_value', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('peak_progress_value', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('total_trades', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('winning_trades', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('losing_trades', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('gross_profit', sa.Numeric(14, 4), nullable=False, server_default='0.0'),
        sa.Column('gross_loss', sa.Numeric(14, 4), nullable=False, server_default='0.0'),
        sa.Column('current_drawdown', sa.Numeric(14, 4), nullable=False, server_default='0.0'),
        sa.Column('max_drawdown_limit', sa.Numeric(14, 4), nullable=True),
        sa.Column('max_consecutive_losses', sa.Integer(), nullable=True),
        sa.Column('current_consecutive_losses', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('min_sample_trades', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('allowed_brokers', sa.JSON(), nullable=True),
        sa.Column('allowed_sender_ids', sa.JSON(), nullable=True),
        sa.Column('allowed_template_ids', sa.JSON(), nullable=True),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='ACTIVE'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_funds_user_id'), 'funds', ['user_id'], unique=False)
    op.create_index(op.f('ix_funds_title'), 'funds', ['title'], unique=False)
    op.create_index(op.f('ix_funds_goal_type'), 'funds', ['goal_type'], unique=False)
    op.create_index(op.f('ix_funds_status'), 'funds', ['status'], unique=False)

    # 5. challenges
    op.create_table(
        'challenges',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('creator_user_id', sa.Integer(), nullable=False),
        sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('goal_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('goal_target_value', sa.Float(), nullable=False),
        sa.Column('min_sample_trades', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('entry_fee', sa.Numeric(14, 4), nullable=False, server_default='0.0'),
        sa.Column('max_drawdown_limit', sa.Numeric(14, 4), nullable=True),
        sa.Column('allowed_brokers', sa.JSON(), nullable=True),
        sa.Column('allowed_sender_ids', sa.JSON(), nullable=True),
        sa.Column('allowed_template_ids', sa.JSON(), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('ranking_metric', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='PROGRESS'),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='RUNNING'),
        sa.Column('winner_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('concluded_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['creator_user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['winner_user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_challenges_creator_user_id'), 'challenges', ['creator_user_id'], unique=False)
    op.create_index(op.f('ix_challenges_title'), 'challenges', ['title'], unique=False)
    op.create_index(op.f('ix_challenges_goal_type'), 'challenges', ['goal_type'], unique=False)
    op.create_index(op.f('ix_challenges_status'), 'challenges', ['status'], unique=False)
    op.create_index(op.f('ix_challenges_is_public'), 'challenges', ['is_public'], unique=False)

    # 6. challenge_participants
    op.create_table(
        'challenge_participants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('challenge_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('joined_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('current_progress_value', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('peak_progress_value', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('total_trades', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('winning_trades', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('losing_trades', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('gross_profit', sa.Numeric(14, 4), nullable=False, server_default='0.0'),
        sa.Column('gross_loss', sa.Numeric(14, 4), nullable=False, server_default='0.0'),
        sa.Column('current_drawdown', sa.Numeric(14, 4), nullable=False, server_default='0.0'),
        sa.Column('max_consecutive_losses_reached', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_disqualified', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('disqualification_reason', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('final_rank', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['challenge_id'], ['challenges.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_challenge_participants_challenge_id'), 'challenge_participants', ['challenge_id'], unique=False)
    op.create_index(op.f('ix_challenge_participants_user_id'), 'challenge_participants', ['user_id'], unique=False)
    op.create_index(op.f('ix_challenge_participants_is_disqualified'), 'challenge_participants', ['is_disqualified'], unique=False)

    # 7. fund_contribution_audits
    op.create_table(
        'fund_contribution_audits',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fund_id', sa.Integer(), nullable=True),
        sa.Column('challenge_participant_id', sa.Integer(), nullable=True),
        sa.Column('order_execution_id', sa.Integer(), nullable=True),
        sa.Column('broker', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('symbol', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('broker_ticket', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('sender_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('template_id', sa.Integer(), nullable=True),
        sa.Column('trade_action', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='BUY'),
        sa.Column('profit_loss', sa.Numeric(14, 4), nullable=False, server_default='0.0'),
        sa.Column('outcome', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('previous_progress_value', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('new_progress_value', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('drawdown_recorded', sa.Numeric(14, 4), nullable=False, server_default='0.0'),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['challenge_participant_id'], ['challenge_participants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['fund_id'], ['funds.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['order_execution_id'], ['order_executions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_fund_contribution_audits_fund_id'), 'fund_contribution_audits', ['fund_id'], unique=False)
    op.create_index(op.f('ix_fund_contribution_audits_challenge_participant_id'), 'fund_contribution_audits', ['challenge_participant_id'], unique=False)
    op.create_index(op.f('ix_fund_contribution_audits_order_execution_id'), 'fund_contribution_audits', ['order_execution_id'], unique=False)
    op.create_index(op.f('ix_fund_contribution_audits_broker'), 'fund_contribution_audits', ['broker'], unique=False)
    op.create_index(op.f('ix_fund_contribution_audits_sender_id'), 'fund_contribution_audits', ['sender_id'], unique=False)
    op.create_index(op.f('ix_fund_contribution_audits_template_id'), 'fund_contribution_audits', ['template_id'], unique=False)


def downgrade() -> None:
    op.drop_table('fund_contribution_audits')
    op.drop_table('challenge_participants')
    op.drop_table('challenges')
    op.drop_table('funds')
    op.drop_constraint('fk_trading_signals_template_id', 'trading_signals', type_='foreignkey')
    op.drop_index(op.f('ix_trading_signals_template_id'), table_name='trading_signals')
    op.drop_index(op.f('ix_trading_signals_sender_id'), table_name='trading_signals')
    op.drop_column('trading_signals', 'template_id')
    op.drop_column('trading_signals', 'sender_id')
    op.drop_table('sender_rules')
    op.drop_table('signal_templates')
