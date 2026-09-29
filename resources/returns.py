from flask import request
from flask_restful import Resource
from flask_jwt_extended import jwt_required
from models import StockReturn, Product, Sale, SaleItem
from extensions import db
from datetime import datetime, timezone, timedelta
from sqlalchemy import func
from utils.tenant import get_tenant_id, current_user_and_tenant, is_admin


class ReturnListResource(Resource):

    @jwt_required()
    def get(self):
        tenant_id = get_tenant_id()
        if not is_admin():
            return {"message": "Admin access required."}, 403

        returns = StockReturn.query.filter_by(tenant_id=tenant_id)\
            .order_by(StockReturn.returned_at.desc()).all()

        eat_offset  = timedelta(hours=3)
        now_eat     = datetime.now(timezone.utc) + eat_offset
        today_start = datetime(now_eat.year, now_eat.month, now_eat.day,
                               tzinfo=timezone.utc) - eat_offset
        today_end   = today_start + timedelta(days=1)

        today_total = db.session.query(func.sum(StockReturn.refund_amount))\
            .filter(
                StockReturn.tenant_id   == tenant_id,
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
        user, tenant_id = current_user_and_tenant()
        if not user or user.role != "admin":
            return {"message": "Admin access required."}, 403

        data          = request.get_json() or {}
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

        # ── SECURITY: product must belong to this tenant ──────────────────
        product = Product.query.filter_by(
            id=product_id, tenant_id=tenant_id
        ).first()
        if not product:
            return {"message": "Product not found."}, 404

        try:
            product.stock = float(product.stock) + quantity

            sale = None
            if sale_id:
                # ── Sale must belong to this tenant too ───────────────────
                sale = Sale.query.filter_by(id=sale_id, tenant_id=tenant_id).first()
                if sale:
                    sale_item = SaleItem.query.filter_by(
                        tenant_id=tenant_id, sale_id=sale_id, product_id=product_id
                    ).first()

                    if sale_item:
                        returned_qty     = float(quantity)
                        sale_item_qty    = float(sale_item.quantity)
                        item_unit_profit = float(sale_item.profit) / sale_item_qty \
                                           if sale_item_qty > 0 else 0

                        if returned_qty >= sale_item_qty:
                            db.session.delete(sale_item)
                        else:
                            sale_item.quantity = sale_item_qty - returned_qty
                            sale_item.profit   = item_unit_profit * (sale_item_qty - returned_qty)

                    old_total         = float(sale.total_amount)
                    sale.total_amount = max(old_total - refund_amount, 0)
                    old_paid          = float(sale.amount_paid)
                    sale.amount_paid  = max(old_paid - refund_amount, 0)
                    sale.change_given = max(
                        float(sale.amount_paid) - float(sale.total_amount), 0
                    )
                    if float(sale.total_amount) <= 0:
                        sale.payment_status = 'returned'

            stock_return = StockReturn(
                tenant_id     = tenant_id,
                sale_id       = sale_id if sale else None,
                product_id    = product_id,
                product_name  = product.name,
                quantity      = quantity,
                refund_amount = refund_amount,
                reason        = reason or None,
                refund_method = refund_method,
                recorded_by   = user.id,
            )
            db.session.add(stock_return)
            db.session.commit()

            return {
                **stock_return.to_dict(),
                "sale_updated":   sale is not None,
                "new_sale_total": float(sale.total_amount) if sale else None,
            }, 201

        except Exception as e:
            db.session.rollback()
            return {"message": f"Error: {str(e)}"}, 500


class ReturnResource(Resource):

    @jwt_required()
    def delete(self, return_id):
        tenant_id = get_tenant_id()
        if not is_admin():
            return {"message": "Admin access required."}, 403

        stock_return = StockReturn.query.filter_by(
            id=return_id, tenant_id=tenant_id
        ).first_or_404()

        try:
            product = Product.query.filter_by(
                id=stock_return.product_id, tenant_id=tenant_id
            ).first()
            if product:
                product.stock = float(product.stock) - stock_return.quantity

            if stock_return.sale_id:
                sale = Sale.query.filter_by(
                    id=stock_return.sale_id, tenant_id=tenant_id
                ).first()
                if sale:
                    sale.total_amount = float(sale.total_amount) + float(stock_return.refund_amount)
                    sale.amount_paid  = float(sale.amount_paid)  + float(stock_return.refund_amount)
                    sale.change_given = max(
                        float(sale.amount_paid) - float(sale.total_amount), 0
                    )
                    if sale.payment_status == 'returned':
                        sale.payment_status = 'paid'

                    sale_item = SaleItem.query.filter_by(
                        tenant_id=tenant_id,
                        sale_id=stock_return.sale_id,
                        product_id=stock_return.product_id,
                    ).first()
                    if sale_item:
                        sale_item.quantity = float(sale_item.quantity) + stock_return.quantity

            db.session.delete(stock_return)
            db.session.commit()
            return {"message": "Return deleted, sale and stock restored."}, 200

        except Exception as e:
            db.session.rollback()
            return {"message": f"Error: {str(e)}"}, 500