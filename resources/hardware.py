from flask import request
from flask_restful import Resource
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Sale, SaleItem, Product, User, Expense, CashAdvance
from extensions import db
from sqlalchemy import func, cast, Date, text
from sqlalchemy.orm import joinedload
from datetime import datetime, timedelta

HARDWARE_CATEGORY   = 'Hardware & Utilities'
LOW_STOCK_THRESHOLD = 1


def is_admin(user_id):
    user = User.query.get(user_id)
    return user and user.role == 'admin'


def hw_sale_ids_subquery():
    """Reusable subquery — hardware sale IDs only."""
    return (
        db.session.query(SaleItem.sale_id)
        .join(Product, SaleItem.product_id == Product.id)
        .filter(Product.category == HARDWARE_CATEGORY)
        .distinct()
        .scalar_subquery()
    )


def get_revenue_and_profit(date_filter=None, month_start=None):
    """
    Single SQL aggregation query — replaces all Python loops.
    date_filter  → filter to a specific date (today's stats)
    month_start  → filter from month_start onward (month stats)
    Neither      → all-time stats
    """
    q = (
        db.session.query(
            func.coalesce(func.sum(SaleItem.price * SaleItem.quantity), 0).label('revenue'),
            func.coalesce(
                func.sum((SaleItem.price - Product.unit_price) * SaleItem.quantity), 0
            ).label('profit'),
        )
        .join(Product, SaleItem.product_id == Product.id)
        .join(Sale,    SaleItem.sale_id    == Sale.id)
        .filter(
            Product.category    == HARDWARE_CATEGORY,
            Sale.payment_status != 'unpaid',
        )
    )
    if date_filter is not None:
        q = q.filter(cast(Sale.sale_date, Date) == date_filter)
    if month_start is not None:
        q = q.filter(cast(Sale.sale_date, Date) >= month_start)

    row = q.first()
    return {
        'revenue': float(row.revenue or 0),
        'profit':  float(row.profit  or 0),
    }


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 1 — HARDWARE DASHBOARD STATS
# ─────────────────────────────────────────────────────────────────────────────
class HardwareDashboardResource(Resource):
    """GET /hardware/dashboard-stats"""

    @jwt_required()
    def get(self):
        if not is_admin(int(get_jwt_identity())):
            return {"message": "Admin access required."}, 403

        today       = datetime.utcnow().date()
        month_start = today.replace(day=1)

        # ── Revenue & Profit — 3 SQL calls instead of 300+ ───────────────
        today_stats = get_revenue_and_profit(date_filter=today)
        month_stats = get_revenue_and_profit(month_start=month_start)
        all_stats   = get_revenue_and_profit()

        # ── Total owed by debtors — 1 query ──────────────────────────────
        hw_sale_ids = hw_sale_ids_subquery()

        total_owed = (
            db.session.query(
                func.coalesce(
                    func.sum(Sale.total_amount - Sale.amount_paid), 0
                )
            )
            .filter(
                Sale.id.in_(hw_sale_ids),
                Sale.payment_status.in_(['unpaid', 'partial']),
            )
            .scalar()
        )

        # ── Expenses — already aggregated correctly ───────────────────────
        today_expenses = (
            db.session.query(func.sum(Expense.amount))
            .filter(
                Expense.department == 'hardware',
                cast(Expense.expense_date, Date) == today,
            )
            .scalar() or 0
        )

        month_expenses = (
            db.session.query(func.sum(Expense.amount))
            .filter(
                Expense.department == 'hardware',
                cast(Expense.expense_date, Date) >= month_start,
            )
            .scalar() or 0
        )

        total_expenses = (
            db.session.query(func.sum(Expense.amount))
            .filter(Expense.department == 'hardware')
            .scalar() or 0
        )

        # ── Cash advances — 1 aggregation query ──────────────────────────
        advances_row = (
            db.session.query(
                func.count(CashAdvance.id).label('count'),
                func.coalesce(
                    func.sum(
                        CashAdvance.amount - func.coalesce(CashAdvance.amount_returned, 0)
                    ),
                    0,
                ).label('owed'),
            )
            .filter(
                CashAdvance.status.in_(['pending', 'partial']),
                CashAdvance.department == 'hardware',
            )
            .first()
        )

        # ── Low stock — small table, fine as-is ──────────────────────────
        low_stock = (
            Product.query.filter(
                Product.category == HARDWARE_CATEGORY,
                Product.stock    <= LOW_STOCK_THRESHOLD,
            )
            .order_by(Product.stock.asc())
            .all()
        )

        return {
            "today_revenue":   round(today_stats['revenue'],  2),
            "today_profit":    round(today_stats['profit'],   2),
            "month_revenue":   round(month_stats['revenue'],  2),
            "total_revenue":   round(all_stats['revenue'],    2),
            "total_profit":    round(all_stats['profit'],     2),
            "total_owed":      round(float(total_owed),       2),
            "today_expenses":  round(float(today_expenses),   2),
            "month_expenses":  round(float(month_expenses),   2),
            "total_expenses":  round(float(total_expenses),   2),
            "advances_owed":   round(float(advances_row.owed  or 0), 2),
            "advances_count":  advances_row.count or 0,
            "low_stock_count": len(low_stock),
            "low_stock_items": [
                {"id": p.id, "name": p.name, "stock": p.stock}
                for p in low_stock
            ],
        }, 200


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 2 — HARDWARE SALES TREND
# ─────────────────────────────────────────────────────────────────────────────
class HardwareSalesTrendResource(Resource):
    """GET /hardware/sales-trend?days=7"""

    @jwt_required()
    def get(self):
        if not is_admin(int(get_jwt_identity())):
            return {"message": "Admin access required."}, 403

        days  = int(request.args.get('days', 7))
        today = datetime.utcnow().date()
        start = today - timedelta(days=days - 1)

        # ── 1 query with GROUP BY instead of a Python loop ────────────────
        rows = (
            db.session.query(
                cast(Sale.sale_date, Date).label('day'),
                func.coalesce(
                    func.sum(SaleItem.price * SaleItem.quantity), 0
                ).label('revenue'),
                func.coalesce(
                    func.sum((SaleItem.price - Product.unit_price) * SaleItem.quantity), 0
                ).label('profit'),
            )
            .join(SaleItem, Sale.id == SaleItem.sale_id)
            .join(Product,  SaleItem.product_id == Product.id)
            .filter(
                Product.category    == HARDWARE_CATEGORY,
                Sale.payment_status != 'unpaid',
                cast(Sale.sale_date, Date) >= start,
            )
            .group_by(cast(Sale.sale_date, Date))
            .order_by(cast(Sale.sale_date, Date))
            .all()
        )

        # Build a lookup and fill missing days with 0
        row_map = {str(r.day): r for r in rows}
        result  = []
        for i in range(days - 1, -1, -1):
            day = today - timedelta(days=i)
            row = row_map.get(str(day))
            result.append({
                "date":    day.strftime('%b %d'),
                "revenue": round(float(row.revenue), 2) if row else 0,
                "profit":  round(float(row.profit),  2) if row else 0,
            })

        return result, 200


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 3 — HARDWARE SALES LIST
# ─────────────────────────────────────────────────────────────────────────────
class HardwareSalesResource(Resource):
    """GET /hardware/sales?date=2026-04-24&period=day|week|month"""

    @jwt_required()
    def get(self):
        if not is_admin(int(get_jwt_identity())):
            return {"message": "Admin access required."}, 403

        date_str = request.args.get('date')
        period   = request.args.get('period', 'day')

        hw_sale_ids = hw_sale_ids_subquery()

        query = Sale.query.filter(Sale.id.in_(hw_sale_ids))

        if date_str:
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                if period == 'day':
                    query = query.filter(cast(Sale.sale_date, Date) == target_date)
                elif period == 'week':
                    week_start = target_date - timedelta(days=target_date.weekday())
                    week_end   = week_start + timedelta(days=6)
                    query = query.filter(
                        cast(Sale.sale_date, Date) >= week_start,
                        cast(Sale.sale_date, Date) <= week_end,
                    )
                elif period == 'month':
                    query = query.filter(
                        cast(Sale.sale_date, Date) >= target_date.replace(day=1)
                    )
            except ValueError:
                return {"message": "Invalid date format. Use YYYY-MM-DD"}, 400

        sales = query.order_by(Sale.sale_date.desc()).all()
        return [s.to_dict() for s in sales], 200


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 4 — HARDWARE LOW STOCK
# ─────────────────────────────────────────────────────────────────────────────
class HardwareLowStockResource(Resource):
    """GET /hardware/low-stock"""

    @jwt_required()
    def get(self):
        if not is_admin(int(get_jwt_identity())):
            return {"message": "Admin access required."}, 403

        low_stock = (
            Product.query
            .filter(
                Product.category == HARDWARE_CATEGORY,
                Product.stock    <= LOW_STOCK_THRESHOLD,
            )
            .order_by(Product.stock.asc())
            .all()
        )

        out_of_stock = [p for p in low_stock if p.stock == 0]
        low          = [p for p in low_stock if 0 < p.stock <= LOW_STOCK_THRESHOLD]

        return {
            "out_of_stock": [
                {"id": p.id, "name": p.name, "stock": p.stock, "category": p.category}
                for p in out_of_stock
            ],
            "low_stock": [
                {"id": p.id, "name": p.name, "stock": p.stock, "category": p.category}
                for p in low
            ],
            "total_alerts": len(low_stock),
        }, 200