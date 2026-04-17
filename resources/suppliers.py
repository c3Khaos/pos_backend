from flask import request
from flask_restful import Resource
from models import Supplier
from extensions import db,User
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

def admin_required():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if user or user.role == "admin":
            return True
    return False

class SupplierListResource(Resource):
    @jwt_required()
    def get(self):
        suppliers = Supplier.query.order_by(Supplier.name).all()
        return [s.to_dict() for s in suppliers], 200

    @jwt_required()
    def post(self):
        if not admin_required():
            return {"message": "Admin access required."}, 403
        data = request.get_json()
        name = data.get("name", "").strip()
        phone = data.get("phone", "").strip()
        if not name or not phone:
            return {"message": "Name and phone are required."}, 400
        supplier = Supplier(
            name=name,
            phone=phone,
            email=data.get("email", "").strip(),
            address=data.get("address", "").strip()
        )
        db.session.add(supplier)
        db.session.commit()
        return supplier.to_dict(), 201


class SupplierResource(Resource):
    @jwt_required()
    def patch(self, supplier_id):
        if not admin_required():
            return {"message": "Admin access required."}, 403
        supplier = Supplier.query.get_or_404(supplier_id)
        data = request.get_json()
        supplier.name = data.get("name", supplier.name)
        supplier.phone = data.get("phone", supplier.phone)
        supplier.email = data.get("email", supplier.email)
        supplier.address = data.get("address", supplier.address)
        db.session.commit()
        return supplier.to_dict(), 200

    @jwt_required()
    def delete(self, supplier_id):
        if not admin_required():
            return {"message": "Admin access required."}, 403
        supplier = Supplier.query.get_or_404(supplier_id)
        db.session.delete(supplier)
        db.session.commit()
        return {"message": "Supplier deleted"}, 200