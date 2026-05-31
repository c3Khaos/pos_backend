# services/report_service.py
from datetime import datetime, date
from sqlalchemy import func, desc
from models import db, Sale, SaleItem, Product, Expense, User


def get_recipient_emails() -> list[str]:
    """Fetch all user emails. Add .filter(User.role == 'admin') if you only want admins."""
    users = db.session.query(User.email).filter(
        User.email.isnot(None),
        User.email != "",
    ).all()
    return [u.email for u in users]


def get_daily_report_data(report_date: date = None) -> dict:
    if report_date is None:
        report_date = date.today()

    day_start = datetime.combine(report_date, datetime.min.time())
    day_end   = datetime.combine(report_date, datetime.max.time())

    # ── Sales summary: transactions + revenue come from Sale ──
    sales_query = db.session.query(
        func.count(Sale.id).label("total_transactions"),
        func.coalesce(func.sum(Sale.total_amount), 0).label("total_revenue"),
    ).filter(
        Sale.sale_date >= day_start,
        Sale.sale_date <= day_end,
    ).first()

    # ── Profit lives on SaleItem — sum across all items in today's sales ──
    profit_query = db.session.query(
        func.coalesce(func.sum(SaleItem.profit), 0).label("total_profit")
    ).join(
        Sale, Sale.id == SaleItem.sale_id
    ).filter(
        Sale.sale_date >= day_start,
        Sale.sale_date <= day_end,
    ).first()

    # ── Expenses ──
    expenses_query = db.session.query(
        func.coalesce(func.sum(Expense.amount), 0).label("total_expenses")
    ).filter(
        Expense.expense_date >= day_start,
        Expense.expense_date <= day_end,
    ).first()

    # ── Top 10 selling products today ──
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
        Sale.sale_date >= day_start,
        Sale.sale_date <= day_end,
    ).group_by(
        Product.id, Product.name, Product.category
    ).order_by(
        desc("qty_sold")
    ).limit(10).all()

    # ── Low stock (1–5) ──
    low_stock = db.session.query(
        Product.name, Product.category, Product.stock,
    ).filter(
        Product.stock > 0,
        Product.stock <= 5,
    ).order_by(Product.stock.asc()).all()

    # ── Out of stock ──
    out_of_stock = db.session.query(
        Product.name, Product.category,
    ).filter(
        Product.stock == 0
    ).order_by(Product.name.asc()).all()

    gross_profit   = float(profit_query.total_profit)
    total_expenses = float(expenses_query.total_expenses)
    net_profit     = gross_profit - total_expenses

    return {
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