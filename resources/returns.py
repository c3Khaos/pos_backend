from flask import request
from flask_restful import Resource
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import StockReturn, Product, Sale, SaleItem, User
from extensions import db
from datetime import datetime, timezone, timedelta
from sqlalchemy import func


def is_admin(user_id):
    user = User.query.get(user_id)
    return user and user.role == 'admin'


class ReturnListResource(Resource):

    @jwt_required()
    def get(self):
        user_id = int(get_jwt_identity())
        if not is_admin(user_id):
            return {"message": "Admin access required."}, 403

        returns = StockReturn.query.order_by(StockReturn.returned_at.desc()).all()

        eat_offset  = timedelta(hours=3)
        now_eat     = datetime.now(timezone.utc) + eat_offset
        today_start = datetime(now_eat.year, now_eat.month, now_eat.day,
                               tzinfo=timezone.utc) - eat_offset
        today_end   = today_start + timedelta(days=1)

        today_total = db.session.query(func.sum(StockReturn.refund_amount))\
            .filter(
                StockReturn.returned_at >= today_start,
                StockReturn.returned_at <  today_end,
            ).scalar() or 0

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
            # ── 1. Stock goes back up ─────────────────────────────────────
            product.stock = float(product.stock) + quantity

            # ── 2. Update original sale if sale_id provided ───────────────
            if sale_id:
                sale = Sale.query.get(sale_id)
                if sale:
                    # Find the matching SaleItem
                    sale_item = SaleItem.query.filter_by(
                        sale_id    = sale_id,
                        product_id = product_id,
                    ).first()

                    if sale_item:
                        returned_qty      = float(quantity)
                        sale_item_qty     = float(sale_item.quantity)
                        item_unit_price   = float(sale_item.price)
                        item_unit_profit  = float(sale_item.profit) / sale_item_qty \
                                           if sale_item_qty > 0 else 0

                        if returned_qty >= sale_item_qty:
                            # Full return of this item — remove SaleItem entirely
                            db.session.delete(sale_item)
                        else:
                            # Partial return — reduce quantity and profit
                            sale_item.quantity = sale_item_qty - returned_qty
                            sale_item.profit   = item_unit_profit * (sale_item_qty - returned_qty)

                    # ── 3. Deduct refund from sale total ──────────────────
                    old_total         = float(sale.total_amount)
                    sale.total_amount = max(old_total - refund_amount, 0)

                    # ── 4. Adjust amount_paid proportionally ──────────────
                    old_paid         = float(sale.amount_paid)
                    sale.amount_paid = max(old_paid - refund_amount, 0)

                    # ── 5. Recalculate change ─────────────────────────────
                    sale.change_given = max(
                        float(sale.amount_paid) - float(sale.total_amount), 0
                    )

                    # ── 6. Mark sale as fully returned if total hits 0 ────
                    if float(sale.total_amount) <= 0:
                        sale.payment_status = 'returned'

            # ── 7. Create StockReturn audit record ────────────────────────
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

            return {
                **stock_return.to_dict(),
                "sale_updated": sale_id is not None,
                "new_sale_total": float(sale.total_amount) if sale_id and sale else None,
            }, 201

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

        try:
            # ── 1. Reverse stock ──────────────────────────────────────────
            product = Product.query.get(stock_return.product_id)
            if product:
                product.stock = float(product.stock) - stock_return.quantity

            # ── 2. Reverse sale changes if sale_id exists ─────────────────
            if stock_return.sale_id:
                sale = Sale.query.get(stock_return.sale_id)
                if sale:
                    # Add refund amount back to sale total
                    sale.total_amount = float(sale.total_amount) + float(stock_return.refund_amount)
                    sale.amount_paid  = float(sale.amount_paid)  + float(stock_return.refund_amount)
                    sale.change_given = max(
                        float(sale.amount_paid) - float(sale.total_amount), 0
                    )

                    # Restore sale status if it was marked returned
                    if sale.payment_status == 'returned':
                        sale.payment_status = 'paid'

                    # Restore the SaleItem quantity
                    sale_item = SaleItem.query.filter_by(
                        sale_id    = stock_return.sale_id,
                        product_id = stock_return.product_id,
                    ).first()

                    if sale_item:
                        # Item still exists — add quantity back
                        sale_item.quantity = float(sale_item.quantity) + stock_return.quantity
                    else:
                        # Item was fully deleted — we can't fully restore it
                        # without the original price. Log it but don't crash.
                        pass

            db.session.delete(stock_return)
            db.session.commit()
            return {"message": "Return deleted, sale and stock restored."}, 200

        except Exception as e:
            db.session.rollback()
            return {"message": f"Error: {str(e)}"}, 500