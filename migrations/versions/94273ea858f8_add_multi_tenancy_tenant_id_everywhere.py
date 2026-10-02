"""add multi-tenancy tenant_id everywhere

Revision ID: 94273ea858f8
Revises: c84844bae900
Create Date: 2026-09-29 16:40:56.922369

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '94273ea858f8'
down_revision = 'c84844bae900'
branch_labels = None
depends_on = None


def upgrade():
    # ═══════════════════════════════════════════════════════════════════════
    # 1. Create the tenants table
    # ═══════════════════════════════════════════════════════════════════════
    op.create_table('tenants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('slug', sa.String(length=60), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=True),
        sa.Column('email', sa.String(length=120), nullable=True),
        sa.Column('plan', sa.String(length=20), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('tenants', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tenants_slug'), ['slug'], unique=True)

    # ═══════════════════════════════════════════════════════════════════════
    # 2. Insert tenant 1 — all existing production data becomes CountyStar's.
    #    This row IS the real client; every existing row is preserved under it.
    # ═══════════════════════════════════════════════════════════════════════
    op.execute("""
        INSERT INTO tenants (id, name, slug, plan, is_active, created_at)
        VALUES (1, 'CountyStar Electrical', 'countystar', 'starter', true, now())
    """)

    # Tables that get a NOT-NULL tenant_id (everything except mpesa_transactions)
    not_null_tables = [
        'cash_advances', 'cash_reconciliations', 'categories', 'debt_payments',
        'expenses', 'products', 'restocks', 'sale_items', 'sales',
        'shop_settings', 'stock_returns', 'suppliers', 'users',
    ]

    # ═══════════════════════════════════════════════════════════════════════
    # 3. Add tenant_id NULLABLE, backfill = 1, then set NOT NULL.
    #    This order avoids the "column contains null values" crash.
    # ═══════════════════════════════════════════════════════════════════════
    for table in not_null_tables:
        op.add_column(table, sa.Column('tenant_id', sa.Integer(), nullable=True))
        op.execute(f"UPDATE {table} SET tenant_id = 1")
        op.alter_column(table, 'tenant_id', nullable=False)
        op.create_index(op.f(f'ix_{table}_tenant_id'), table, ['tenant_id'], unique=False)
        op.create_foreign_key(f'fk_{table}_tenant', table, 'tenants', ['tenant_id'], ['id'])

    # mpesa_transactions — tenant_id is NULLABLE (webhooks may arrive w/o tenant)
    op.add_column('mpesa_transactions', sa.Column('tenant_id', sa.Integer(), nullable=True))
    op.execute("UPDATE mpesa_transactions SET tenant_id = 1")  # backfill existing rows
    op.create_index(op.f('ix_mpesa_transactions_tenant_id'), 'mpesa_transactions', ['tenant_id'], unique=False)
    op.create_foreign_key('fk_mpesa_transactions_tenant', 'mpesa_transactions', 'tenants', ['tenant_id'], ['id'])

    # ═══════════════════════════════════════════════════════════════════════
    # 4. Swap unique constraints: drop old global ones, add per-tenant ones
    # ═══════════════════════════════════════════════════════════════════════

    # users — username/email now unique per tenant
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('email', existing_type=sa.VARCHAR(length=80), nullable=True)
        batch_op.drop_constraint('users_email_key', type_='unique')
        batch_op.drop_constraint('users_username_key', type_='unique')
        batch_op.create_unique_constraint('uq_user_tenant_email', ['tenant_id', 'email'])
        batch_op.create_unique_constraint('uq_user_tenant_username', ['tenant_id', 'username'])

    # products — barcode now unique per tenant (drop global unique index)
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_index('ix_products_barcode')
        batch_op.create_index(batch_op.f('ix_products_barcode'), ['barcode'], unique=False)
        batch_op.create_unique_constraint('uq_product_tenant_barcode', ['tenant_id', 'barcode'])

    # sales — transaction_id now unique per tenant; add sale_date index
    with op.batch_alter_table('sales', schema=None) as batch_op:
        batch_op.drop_index('ix_sales_transaction_id')
        batch_op.create_index(batch_op.f('ix_sales_transaction_id'), ['transaction_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_sales_sale_date'), ['sale_date'], unique=False)
        batch_op.create_unique_constraint('uq_sale_tenant_txn', ['tenant_id', 'transaction_id'])

    # categories — name now unique per tenant
    with op.batch_alter_table('categories', schema=None) as batch_op:
        batch_op.drop_constraint('categories_name_key', type_='unique')
        batch_op.create_unique_constraint('uq_category_tenant_name', ['tenant_id', 'name'])

    # cash_reconciliations — date now unique per tenant
    with op.batch_alter_table('cash_reconciliations', schema=None) as batch_op:
        batch_op.drop_constraint('cash_reconciliations_reconciled_date_key', type_='unique')
        batch_op.create_unique_constraint('uq_recon_tenant_date', ['tenant_id', 'reconciled_date'])

    # shop_settings — one row per tenant (make the tenant_id index unique)
    with op.batch_alter_table('shop_settings', schema=None) as batch_op:
        batch_op.drop_index('ix_shop_settings_tenant_id')
        batch_op.create_index('ix_shop_settings_tenant_id', ['tenant_id'], unique=True)

    # ═══════════════════════════════════════════════════════════════════════
    # 5. Bump tenants id sequence past 1 so the next onboarded shop doesn't
    #    collide with the CountyStar row inserted with id=1.
    # ═══════════════════════════════════════════════════════════════════════
    op.execute("SELECT setval('tenants_id_seq', (SELECT MAX(id) FROM tenants))")
    # ### end Alembic commands ###


def downgrade():
    # Reverse order — drop constraints, indexes, columns, then the table.
    with op.batch_alter_table('shop_settings', schema=None) as batch_op:
        batch_op.drop_index('ix_shop_settings_tenant_id')
        batch_op.create_index('ix_shop_settings_tenant_id', ['tenant_id'], unique=False)

    with op.batch_alter_table('cash_reconciliations', schema=None) as batch_op:
        batch_op.drop_constraint('uq_recon_tenant_date', type_='unique')
        batch_op.create_unique_constraint('cash_reconciliations_reconciled_date_key', ['reconciled_date'])

    with op.batch_alter_table('categories', schema=None) as batch_op:
        batch_op.drop_constraint('uq_category_tenant_name', type_='unique')
        batch_op.create_unique_constraint('categories_name_key', ['name'])

    with op.batch_alter_table('sales', schema=None) as batch_op:
        batch_op.drop_constraint('uq_sale_tenant_txn', type_='unique')
        batch_op.drop_index(batch_op.f('ix_sales_sale_date'))
        batch_op.drop_index(batch_op.f('ix_sales_transaction_id'))
        batch_op.create_index('ix_sales_transaction_id', ['transaction_id'], unique=True)

    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_constraint('uq_product_tenant_barcode', type_='unique')
        batch_op.drop_index(batch_op.f('ix_products_barcode'))
        batch_op.create_index('ix_products_barcode', ['barcode'], unique=True)

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('uq_user_tenant_username', type_='unique')
        batch_op.drop_constraint('uq_user_tenant_email', type_='unique')
        batch_op.create_unique_constraint('users_username_key', ['username'])
        batch_op.create_unique_constraint('users_email_key', ['email'])
        batch_op.alter_column('email', existing_type=sa.VARCHAR(length=80), nullable=False)

    # Drop tenant_id from all tables
    all_tables = [
        'cash_advances', 'cash_reconciliations', 'categories', 'debt_payments',
        'expenses', 'mpesa_transactions', 'products', 'restocks', 'sale_items',
        'sales', 'shop_settings', 'stock_returns', 'suppliers', 'users',
    ]
    for table in all_tables:
        try:
            op.drop_constraint(f'fk_{table}_tenant', table, type_='foreignkey')
        except Exception:
            pass
        op.drop_index(op.f(f'ix_{table}_tenant_id'), table_name=table)
        op.drop_column(table, 'tenant_id')

    with op.batch_alter_table('tenants', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tenants_slug'))
    op.drop_table('tenants')
    # ### end Alembic commands ###