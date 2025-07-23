from flask import request, session
from flask_restful import Resource
from models import Sale, User, SaleItem
from extensions import db
from datetime import datetime

from flask_jwt_extended import jwt_required, get_jwt_identity

class SaleListResource(Resource):
    @jwt_required()
    def get(self):
        current_user_id = get_jwt_identity()
        sales = sales = Sale.query.filter_by(user_id=current_user_id).all()
        return [sale.to_dict() for sale in sales], 200
    @jwt_required()
    def post(self):
        user_id  = get_jwt_identity()
        if not user_id:
            return {"error": "Unauthorized. Please log in."}, 401

        data = request.get_json()
        # debugging mode
        print("Received sale data:", data) 
        
        #validate incoming data
        items_data = data.get('items')
        total_amount = data.get('total_amount')
        amount_paid = data.get('amount_paid')
        payment_method = data.get('payment_method', 'cash')
        sale_date_str = data.get('sale_date')

        if not items_data or not isinstance(items_data,list) or not total_amount is not None or not amount_paid is not None:
            return {"message":"Invalid sale data.Missing items or amounts."},400
        
        try:
            #calculate change to ensure accuracy
            change_given = amount_paid - total_amount
            if change_given < 0:
                return {"message": "Amount paid is insufficient."}, 400
            
            #convert sale_date to datetime object
            sale_date = datetime.fromisoformat(sale_date_str.replace ("Z",'+00:00')) if sale_date_str else datetime.utcnow()

            # main sale record  (transaction header)
            new_sale = Sale(
                total_amount=total_amount,
                amount_paid=amount_paid,
                change_given=change_given,
                payment_method=payment_method,
                sale_date=sale_date, 
                user_id=user_id
            )

            db.session.add(new_sale)
            db.session.flush() # This assigns an ID to new_sale before committing

            for item_data in items_data:
                product_id = item_data.get('product_id')
                product_name = item_data.get('name')
                quantity = item_data.get('quantity')
                price_from_frontend = item_data.get('price')

                if not product_id or not product_name or not quantity or not price_from_frontend:
                    raise ValueError("Invalid item data within sale.")
                

                new_sale_item = SaleItem(
                    sale_id=new_sale.id, 
                    product_id=product_id,
                    name=product_name,
                    quantity=quantity,
                    price=price_from_frontend,
                    
                )
                db.session.add(new_sale_item)

            db.session.commit() 

            return new_sale.to_dict(), 201
        

        except ValueError as e:
            db.session.rollback() 
            return {"message": str(e)}, 400
        except Exception as e:
            db.session.rollback() 
            print(f"Error processing sale: {e}") 
            return {"message": "An unexpected error occurred during sale processing."}, 500




