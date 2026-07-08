from flask import request
from flask_restful import Resource
from models import Sale, SaleItem, Product, User
from extensions import db
from datetime import datetime, timezone
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.exc import IntegrityError
from decimal import Decimal  # ✅ FIXED: Missing import that caused 500 error

class SaleListResource(Resource):

    @jwt_required()
    def get(self):
        current_user_id = int(get_jwt_identity())
        user = User.query.get(current_user_id)
        if user and user.role == "admin":
            sales = Sale.query.order_by(Sale.sale_date.desc()).all()
        else:
            sales = Sale.query.filter_by(
                user_id = current_user_id
            ).order_by(Sale.sale_date.desc()).all()

        return [sale.to_dict() for sale in sales], 200

    @jwt_required()
    def post(self):
        user_id = int(get_jwt_identity())
        if not user_id:
            return {"error": "Unauthorized. Please log in."}, 401

        data           = request.get_json()
        transaction_id = data.get('transaction_id')
        items_data     = data.get('items')
        total_amount   = data.get('total_amount')
        amount_paid    = data.get('amount_paid')
        payment_method = data.get('payment_method', 'cash')
        sale_date_str  = data.get('sale_date')
        customer_name  = data.get('customer_name')
        customer_phone = data.get('customer_phone')
        cash_portion   = data.get('cash_portion',  None)
        mpesa_portion  = data.get('mpesa_portion', None)

        if not transaction_id:
            return {"message": "Missing transaction_id"}, 400

        if not items_data or not isinstance(items_data, list) or total_amount is None:
            return {"message": "Invalid sale data. Missing items or amounts."}, 400

        # Convert total_amount to float just in case it came as a string
        total_amount = float(total_amount)

        # ── Payment Validation ───────────────────────────────────────────
        if payment_method == 'credit':
            if not customer_name or not customer_phone:
                return {"message": "Customer name and phone are required for credit sales."}, 400
            payment_status = 'unpaid'
            amount_paid    = 0
            change_given   = 0
        else:
            # ✅ FIXED: If it's a direct M-Pesa, Card, or Split sale where frontend 
            # passes blank/null cash text input, default amount_paid to total_amount
            if amount_paid is None or amount_paid == "" or float(amount_paid) == 0:
                if payment_method in ['mpesa', 'card', 'split', 'm-pesa']:
                    amount_paid = total_amount

            if amount_paid is None:
                return {"message": "Amount paid is required."}, 400
            
            amount_paid  = float(amount_paid)
            change_given = amount_paid - total_amount
            payment_status = 'paid'

            if change_given < 0:
                return {"message": f"Amount paid (KSh {amount_paid}) is insufficient for total (KSh {total_amount})."}, 400

        try:
            # ── Idempotency check ─────────────────────────────────────────
            existing_sale = Sale.query.filter_by(transaction_id=transaction_id).first()
            if existing_sale:
                return existing_sale.to_dict(), 200

            sale_date = (
                datetime.fromisoformat(sale_date_str.replace("Z", "+00:00"))
                if sale_date_str
                else datetime.now(timezone.utc)
            )

            validated_items = []

            for item_data in items_data:
                product_id          = item_data.get('product_id')
                product_name        = item_data.get('name')
                quantity            = item_data.get('quantity')
                price_from_frontend = item_data.get('price')
                sale_type           = item_data.get('sale_type', 'retail')

                if not product_id or not product_name or not quantity or price_from_frontend is None:
                    raise ValueError("Invalid item data within sale.")

                product = Product.query.get(product_id)
                if not product:
                    raise ValueError(f"Product {product_id} not found")

                # ── Stock deduction + profit calculation ──────────────────
                if sale_type == 'wholesale' and product.carton_qty:
                    units_to_deduct = quantity * int(product.carton_qty)
                    total_revenue   = price_from_frontend * quantity
                    total_cost      = units_to_deduct * float(product.unit_price)
                    profit          = total_revenue - total_cost
                else:
                    units_to_deduct = quantity
                    profit          = (price_from_frontend - float(product.unit_price)) * quantity

                if float(product.stock) < units_to_deduct:
                    carton_info = (
                        f" ({int(float(product.stock)) // int(product.carton_qty)} cartons available)"
                        if product.carton_qty else ""
                    )
                    return {
                        "message": f"Not enough stock for {product.name}. "
                                   f"Available: {int(float(product.stock))} pcs{carton_info}"
                    }, 409

                validated_items.append({
                    "product":         product,
                    "quantity":        quantity,
                    "price":           price_from_frontend,
                    "profit":          profit,
                    "units_to_deduct": units_to_deduct,
                    "sale_type":       sale_type,
                })

            # ── Create Sale ───────────────────────────────────────────────
            new_sale = Sale(
                transaction_id = transaction_id,
                total_amount   = total_amount,
                amount_paid    = amount_paid,
                change_given   = change_given,
                payment_method = payment_method,
                sale_date      = sale_date,
                user_id        = user_id,
                customer_name  = customer_name,
                customer_phone = customer_phone,
                payment_status = payment_status,
                cash_amount    = Decimal(str(cash_portion))  if cash_portion  else None,
                mpesa_amount   = Decimal(str(mpesa_portion)) if mpesa_portion else None,
            )
            db.session.add(new_sale)
            db.session.flush()

            # ── Create SaleItems + deduct stock ───────────────────────────
            for item in validated_items:
                product = item["product"]
                product.stock = float(product.stock) - item["units_to_deduct"]

                sale_item = SaleItem(
                    sale_id    = new_sale.id,
                    product_id = product.id,
                    name       = product.name,
                    quantity   = item["quantity"],
                    price      = item["price"],
                    profit     = item["profit"],
                )
                db.session.add(sale_item)

            db.session.commit()
            return new_sale.to_dict(), 201

        except IntegrityError:
            db.session.rollback()
            existing_sale = Sale.query.filter_by(transaction_id=transaction_id).first()
            if existing_sale:
                return existing_sale.to_dict(), 200
            return {"message": "Database integrity error"}, 500

        except ValueError as e:
            db.session.rollback()
            return {"message": str(e)}, 400

        except Exception as e:
            db.session.rollback()
            return {"message": f"An unexpected error occurred: {str(e)}"}, 500