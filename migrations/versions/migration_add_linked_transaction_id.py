"""add linked_transaction_id to mpesa_transactions

Revision ID: a1b2c3d4e5f6
Revises: 92aff41a54e7
Create Date: 2026-04-20
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = '92aff41a54e7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'mpesa_transactions',
        sa.Column('linked_transaction_id', sa.String(100), nullable=True)
    )
    op.create_index(
        'ix_mpesa_transactions_linked_transaction_id',
        'mpesa_transactions',
        ['linked_transaction_id']
    )


def downgrade():
    op.drop_index('ix_mpesa_transactions_linked_transaction_id', table_name='mpesa_transactions')
    op.drop_column('mpesa_transactions', 'linked_transaction_id')
