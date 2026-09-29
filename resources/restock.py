from flask import request
from flask_restful import Resource
from flask_jwt_extended import jwt_required
from models import Restock, Product, Supplier
from extensions import db
from datetime import datetime, timezone, timedelta
from sqlalchemy import func
from utils.tenant import get_tenant_id, current_user_and_tenant, is_admin


class RestockListResource(Resource):

    @jwt_required()
    def get(self):
        tenant_id = get_tenant_id()
        if not is_admin():
            return {"message": "Admin access required."}, 403

        restocks = Restock.query.filter_by(tenant_id=tenant_id)\
            .order_by(Restock.restocked_at.desc()).all()

        eat_offset  = timedelta(hours=3)
        now_eat     = datetime.now(timezone.utc) + eat_offset
        month_start = datetime(now_eat.year, now_eat.month, 1,
                               tzinfo=timezone.utc) - eat_offset

        month_total = db.session.query(func.sum(Restock.total_cost))\
            .filter(
                Restock.tenant_id    == tenant_id,
                Restock.restocked_at >= month_start,
            ).scalar() or 0

        return {
            "restocks":    [r.to_dict() for r in restocks],
            "month_total": float(month_total),
            "total_count": len(restocks),
        }, 200

    @jwt_required()
    def post(self):
        user, tenant_id = current_user_and_tenant()
        if not user or user.role != "admin":
            return {"message": "Admin access required."}, 403

        data              = request.get_json() or {}
        product_id        = data.get('product_id')
        cartons           = data.get('cartons')
        loose_pieces      = data.get('loose_pieces', 0)
        pcs_per_carton    = data.get('pcs_per_carton')
        cost_per_unit     = data.get('cost_per_unit')
        supplier_id       = data.get('supplier_id')
        notes             = data.get('notes', '').strip()
        pricing_method    = data.get('pricing_method', 'weighted_average')
        new_selling_price = data.get('new_selling_price')

        if not product_id or cost_per_unit is None:
            return {"message": "Product and cost per unit required."}, 400

        # ── SECURITY: product must belong to this tenant ──────────────────
        product = Product.query.filter_by(
            id=product_id, tenant_id=tenant_id
        ).first()
        if not product:
            return {"message": "Product not found."}, 404

        try:
            cost_per_unit  = float(cost_per_unit)
            cartons        = int(cartons or 0)
            loose_pieces   = int(loose_pieces or 0)
            pcs_per_carton = int(pcs_per_carton or product.carton_qty or 1)
        except (TypeError, ValueError):
            return {"message": "Invalid numbers."}, 400

        total_pieces = (cartons * pcs_per_carton) + loose_pieces
        if total_pieces <= 0:
            return {"message": "Quantity must be greater than 0."}, 400
        if cost_per_unit <= 0:
            return {"message": "Cost per unit must be greater than 0."}, 400

        total_cost = total_pieces * cost_per_unit

        # ── Supplier must also belong to this tenant ──────────────────────
        supplier_name = None
        if supplier_id:
            supplier = Supplier.query.filter_by(
                id=supplier_id, tenant_id=tenant_id
            ).first()
            if supplier:
                supplier_name = supplier.name
            else:
                supplier_id = None  # ignore a foreign supplier id silently

        try:
            old_stock         = float(product.stock or 0)
            old_price         = float(product.unit_price or 0)
            old_selling_price = float(product.price or 0)
            new_stock         = old_stock + total_pieces

            old_price_changed = abs(cost_per_unit - old_price) > 0.01

            if pricing_method == 'weighted_average' and old_price_changed:
                old_value     = old_stock * old_price
                new_value     = total_pieces * cost_per_unit
                new_avg_price = (old_value + new_value) / new_stock \
                                if new_stock > 0 else cost_per_unit
                product.unit_price = round(new_avg_price, 2)
            elif pricing_method == 'override' and old_price_changed:
                product.unit_price = cost_per_unit

            selling_price_changed = False
            if new_selling_price is not None and str(new_selling_price).strip() != "":
                try:
                    new_selling = float(new_selling_price)
                    if new_selling <= 0:
                        return {"message": "Selling price must be greater than 0."}, 400
                    if abs(new_selling - old_selling_price) > 0.01:
                        product.price = round(new_selling, 2)
                        selling_price_changed = True
                except (TypeError, ValueError):
                    return {"message": "Invalid selling price."}, 400

            product.stock = new_stock

            restock = Restock(
                tenant_id     = tenant_id,
                product_id    = product_id,
                product_name  = product.name,
                quantity      = total_pieces,
                cartons       = cartons if cartons > 0 else None,
                cost_per_unit = cost_per_unit,
                total_cost    = total_cost,
                supplier_id   = supplier_id,
                supplier_name = supplier_name,
                notes         = notes or None,
                recorded_by   = user.id,
            )
            db.session.add(restock)
            db.session.commit()

            return {
                **restock.to_dict(),
                "old_buying_price":      round(old_price, 2),
                "new_buying_price":      float(product.unit_price),
                "old_selling_price":     round(old_selling_price, 2),
                "new_selling_price":     float(product.price),
                "selling_price_changed": selling_price_changed,
                "pricing_method":        pricing_method,
            }, 201

        except Exception as e:
            db.session.rollback()
            return {"message": f"Error: {str(e)}"}, 500


class RestockResource(Resource):

    @jwt_required()
    def delete(self, restock_id):
        tenant_id = get_tenant_id()
        if not is_admin():
            return {"message": "Admin access required."}, 403

        restock = Restock.query.filter_by(
            id=restock_id, tenant_id=tenant_id
        ).first_or_404()

        product = Product.query.filter_by(
            id=restock.product_id, tenant_id=tenant_id
        ).first()
        if product:
            product.stock = float(product.stock) - restock.quantity
            if product.stock < 0:
                product.stock = 0

        db.session.delete(restock)
        db.session.commit()
        return {"message": "Restock deleted, stock adjusted"}, 200