from flask import request
from flask_restful import Resource
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Restock, Product, Supplier, User
from extensions import db
from datetime import datetime, timezone, timedelta
from sqlalchemy import func


def is_admin(user_id):
    user = User.query.get(user_id)
    return user and user.role == 'admin'


class RestockListResource(Resource):
    """
    GET  /restock — list all restocks + month total
    POST /restock — record new stock arrival
    """

    @jwt_required()
    def get(self):
        user_id = int(get_jwt_identity())
        if not is_admin(user_id):
            return {"message": "Admin access required."}, 403

        restocks = Restock.query.order_by(Restock.restocked_at.desc()).all()

        # Month total
        eat_offset  = timedelta(hours=3)
        now_eat     = datetime.now(timezone.utc) + eat_offset
        month_start = datetime(now_eat.year, now_eat.month, 1,
                               tzinfo=timezone.utc) - eat_offset

        month_total = db.session.query(func.sum(Restock.total_cost))\
            .filter(Restock.restocked_at >= month_start)\
            .scalar() or 0

        return {
            "restocks":    [r.to_dict() for r in restocks],
            "month_total": float(month_total),
            "total_count": len(restocks),
        }, 200

    @jwt_required()
    def post(self):
        user_id = int(get_jwt_identity())
        if not is_admin(user_id):
            return {"message": "Admin access required."}, 403

        data = request.get_json()

        product_id     = data.get('product_id')
        cartons        = data.get('cartons')
        loose_pieces   = data.get('loose_pieces', 0)
        pcs_per_carton = data.get('pcs_per_carton')
        cost_per_unit  = data.get('cost_per_unit')
        supplier_id    = data.get('supplier_id')
        notes          = data.get('notes', '').strip()
        pricing_method = data.get('pricing_method', 'weighted_average')

        if not product_id or cost_per_unit is None:
            return {"message": "Product and cost per unit required."}, 400

        product = Product.query.get(product_id)
        if not product:
            return {"message": "Product not found."}, 404

        try:
            cost_per_unit  = float(cost_per_unit)
            cartons        = int(cartons or 0)
            loose_pieces   = int(loose_pieces or 0)
            # Use form value, fall back to product's saved carton_qty, then 1
            pcs_per_carton = int(pcs_per_carton or product.carton_qty or 1)
        except (TypeError, ValueError):
            return {"message": "Invalid numbers."}, 400

        # ── Total pieces being added ──────────────────────────────────────
        total_pieces = (cartons * pcs_per_carton) + loose_pieces

        if total_pieces <= 0:
            return {"message": "Quantity must be greater than 0."}, 400

        if cost_per_unit <= 0:
            return {"message": "Cost per unit must be greater than 0."}, 400

        total_cost = total_pieces * cost_per_unit

        # ── Get supplier name if linked ───────────────────────────────────
        supplier_name = None
        if supplier_id:
            supplier = Supplier.query.get(supplier_id)
            if supplier:
                supplier_name = supplier.name

        try:
            # ── PRICING LOGIC ─────────────────────────────────────────────
            old_stock = float(product.stock or 0)
            old_price = float(product.unit_price or 0)
            new_stock = old_stock + total_pieces

            # Has the price changed?
            old_price_changed = abs(cost_per_unit - old_price) > 0.01

            if pricing_method == 'weighted_average' and old_price_changed:
                # Weighted Average Cost (WAC)
                # = (old_value + new_value) / total_pieces
                old_value     = old_stock * old_price
                new_value     = total_pieces * cost_per_unit
                new_avg_price = (old_value + new_value) / new_stock \
                                if new_stock > 0 else cost_per_unit
                product.unit_price = round(new_avg_price, 2)

            elif pricing_method == 'override' and old_price_changed:
                # Just use the new price for everything
                product.unit_price = cost_per_unit

            # If pricing_method == 'keep' → don't touch buying price

            # ── Increase stock ─────────────────────────────────────────────
            product.stock = new_stock

            # ── Record the restock ─────────────────────────────────────────
            restock = Restock(
                product_id    = product_id,
                product_name  = product.name,
                quantity      = total_pieces,
                cartons       = cartons if cartons > 0 else None,
                cost_per_unit = cost_per_unit,
                total_cost    = total_cost,
                supplier_id   = supplier_id,
                supplier_name = supplier_name,
                notes         = notes or None,
                recorded_by   = user_id,
            )
            db.session.add(restock)
            db.session.commit()

            # Return restock + price info for UI feedback
            return {
                **restock.to_dict(),
                "old_buying_price": round(old_price, 2),
                "new_buying_price": float(product.unit_price),
                "pricing_method":   pricing_method,
            }, 201

        except Exception as e:
            db.session.rollback()
            return {"message": f"Error: {str(e)}"}, 500


class RestockResource(Resource):
    """DELETE /restock/<id> — reverse a restock"""

    @jwt_required()
    def delete(self, restock_id):
        user_id = int(get_jwt_identity())
        if not is_admin(user_id):
            return {"message": "Admin access required."}, 403

        restock = Restock.query.get_or_404(restock_id)
        product = Product.query.get(restock.product_id)
        if product:
            product.stock = float(product.stock) - restock.quantity
            if product.stock < 0:
                product.stock = 0

        db.session.delete(restock)
        db.session.commit()
        return {"message": "Restock deleted, stock adjusted"}, 200