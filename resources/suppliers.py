from flask import request
from flask_restful import Resource
from models import Supplier
from extensions import db
from flask_jwt_extended import jwt_required
from utils.tenant import get_tenant_id, is_admin


class SupplierListResource(Resource):

    @jwt_required()
    def get(self):
        tenant_id = get_tenant_id()
        if tenant_id is None:
            return {"message": "Unauthorized."}, 401

        suppliers = Supplier.query.filter_by(tenant_id=tenant_id)\
            .order_by(Supplier.name).all()
        return [s.to_dict() for s in suppliers], 200

    @jwt_required()
    def post(self):
        tenant_id = get_tenant_id()
        if not is_admin():
            return {"message": "Admin access required."}, 403

        data  = request.get_json() or {}
        name  = data.get("name",  "").strip()
        phone = data.get("phone", "").strip()
        if not name or not phone:
            return {"message": "Name and phone are required."}, 400

        supplier = Supplier(
            tenant_id = tenant_id,
            name      = name,
            phone     = phone,
            email     = (data.get("email")   or "").strip() or None,
            address   = (data.get("address") or "").strip() or None,
        )
        db.session.add(supplier)
        db.session.commit()
        return supplier.to_dict(), 201


class SupplierResource(Resource):

    @jwt_required()
    def patch(self, supplier_id):
        tenant_id = get_tenant_id()
        if not is_admin():
            return {"message": "Admin access required."}, 403

        supplier = Supplier.query.filter_by(
            id=supplier_id, tenant_id=tenant_id
        ).first_or_404()
        data = request.get_json() or {}

        supplier.name    = data.get("name",    supplier.name)
        supplier.phone   = data.get("phone",   supplier.phone)
        supplier.email   = data.get("email",   supplier.email)
        supplier.address = data.get("address", supplier.address)
        db.session.commit()
        return supplier.to_dict(), 200

    @jwt_required()
    def delete(self, supplier_id):
        tenant_id = get_tenant_id()
        if not is_admin():
            return {"message": "Admin access required."}, 403

        supplier = Supplier.query.filter_by(
            id=supplier_id, tenant_id=tenant_id
        ).first_or_404()
        db.session.delete(supplier)
        db.session.commit()
        return {"message": "Supplier deleted"}, 200