from flask import request
from flask_restful import Resource
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Sale, SaleItem, Product, Expense, User
from extensions import db
from sqlalchemy import func, cast, Date
from datetime import datetime, timezone, timedelta


def is_admin(user_id):
    user = User.query.get(user_id)
    return user and user.role == 'admin'


class ReportsResource(Resource):
    """GET /reports?type=best_sellers|profit_by_category|sales_by_period|cashier_performance
                  &period=day|week|month|year
                  &date=YYYY-MM-DD"""

    @jwt_required()
    def get(self):
        user_id = int(get_jwt_identity())
        if not is_admin(user_id):
            return {"message": "Admin access required."}, 403

        report_type = request.args.get('type', 'best_sellers')
        period      = request.args.get('period', 'month')

        # Calculate date range
        eat_offset = timedelta(hours=3)
        now_eat    = datetime.now(timezone.utc) + eat_offset
        today      = now_eat.date()

        if period == 'day':
            start_date = datetime(today.year, today.month, today.day,
                                  tzinfo=timezone.utc) - eat_offset
        elif period == 'week':
            week_start = today - timedelta(days=7)
            start_date = datetime(week_start.year, week_start.month, week_start.day,
                                  tzinfo=timezone.utc) - eat_offset
        elif period == 'year':
            start_date = datetime(today.year, 1, 1,
                                  tzinfo=timezone.utc) - eat_offset
        else:  # month
            start_date = datetime(today.year, today.month, 1,
                                  tzinfo=timezone.utc) - eat_offset

        # ── Best Sellers ──────────────────────────────────────────────────
        if report_type == 'best_sellers':
            results = db.session.query(
                Product.id,
                Product.name,
                Product.category,
                func.sum(SaleItem.quantity).label('total_qty'),
                func.sum(SaleItem.price * SaleItem.quantity).label('total_revenue'),
                func.sum(SaleItem.profit).label('total_profit'),
            ).join(
                SaleItem, SaleItem.product_id == Product.id
            ).join(
                Sale, Sale.id == SaleItem.sale_id
            ).filter(
                Sale.sale_date >= start_date
            ).group_by(
                Product.id, Product.name, Product.category
            ).order_by(
                func.sum(SaleItem.quantity).desc()
            ).limit(20).all()

            return {
                "type":   "best_sellers",
                "period": period,
                "data": [
                    {
                        "product_id":    r.id,
                        "name":          r.name,
                        "category":      r.category,
                        "quantity_sold": float(r.total_qty),
                        "revenue":       float(r.total_revenue),
                        "profit":        float(r.total_profit),
                    } for r in results
                ]
            }, 200

        # ── Profit by Category ─────────────────────────────────────────────
        if report_type == 'profit_by_category':
            results = db.session.query(
                Product.category,
                func.sum(SaleItem.quantity).label('total_qty'),
                func.sum(SaleItem.price * SaleItem.quantity).label('total_revenue'),
                func.sum(SaleItem.profit).label('total_profit'),
            ).join(
                SaleItem, SaleItem.product_id == Product.id
            ).join(
                Sale, Sale.id == SaleItem.sale_id
            ).filter(
                Sale.sale_date >= start_date
            ).group_by(
                Product.category
            ).order_by(
                func.sum(SaleItem.profit).desc()
            ).all()

            return {
                "type":   "profit_by_category",
                "period": period,
                "data": [
                    {
                        "category":      r.category,
                        "quantity_sold": float(r.total_qty),
                        "revenue":       float(r.total_revenue),
                        "profit":        float(r.total_profit),
                    } for r in results
                ]
            }, 200

        # ── Sales by Day (for chart) ──────────────────────────────────────
        if report_type == 'sales_by_period':
            days = 7 if period == 'week' else 30 if period == 'month' else 365

            results = []
            for i in range(days - 1, -1, -1):
                day = today - timedelta(days=i)
                day_start = datetime(day.year, day.month, day.day,
                                     tzinfo=timezone.utc) - eat_offset
                day_end   = day_start + timedelta(days=1)

                revenue = db.session.query(func.sum(Sale.total_amount))\
                    .filter(
                        Sale.sale_date >= day_start,
                        Sale.sale_date <  day_end,
                        Sale.payment_status == 'paid'
                    ).scalar() or 0

                profit = db.session.query(func.sum(SaleItem.profit))\
                    .join(Sale, Sale.id == SaleItem.sale_id)\
                    .filter(
                        Sale.sale_date >= day_start,
                        Sale.sale_date <  day_end,
                        Sale.payment_status == 'paid'
                    ).scalar() or 0

                results.append({
                    "date":    day.strftime('%b %d'),
                    "revenue": float(revenue),
                    "profit":  float(profit),
                })

            return {
                "type":   "sales_by_period",
                "period": period,
                "data":   results,
            }, 200

        # ── Cashier Performance ────────────────────────────────────────────
        if report_type == 'cashier_performance':
            results = db.session.query(
                User.id,
                User.username,
                func.count(Sale.id).label('sales_count'),
                func.sum(Sale.total_amount).label('total_revenue'),
            ).join(
                Sale, Sale.user_id == User.id
            ).filter(
                Sale.sale_date >= start_date
            ).group_by(
                User.id, User.username
            ).order_by(
                func.sum(Sale.total_amount).desc()
            ).all()

            return {
                "type":   "cashier_performance",
                "period": period,
                "data": [
                    {
                        "user_id":     r.id,
                        "username":    r.username,
                        "sales_count": r.sales_count,
                        "revenue":     float(r.total_revenue or 0),
                    } for r in results
                ]
            }, 200

        return {"message": "Unknown report type."}, 400