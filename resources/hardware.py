# resources/hardware.py
from flask import request, current_app
from flask_restful import Resource
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Sale, SaleItem, Product, User, Expense, Supplier
from extensions import db
from sqlalchemy import func, cast, Date
from datetime import datetime, timedelta

HARDWARE_CATEGORY = 'Hardware & Utilities'
LOW_STOCK_THRESHOLD = 5

def is_admin(user_id):
    user = User.query.get(user_id)
    return user and user.role == 'admin'


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 1 — HARDWARE DASHBOARD STATS
# ─────────────────────────────────────────────────────────────────────────────
class HardwareDashboardResource(Resource):
    """GET /hardware/dashboard-stats"""

    @jwt_required()
    def get(self):
        if not is_admin(get_jwt_identity()):
            return {"message": "Admin access required."}, 403

        today     = datetime.utcnow().date()
        month_start = today.replace(day=1)

        # ── Get all sale IDs that contain hardware products ───────────────
        hardware_sale_ids = db.session.query(SaleItem.sale_id).join(
            Product, SaleItem.product_id == Product.id
        ).filter(
            Product.category == HARDWARE_CATEGORY
        ).distinct().subquery()

        hardware_sales = Sale.query.filter(
            Sale.id.in_(hardware_sale_ids),
            Sale.payment_status != 'unpaid'
        )

        # ── Today's sales ─────────────────────────────────────────────────
        today_sales = hardware_sales.filter(
            cast(Sale.sale_date, Date) == today
        ).all()

        today_revenue = sum(s.total_amount for s in today_sales)
        today_profit  = sum(
            (item.price - item.price / (1 + ((item.price - item.price) or 1)))
            for s in today_sales for item in s.items
        )

        # Calculate profit properly from sale items
        today_profit = 0
        for sale in today_sales:
            for item in sale.items:
                product = Product.query.get(item.product_id)
                if product:
                    profit = (item.price - product.unit_price) * item.quantity
                    today_profit += profit

        # ── Total all-time ─────────────────────────────────────────────────
        all_sales   = hardware_sales.all()
        total_revenue = sum(s.total_amount for s in all_sales)
        total_profit  = 0
        for sale in all_sales:
            for item in sale.items:
                product = Product.query.get(item.product_id)
                if product:
                    total_profit += (item.price - product.unit_price) * item.quantity

        # ── This month ───────────────────────────────────────────────────
        month_sales   = hardware_sales.filter(
            cast(Sale.sale_date, Date) >= month_start
        ).all()
        month_revenue = sum(s.total_amount for s in month_sales)

        # ── Low stock hardware products ───────────────────────────────────
        low_stock = Product.query.filter(
            Product.category == HARDWARE_CATEGORY,
            Product.stock    <= LOW_STOCK_THRESHOLD
        ).all()

        # ── Hardware debtors ──────────────────────────────────────────────
        hardware_credit_sales = Sale.query.filter(
            Sale.id.in_(hardware_sale_ids),
            Sale.payment_status.in_(['unpaid', 'partial'])
        ).all()

        total_owed = sum(
            s.total_amount - s.amount_paid
            for s in hardware_credit_sales
        )

        return {
            "today_revenue":   round(today_revenue, 2),
            "today_profit":    round(today_profit, 2),
            "month_revenue":   round(month_revenue, 2),
            "total_revenue":   round(total_revenue, 2),
            "total_profit":    round(total_profit, 2),
            "total_owed":      round(total_owed, 2),
            "low_stock_count": len(low_stock),
            "low_stock_items": [
                {
                    "id":    p.id,
                    "name":  p.name,
                    "stock": p.stock,
                }
                for p in low_stock
            ],
        }, 200


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 2 — HARDWARE SALES TREND (for graph)
# ─────────────────────────────────────────────────────────────────────────────
class HardwareSalesTrendResource(Resource):
    """GET /hardware/sales-trend"""

    @jwt_required()
    def get(self):
        if not is_admin(get_jwt_identity()):
            return {"message": "Admin access required."}, 403

        days = int(request.args.get('days', 7))

        hardware_sale_ids = db.session.query(SaleItem.sale_id).join(
            Product, SaleItem.product_id == Product.id
        ).filter(
            Product.category == HARDWARE_CATEGORY
        ).distinct().subquery()

        result = []
        today  = datetime.utcnow().date()

        for i in range(days - 1, -1, -1):
            day      = today - timedelta(days=i)
            day_sales = Sale.query.filter(
                Sale.id.in_(hardware_sale_ids),
                Sale.payment_status != 'unpaid',
                cast(Sale.sale_date, Date) == day
            ).all()

            revenue = sum(s.total_amount for s in day_sales)
            profit  = 0
            for sale in day_sales:
                for item in sale.items:
                    product = Product.query.get(item.product_id)
                    if product:
                        profit += (item.price - product.unit_price) * item.quantity

            result.append({
                "date":    day.strftime('%b %d'),
                "revenue": round(revenue, 2),
                "profit":  round(profit, 2),
            })

        return result, 200


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 3 — HARDWARE SALES LIST (filtered by date)
# ─────────────────────────────────────────────────────────────────────────────
class HardwareSalesResource(Resource):
    """GET /hardware/sales?date=2026-04-24"""

    @jwt_required()
    def get(self):
        if not is_admin(get_jwt_identity()):
            return {"message": "Admin access required."}, 403

        date_str = request.args.get('date')
        period   = request.args.get('period', 'day')  # day | week | month

        hardware_sale_ids = db.session.query(SaleItem.sale_id).join(
            Product, SaleItem.product_id == Product.id
        ).filter(
            Product.category == HARDWARE_CATEGORY
        ).distinct().subquery()

        query = Sale.query.filter(Sale.id.in_(hardware_sale_ids))

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
                        cast(Sale.sale_date, Date) <= week_end
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
# ENDPOINT 4 — HARDWARE LOW STOCK ALERTS
# ─────────────────────────────────────────────────────────────────────────────
class HardwareLowStockResource(Resource):
    """GET /hardware/low-stock"""

    @jwt_required()
    def get(self):
        if not is_admin(get_jwt_identity()):
            return {"message": "Admin access required."}, 403

        low_stock = Product.query.filter(
            Product.category == HARDWARE_CATEGORY,
            Product.stock    <= LOW_STOCK_THRESHOLD
        ).order_by(Product.stock.asc()).all()

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