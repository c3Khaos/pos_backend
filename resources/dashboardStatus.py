from flask_restful import Resource
from models import User, SaleItem, Product, Sale, Expense, db
from sqlalchemy import func
from datetime import datetime, timezone,timedelta
from flask_jwt_extended import jwt_required


class DashboardInfo(Resource):
    @jwt_required()
    def get(self):
        try:
            # ── TODAY bounds in UTC, accounting for EAT (UTC+3) ─────────────────
            eat_offset  = timedelta(hours=3)
            now_eat     = datetime.now(timezone.utc) + eat_offset
            today_start = datetime(now_eat.year, now_eat.month, now_eat.day,
                                tzinfo=timezone.utc) - eat_offset
            today_end   = today_start + timedelta(days=1)
            month_start = datetime(now_eat.year, now_eat.month, 1,
                                tzinfo=timezone.utc) - eat_offset

            total_users    = db.session.query(User).count()
            total_products = db.session.query(Product).count()
            total_profit   = db.session.query(func.sum(SaleItem.profit)).scalar() or 0
            total_sales    = db.session.query(
                func.sum(SaleItem.price * SaleItem.quantity)
            ).scalar() or 0

            today_sales = db.session.query(func.sum(Sale.total_amount))\
                .filter(Sale.sale_date >= today_start, Sale.sale_date < today_end)\
                .scalar() or 0

            today_profit = db.session.query(func.sum(SaleItem.profit))\
                .join(Sale, Sale.id == SaleItem.sale_id)\
                .filter(Sale.sale_date >= today_start, Sale.sale_date < today_end)\
                .scalar() or 0

            today_expenses = db.session.query(func.sum(Expense.amount))\
                .filter(Expense.expense_date >= today_start,
                        Expense.expense_date <  today_end)\
                .scalar() or 0

            month_expenses = db.session.query(func.sum(Expense.amount))\
                .filter(Expense.expense_date >= month_start)\
                .scalar() or 0

            total_expenses = db.session.query(func.sum(Expense.amount)).scalar() or 0

            low_stock = Product.query.filter(Product.stock <= 5).all()

            return {
                "total_users":       total_users,
                "total_products":    total_products,
                "total_profit":      float(total_profit),
                "total_sales":       float(total_sales),
                "today_sales":       float(today_sales),
                "today_profit":      float(today_profit),
                "today_expenses":    float(today_expenses),
                "month_expenses":    float(month_expenses),
                "total_expenses":    float(total_expenses),
                "low_stock_products": [
                    {"id": p.id, "name": p.name, "stock": p.stock}
                    for p in low_stock
                ],
            }, 200

        except Exception as e:
            return {"message": f"Error fetching stats: {e}"}, 500