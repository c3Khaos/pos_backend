"""float to numeric, fix change_given

Revision ID: 421cd4ad5411
Revises: 9cc74d414209
Create Date: 2026-06-09 11:08:49.883922

NOTE on idempotency:
This migration was originally auto-generated and contained drops that
assumed certain tables/columns existed. In production, the previous
migration (9cc74d414209) was recorded as run but `sale_audit_log` did
not exist (likely manual intervention or partial state). To make this
migration safe in both fresh and partial-state databases, every drop
is now guarded with an existence check.

The actual schema goal of this migration:
  - Convert money columns from float (DOUBLE PRECISION) to Numeric(10,2)
    for proper decimal precision
  - Remove the unused backdating + audit-log feature (never used by app code)
  - Add a missing FK on sale_items.product_id

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '421cd4ad5411'
down_revision = '9cc74d414209'
branch_labels = None
depends_on = None


# ── Helpers for idempotent drops ──────────────────────────────────────────────
def _has_table(bind, table_name):
    return table_name in inspect(bind).get_table_names()


def _has_column(bind, table_name, column_name):
    if not _has_table(bind, table_name):
        return False
    cols = [c['name'] for c in inspect(bind).get_columns(table_name)]
    return column_name in cols


def _has_fk(bind, table_name, fk_name):
    if not _has_table(bind, table_name):
        return False
    fks = inspect(bind).get_foreign_keys(table_name)
    return any(fk.get('name') == fk_name for fk in fks)


def upgrade():
    bind = op.get_bind()

    # ── 1. Drop sale_audit_log only if it exists ───────────────────────────
    # Never used by app code. Safe to drop. May not exist in production due
    # to partial-state history.
    if _has_table(bind, 'sale_audit_log'):
        op.drop_table('sale_audit_log')

    # ── 2. Money columns: DOUBLE PRECISION → Numeric(10, 2) ────────────────
    # These tables/columns definitely exist (core schema), so no guards needed.
    with op.batch_alter_table('cash_advances', schema=None) as batch_op:
        batch_op.alter_column('amount',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=10, scale=2),
               existing_nullable=False)
        batch_op.alter_column('amount_returned',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=10, scale=2),
               existing_nullable=True)

    with op.batch_alter_table('debt_payments', schema=None) as batch_op:
        batch_op.alter_column('amount',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=10, scale=2),
               existing_nullable=False)

    with op.batch_alter_table('expenses', schema=None) as batch_op:
        batch_op.alter_column('amount',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=10, scale=2),
               existing_nullable=False)

    with op.batch_alter_table('mpesa_transactions', schema=None) as batch_op:
        batch_op.alter_column('amount',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=10, scale=2),
               existing_nullable=True)

    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.alter_column('price',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=10, scale=2),
               existing_nullable=False)
        batch_op.alter_column('unit_price',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=10, scale=2),
               existing_nullable=False)
        batch_op.alter_column('stock',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=10, scale=2),
               existing_nullable=False)

    # ── 3. sale_items: types + add missing FK ──────────────────────────────
    with op.batch_alter_table('sale_items', schema=None) as batch_op:
        batch_op.alter_column('quantity',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=10, scale=2),
               existing_nullable=False)
        batch_op.alter_column('price',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=10, scale=2),
               existing_nullable=False)
        batch_op.alter_column('profit',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=10, scale=2),
               existing_nullable=False)
        batch_op.create_foreign_key(
            'fk_sale_items_product_id', 'products', ['product_id'], ['id']
        )

    # ── 4. sales: types + drop unused backdating/audit columns (if present) ─
    with op.batch_alter_table('sales', schema=None) as batch_op:
        batch_op.alter_column('total_amount',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=10, scale=2),
               existing_nullable=False)
        batch_op.alter_column('amount_paid',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=10, scale=2),
               existing_nullable=False)
        batch_op.alter_column('change_given',
               existing_type=sa.DOUBLE_PRECISION(precision=53),
               type_=sa.Numeric(precision=10, scale=2),
               existing_nullable=False)

    # Drop foreign keys defensively (only if they exist).
    # We do this OUTSIDE the batch_alter_table block above because we need
    # to inspect the live DB, and batch_alter_table operates on a copy.
    if _has_fk(bind, 'sales', 'fk_sales_approved_by'):
        with op.batch_alter_table('sales', schema=None) as batch_op:
            batch_op.drop_constraint('fk_sales_approved_by', type_='foreignkey')

    if _has_fk(bind, 'sales', 'fk_sales_entered_by'):
        with op.batch_alter_table('sales', schema=None) as batch_op:
            batch_op.drop_constraint('fk_sales_entered_by', type_='foreignkey')

    # Drop columns defensively — each only if it exists.
    for col in [
        'entered_by_id',
        'approved_by_id',
        'backdate_reference',
        'backdate_reason',
        'is_backdated',
        'created_at',
    ]:
        if _has_column(bind, 'sales', col):
            with op.batch_alter_table('sales', schema=None) as batch_op:
                batch_op.drop_column(col)


def downgrade():
    """
    NOTE: This downgrade restores the schema as it was before this
    migration, including re-creating sale_audit_log and the backdating
    columns. It mirrors the original auto-generated downgrade. Data
    that was dropped in upgrade() cannot be restored.
    """
    bind = op.get_bind()

    with op.batch_alter_table('sales', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_at', postgresql.TIMESTAMP(), server_default=sa.text('now()'), autoincrement=False, nullable=False))
        batch_op.add_column(sa.Column('is_backdated', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False))
        batch_op.add_column(sa.Column('backdate_reason', sa.VARCHAR(length=255), autoincrement=False, nullable=True))
        batch_op.add_column(sa.Column('backdate_reference', sa.VARCHAR(length=100), autoincrement=False, nullable=True))
        batch_op.add_column(sa.Column('approved_by_id', sa.INTEGER(), autoincrement=False, nullable=True))
        batch_op.add_column(sa.Column('entered_by_id', sa.INTEGER(), autoincrement=False, nullable=True))
        batch_op.create_foreign_key('fk_sales_entered_by', 'users', ['entered_by_id'], ['id'])
        batch_op.create_foreign_key('fk_sales_approved_by', 'users', ['approved_by_id'], ['id'])
        batch_op.alter_column('change_given',
               existing_type=sa.Numeric(precision=10, scale=2),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=False)
        batch_op.alter_column('amount_paid',
               existing_type=sa.Numeric(precision=10, scale=2),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=False)
        batch_op.alter_column('total_amount',
               existing_type=sa.Numeric(precision=10, scale=2),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=False)

    with op.batch_alter_table('sale_items', schema=None) as batch_op:
        batch_op.drop_constraint('fk_sale_items_product_id', type_='foreignkey')
        batch_op.alter_column('profit',
               existing_type=sa.Numeric(precision=10, scale=2),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=False)
        batch_op.alter_column('price',
               existing_type=sa.Numeric(precision=10, scale=2),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=False)
        batch_op.alter_column('quantity',
               existing_type=sa.Numeric(precision=10, scale=2),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=False)

    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.alter_column('stock',
               existing_type=sa.Numeric(precision=10, scale=2),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=False)
        batch_op.alter_column('unit_price',
               existing_type=sa.Numeric(precision=10, scale=2),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=False)
        batch_op.alter_column('price',
               existing_type=sa.Numeric(precision=10, scale=2),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=False)

    with op.batch_alter_table('mpesa_transactions', schema=None) as batch_op:
        batch_op.alter_column('amount',
               existing_type=sa.Numeric(precision=10, scale=2),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=True)

    with op.batch_alter_table('expenses', schema=None) as batch_op:
        batch_op.alter_column('amount',
               existing_type=sa.Numeric(precision=10, scale=2),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=False)

    with op.batch_alter_table('debt_payments', schema=None) as batch_op:
        batch_op.alter_column('amount',
               existing_type=sa.Numeric(precision=10, scale=2),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=False)

    with op.batch_alter_table('cash_advances', schema=None) as batch_op:
        batch_op.alter_column('amount_returned',
               existing_type=sa.Numeric(precision=10, scale=2),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=True)
        batch_op.alter_column('amount',
               existing_type=sa.Numeric(precision=10, scale=2),
               type_=sa.DOUBLE_PRECISION(precision=53),
               existing_nullable=False)

    if not _has_table(bind, 'sale_audit_log'):
        op.create_table('sale_audit_log',
            sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
            sa.Column('sale_id', sa.INTEGER(), autoincrement=False, nullable=True),
            sa.Column('action', sa.VARCHAR(length=50), autoincrement=False, nullable=False),
            sa.Column('performed_by', sa.INTEGER(), autoincrement=False, nullable=False),
            sa.Column('performed_at', postgresql.TIMESTAMP(), server_default=sa.text('now()'), autoincrement=False, nullable=False),
            sa.Column('details', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
            sa.Column('ip_address', sa.VARCHAR(length=45), autoincrement=False, nullable=True),
            sa.ForeignKeyConstraint(['performed_by'], ['users.id'], name='fk_audit_performed_by'),
            sa.ForeignKeyConstraint(['sale_id'], ['sales.id'], name='fk_audit_sale', ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id', name='sale_audit_log_pkey')
        )