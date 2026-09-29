# services/report_service.py
from datetime import datetime, date
from sqlalchemy import func, desc
from models import db, Sale, SaleItem, Product, Expense, User


def get_recipient_emails(tenant_id: int) -> list:
    """
    Admin emails for a SINGLE tenant only.
    SECURITY: scoping to tenant_id ensures one shop's report never goes to
    another shop's admins.
    """
    users = db.session.query(User.email).filter(
        User.tenant_id == tenant_id,
        User.role == "admin",
        User.active.is_(True),
        User.email.isnot(None),
        User.email != "",
    ).all()
    return [u.email for u in users]


def get_daily_report_data(tenant_id: int, report_date: date = None) -> dict:
    """
    Compile the daily report for ONE tenant.
    Every query is filtered by tenant_id so the numbers reflect only that shop.
    """
    if report_date is None:
        report_date = date.today()

    day_start = datetime.combine(report_date, datetime.min.time())
    day_end   = datetime.combine(report_date, datetime.max.time())

    # ── Sales summary (this tenant) ───────────────────────────────────────
    sales_query = db.session.query(
        func.count(Sale.id).label("total_transactions"),
        func.coalesce(func.sum(Sale.total_amount), 0).label("total_revenue"),
    ).filter(
        Sale.tenant_id == tenant_id,
        Sale.sale_date >= day_start,
        Sale.sale_date <= day_end,
    ).first()

    # ── Profit — join Sale, both scoped to tenant ─────────────────────────
    profit_query = db.session.query(
        func.coalesce(func.sum(SaleItem.profit), 0).label("total_profit")
    ).join(
        Sale, Sale.id == SaleItem.sale_id
    ).filter(
        Sale.tenant_id     == tenant_id,
        SaleItem.tenant_id == tenant_id,
        Sale.sale_date >= day_start,
        Sale.sale_date <= day_end,
    ).first()

    # ── Expenses (this tenant) ────────────────────────────────────────────
    expenses_query = db.session.query(
        func.coalesce(func.sum(Expense.amount), 0).label("total_expenses")
    ).filter(
        Expense.tenant_id    == tenant_id,
        Expense.expense_date >= day_start,
        Expense.expense_date <= day_end,
    ).first()

    # ── Top 10 selling products (this tenant) ─────────────────────────────
    top_products = db.session.query(
        Product.name,
        Product.category,
        func.sum(SaleItem.quantity).label("qty_sold"),
        func.sum(SaleItem.quantity * SaleItem.price).label("revenue"),
    ).join(
        SaleItem, SaleItem.product_id == Product.id
    ).join(
        Sale, Sale.id == SaleItem.sale_id
    ).filter(
        Sale.tenant_id     == tenant_id,
        SaleItem.tenant_id == tenant_id,
        Product.tenant_id  == tenant_id,
        Sale.sale_date >= day_start,
        Sale.sale_date <= day_end,
    ).group_by(
        Product.id, Product.name, Product.category
    ).order_by(
        desc("qty_sold")
    ).limit(10).all()

    # ── Low stock (this tenant) ───────────────────────────────────────────
    low_stock = db.session.query(
        Product.name, Product.category, Product.stock,
    ).filter(
        Product.tenant_id == tenant_id,
        Product.stock > 0,
        Product.stock <= 5,
    ).order_by(Product.stock.asc()).all()

    # ── Out of stock (this tenant) ────────────────────────────────────────
    out_of_stock = db.session.query(
        Product.name, Product.category,
    ).filter(
        Product.tenant_id == tenant_id,
        Product.stock == 0,
    ).order_by(Product.name.asc()).all()

    gross_profit   = float(profit_query.total_profit)
    total_expenses = float(expenses_query.total_expenses)
    net_profit     = gross_profit - total_expenses

    return {
        "tenant_id": tenant_id,
        "date": report_date.strftime("%A, %d %B %Y"),
        "summary": {
            "transactions": sales_query.total_transactions or 0,
            "revenue":      float(sales_query.total_revenue),
            "gross_profit": gross_profit,
            "expenses":     total_expenses,
            "net_profit":   net_profit,
        },
        "top_products": [
            {
                "name":     row.name,
                "category": row.category,
                "qty_sold": float(row.qty_sold),
                "revenue":  float(row.revenue),
            }
            for row in top_products
        ],
        "low_stock":    [{"name": r.name, "category": r.category, "stock": r.stock} for r in low_stock],
        "out_of_stock": [{"name": r.name, "category": r.category} for r in out_of_stock],
    }