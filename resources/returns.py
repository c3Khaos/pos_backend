from flask import request
from flask_restful import Resource
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import StockReturn, Product, Sale, User
from extensions import db
from datetime import datetime, timezone, timedelta
from sqlalchemy import func


def is_admin(user_id):
    user = User.query.get(user_id)
    return user and user.role == 'admin'


class ReturnListResource(Resource):
    """GET /returns — list all returns
       POST /returns — record a return"""

    @jwt_required()
    def get(self):
        user_id = int(get_jwt_identity())
        if not is_admin(user_id):
            return {"message": "Admin access required."}, 403

        returns = StockReturn.query.order_by(StockReturn.returned_at.desc()).all()

        # Summary
        eat_offset = timedelta(hours=3)
        now_eat    = datetime.now(timezone.utc) + eat_offset
        today_start = datetime(now_eat.year, now_eat.month, now_eat.day,
                               tzinfo=timezone.utc) - eat_offset
        today_end   = today_start + timedelta(days=1)

        today_total = db.session.query(func.sum(StockReturn.refund_amount))\
            .filter(StockReturn.returned_at >= today_start,
                    StockReturn.returned_at <  today_end)\
            .scalar() or 0

        return {
            "returns":     [r.to_dict() for r in returns],
            "today_total": float(today_total),
            "total_count": len(returns),
        }, 200

    @jwt_required()
    def post(self):
        user_id = int(get_jwt_identity())
        if not is_admin(user_id):
            return {"message": "Admin access required."}, 403

        data = request.get_json()

        product_id    = data.get('product_id')
        quantity      = data.get('quantity')
        refund_amount = data.get('refund_amount')
        reason        = data.get('reason', '').strip()
        refund_method = data.get('refund_method', 'cash')
        sale_id       = data.get('sale_id')

        if not product_id or not quantity or refund_amount is None:
            return {"message": "Product, quantity and refund amount required."}, 400

        try:
            quantity      = int(quantity)
            refund_amount = float(refund_amount)
            if quantity <= 0 or refund_amount < 0:
                return {"message": "Invalid quantity or refund amount."}, 400
        except (TypeError, ValueError):
            return {"message": "Invalid numbers."}, 400

        product = Product.query.get(product_id)
        if not product:
            return {"message": "Product not found."}, 404

        try:
            # Stock goes back up
            product.stock = float(product.stock) + quantity

            stock_return = StockReturn(
                sale_id       = sale_id,
                product_id    = product_id,
                product_name  = product.name,
                quantity      = quantity,
                refund_amount = refund_amount,
                reason        = reason or None,
                refund_method = refund_method,
                recorded_by   = user_id,
            )
            db.session.add(stock_return)
            db.session.commit()
            return stock_return.to_dict(), 201

        except Exception as e:
            db.session.rollback()
            return {"message": f"Error: {str(e)}"}, 500


class ReturnResource(Resource):

    @jwt_required()
    def delete(self, return_id):
        user_id = int(get_jwt_identity())
        if not is_admin(user_id):
            return {"message": "Admin access required."}, 403

        stock_return = StockReturn.query.get_or_404(return_id)

        # Reverse stock — return was wrong, deduct again
        product = Product.query.get(stock_return.product_id)
        if product:
            product.stock = float(product.stock) - stock_return.quantity

        db.session.delete(stock_return)
        db.session.commit()
        return {"message": "Return deleted, stock adjusted"}, 200