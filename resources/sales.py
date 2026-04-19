from flask import request
from flask_restful import Resource
from models import Sale, SaleItem, Product
from extensions import db
from datetime import datetime
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.exc import IntegrityError


class SaleListResource(Resource):

    @jwt_required()
    def get(self):
        current_user_id = get_jwt_identity()
        sales = Sale.query.filter_by(user_id=current_user_id).all()
        return [sale.to_dict() for sale in sales], 200

    @jwt_required()
    def post(self):
        user_id = get_jwt_identity()
        if not user_id:
            return {"error": "Unauthorized. Please log in."}, 401

        data = request.get_json()

        transaction_id = data.get('transaction_id')
        items_data     = data.get('items')
        total_amount   = data.get('total_amount')
        amount_paid    = data.get('amount_paid')
        payment_method = data.get('payment_method', 'cash')
        sale_date_str  = data.get('sale_date')

        # 👇 NEW — credit sale fields
        customer_name  = data.get('customer_name')
        customer_phone = data.get('customer_phone')

        if not transaction_id:
            return {"message": "Missing transaction_id"}, 400

        if not items_data or not isinstance(items_data, list) or total_amount is None:
            return {"message": "Invalid sale data. Missing items or amounts."}, 400

        # 👇 NEW — credit sale validation
        if payment_method == 'credit':
            if not customer_name or not customer_phone:
                return {"message": "Customer name and phone are required for credit sales."}, 400
            payment_status = 'unpaid'
            amount_paid    = 0          # nothing paid yet
            change_given   = 0
        else:
            if amount_paid is None:
                return {"message": "Amount paid is required."}, 400
            change_given   = amount_paid - total_amount
            payment_status = 'paid'
            if change_given < 0:
                return {"message": "Amount paid is insufficient."}, 400

        try:
            # --- idempotency check ---
            existing_sale = Sale.query.filter_by(transaction_id=transaction_id).first()
            if existing_sale:
                return existing_sale.to_dict(), 200

            sale_date = (
                datetime.fromisoformat(sale_date_str.replace("Z", "+00:00"))
                if sale_date_str else datetime.utcnow()
            )

            validated_items = []

            # --- validate products first ---
            for item_data in items_data:
                product_id         = item_data.get('product_id')
                product_name       = item_data.get('name')
                quantity           = item_data.get('quantity')
                price_from_frontend = item_data.get('price')

                if not product_id or not product_name or not quantity or price_from_frontend is None:
                    raise ValueError("Invalid item data within sale.")

                product = Product.query.get(product_id)
                if not product:
                    raise ValueError(f"Product {product_id} not found")

                if product.stock < quantity:
                    return {
                        "message": f"Not enough stock for {product.name}. Available: {product.stock}"
                    }, 409

                validated_items.append({
                    "product":  product,
                    "quantity": quantity,
                    "price":    price_from_frontend,
                    "profit":   (price_from_frontend - product.unit_price) * quantity
                })

            # --- create sale ---
            new_sale = Sale(
                transaction_id = transaction_id,
                total_amount   = total_amount,
                amount_paid    = amount_paid,
                change_given   = change_given,
                payment_method = payment_method,
                sale_date      = sale_date,
                user_id        = user_id,
                # 👇 NEW
                customer_name  = customer_name,
                customer_phone = customer_phone,
                payment_status = payment_status,
            )

            db.session.add(new_sale)
            db.session.flush()

            # --- create sale items + update stock (even for credit) ---
            for item in validated_items:
                product  = item["product"]
                quantity = item["quantity"]

                product.stock -= quantity

                sale_item = SaleItem(
                    sale_id    = new_sale.id,
                    product_id = product.id,
                    name       = product.name,
                    quantity   = quantity,
                    price      = item["price"],
                    profit     = item["profit"]
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
            print(f"Error processing sale: {e}")
            return {"message": "An unexpected error occurred during sale processing."}, 500