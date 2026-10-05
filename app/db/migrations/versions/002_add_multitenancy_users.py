"""add_multitenancy_users

Revision ID: 002_add_multitenancy_users
Revises: 001_initial_schema
Create Date: 2026-09-29 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = '002_add_multitenancy_users'
down_revision: Union[str, None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create users table
    users_table = op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('username', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('hashed_password', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('full_name', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('role', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='user'),
        sa.Column('telegram_id', sa.BigInteger(), nullable=True),
        sa.Column('api_key', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('is_superuser', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.create_index(op.f('ix_users_role'), 'users', ['role'], unique=False)
    op.create_index(op.f('ix_users_telegram_id'), 'users', ['telegram_id'], unique=True)
    op.create_index(op.f('ix_users_api_key'), 'users', ['api_key'], unique=True)
    op.create_index(op.f('ix_users_is_active'), 'users', ['is_active'], unique=False)

    # 2. Seed initial default Administrator user (AdminQuant2026!)
    admin_password_hash = "pbkdf2_sha256$100000$7f2f9509852418f8e2502aa690e76b97$8323fe43ac0e6d8838802f3aa42490751e86f920201f32a091985efd4fd1674d"
    op.bulk_insert(
        users_table,
        [
            {
                'id': 1,
                'email': 'admin@quant.com',
                'username': 'admin',
                'hashed_password': admin_password_hash,
                'full_name': 'Administrator',
                'role': 'admin',
                'telegram_id': None,
                'api_key': 'quant_admin_initial_master_key',
                'is_active': True,
                'is_superuser': True,
            }
        ]
    )
    # Sync sequence for PostgreSQL id counter
    op.execute("SELECT setval(pg_get_serial_sequence('users', 'id'), (SELECT MAX(id) FROM users));")

    # 3. Add user_id to trading_accounts with backfill
    op.add_column('trading_accounts', sa.Column('user_id', sa.Integer(), nullable=True))
    op.execute("UPDATE trading_accounts SET user_id = 1 WHERE user_id IS NULL;")
    op.alter_column('trading_accounts', 'user_id', nullable=False)
    op.create_index(op.f('ix_trading_accounts_user_id'), 'trading_accounts', ['user_id'], unique=False)
    op.create_foreign_key(
        'fk_trading_accounts_user_id_users',
        'trading_accounts',
        'users',
        ['user_id'],
        ['id'],
        ondelete='CASCADE'
    )

    # 4. Add user_id to trading_signals
    op.add_column('trading_signals', sa.Column('user_id', sa.Integer(), nullable=True))
    op.execute("UPDATE trading_signals SET user_id = 1 WHERE user_id IS NULL;")
    op.create_index(op.f('ix_trading_signals_user_id'), 'trading_signals', ['user_id'], unique=False)
    op.create_foreign_key(
        'fk_trading_signals_user_id_users',
        'trading_signals',
        'users',
        ['user_id'],
        ['id'],
        ondelete='SET NULL'
    )

    # 5. Add user_id to order_executions
    op.add_column('order_executions', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_order_executions_user_id'), 'order_executions', ['user_id'], unique=False)
    op.create_foreign_key(
        'fk_order_executions_user_id_users',
        'order_executions',
        'users',
        ['user_id'],
        ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    # 1. order_executions
    op.drop_constraint('fk_order_executions_user_id_users', 'order_executions', type_='foreignkey')
    op.drop_index(op.f('ix_order_executions_user_id'), table_name='order_executions')
    op.drop_column('order_executions', 'user_id')

    # 2. trading_signals
    op.drop_constraint('fk_trading_signals_user_id_users', 'trading_signals', type_='foreignkey')
    op.drop_index(op.f('ix_trading_signals_user_id'), table_name='trading_signals')
    op.drop_column('trading_signals', 'user_id')

    # 3. trading_accounts
    op.drop_constraint('fk_trading_accounts_user_id_users', 'trading_accounts', type_='foreignkey')
    op.drop_index(op.f('ix_trading_accounts_user_id'), table_name='trading_accounts')
    op.drop_column('trading_accounts', 'user_id')

    # 4. users
    op.drop_index(op.f('ix_users_is_active'), table_name='users')
    op.drop_index(op.f('ix_users_api_key'), table_name='users')
    op.drop_index(op.f('ix_users_telegram_id'), table_name='users')
    op.drop_index(op.f('ix_users_role'), table_name='users')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
