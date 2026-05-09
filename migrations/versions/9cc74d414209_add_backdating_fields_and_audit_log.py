"""add backdating fields and audit log

Revision ID: 9cc74d414209
Revises: 1bbbdcf76bc7
Create Date: 2026-05-07 14:31:08.897261
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision      = '9cc74d414209'
down_revision = '1bbbdcf76bc7'
branch_labels = None
depends_on    = None


def upgrade():
    # ── 1. New audit log table ───────────────────────────────────────────────
    op.create_table(
        'sale_audit_log',
        sa.Column('id',           sa.Integer(),       nullable=False),
        sa.Column('sale_id',      sa.Integer(),       nullable=True),
        sa.Column('action',       sa.String(50),      nullable=False),
        sa.Column('performed_by', sa.Integer(),       nullable=False),
        sa.Column('performed_at', sa.DateTime(),      server_default=sa.func.now(), nullable=False),
        sa.Column('details',      sa.JSON(),          nullable=True),
        sa.Column('ip_address',   sa.String(45),      nullable=True),
        sa.ForeignKeyConstraint(['performed_by'], ['users.id'], name='fk_audit_performed_by'),
        sa.ForeignKeyConstraint(['sale_id'],      ['sales.id'], name='fk_audit_sale', ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── 2. Add new columns to `sales` — created_at NULLABLE for now ──────────
    with op.batch_alter_table('sales', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_at',         sa.DateTime(),  nullable=True))
        batch_op.add_column(sa.Column('is_backdated',       sa.Boolean(),   server_default=sa.text('false'), nullable=False))
        batch_op.add_column(sa.Column('backdate_reason',    sa.String(255), nullable=True))
        batch_op.add_column(sa.Column('backdate_reference', sa.String(100), nullable=True))
        batch_op.add_column(sa.Column('entered_by_id',      sa.Integer(),   nullable=True))
        batch_op.add_column(sa.Column('approved_by_id',     sa.Integer(),   nullable=True))
        batch_op.create_foreign_key('fk_sales_entered_by',  'users', ['entered_by_id'],  ['id'])
        batch_op.create_foreign_key('fk_sales_approved_by', 'users', ['approved_by_id'], ['id'])

    # ── 3. Backfill created_at for existing rows ─────────────────────────────
    # Best approximation: use sale_date. New rows get now() via the server default.
    op.execute("UPDATE sales SET created_at = sale_date WHERE created_at IS NULL")

    # ── 4. Lock created_at down: NOT NULL + server default for future inserts ─
    with op.batch_alter_table('sales', schema=None) as batch_op:
        batch_op.alter_column(
            'created_at',
            existing_type   = sa.DateTime(),
            nullable        = False,
            server_default  = sa.func.now(),
        )


def downgrade():
    with op.batch_alter_table('sales', schema=None) as batch_op:
        batch_op.drop_constraint('fk_sales_approved_by', type_='foreignkey')
        batch_op.drop_constraint('fk_sales_entered_by',  type_='foreignkey')
        batch_op.drop_column('approved_by_id')
        batch_op.drop_column('entered_by_id')
        batch_op.drop_column('backdate_reference')
        batch_op.drop_column('backdate_reason')
        batch_op.drop_column('is_backdated')
        batch_op.drop_column('created_at')

    op.drop_table('sale_audit_log')