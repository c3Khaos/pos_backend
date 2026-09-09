from flask import request
from flask_restful import Resource
from models import User, SaleItem, Product, Sale, Expense, CashAdvance, db
from sqlalchemy import func
from datetime import datetime, timezone, timedelta
from flask_jwt_extended import jwt_required, get_jwt_identity


class DashboardInfo(Resource):

    @jwt_required()
    def get(self):
        try:
            eat_offset  = timedelta(hours=3)
            now_eat     = datetime.now(timezone.utc) + eat_offset
            today_start = datetime(now_eat.year, now_eat.month, now_eat.day,
                                   tzinfo=timezone.utc) - eat_offset
            today_end   = today_start + timedelta(days=1)
            month_start = datetime(now_eat.year, now_eat.month, 1,
                                   tzinfo=timezone.utc) - eat_offset

            # ── Metrics ────────────────────────────────────────────────────
            total_users    = db.session.query(User).count()
            total_products = db.session.query(Product).count()

            total_profit = db.session.query(func.sum(SaleItem.profit))\
                .scalar() or 0

            total_sales = db.session.query(func.sum(Sale.total_amount))\
                .filter(Sale.payment_status == 'paid')\
                .scalar() or 0

            today_sales = db.session.query(func.sum(Sale.total_amount))\
                .filter(
                    Sale.sale_date      >= today_start,
                    Sale.sale_date      <  today_end,
                    Sale.payment_status == 'paid',
                ).scalar() or 0

            today_profit = db.session.query(func.sum(SaleItem.profit))\
                .join(Sale, Sale.id == SaleItem.sale_id)\
                .filter(
                    Sale.sale_date >= today_start,
                    Sale.sale_date <  today_end,
                ).scalar() or 0

            today_expenses = db.session.query(func.sum(Expense.amount))\
                .filter(
                    Expense.expense_date >= today_start,
                    Expense.expense_date <  today_end,
                ).scalar() or 0

            month_expenses = db.session.query(func.sum(Expense.amount))\
                .filter(Expense.expense_date >= month_start)\
                .scalar() or 0

            total_expenses = db.session.query(func.sum(Expense.amount))\
                .scalar() or 0

            low_stock = Product.query.filter(Product.stock <= 5).all()

            advances = CashAdvance.query.filter(
                CashAdvance.status.in_(['pending', 'partial'])
            ).all()

            advances_owed  = sum(
                a.amount - (a.amount_returned or 0) for a in advances
            )
            advances_count = len(advances)

            return {
                "total_users":        total_users,
                "total_products":     total_products,
                "total_profit":       float(total_profit),
                "total_sales":        float(total_sales),
                "today_sales":        float(today_sales),
                "today_profit":       float(today_profit),
                "today_expenses":     float(today_expenses),
                "month_expenses":     float(month_expenses),
                "total_expenses":     float(total_expenses),
                "low_stock_products": [
                    {"id": p.id, "name": p.name, "stock": float(p.stock)}
                    for p in low_stock
                ],
                "advances_owed":  round(float(advances_owed), 2),
                "advances_count": advances_count,
            }, 200

        except Exception as e:
            return {"message": f"Error fetching stats: {str(e)}"}, 500