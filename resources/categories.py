from flask import request
from flask_restful import Resource
from flask_jwt_extended import jwt_required
from models import Category, Product
from extensions import db
from sqlalchemy import func
from utils.tenant import get_tenant_id, is_admin


class CategoryListResource(Resource):
    """
    GET  /categories — list this tenant's categories (any logged-in user)
    POST /categories — add new (admin only)
    """

    @jwt_required()
    def get(self):
        tenant_id = get_tenant_id()
        if tenant_id is None:
            return {"message": "Unauthorized."}, 401

        categories = Category.query.filter_by(tenant_id=tenant_id)\
            .order_by(Category.name).all()
        return [c.to_dict() for c in categories], 200

    @jwt_required()
    def post(self):
        tenant_id = get_tenant_id()
        if not is_admin():
            return {"message": "Admin access required."}, 403

        data = request.get_json() or {}
        name = (data.get("name") or "").strip()

        if not name:
            return {"message": "Category name is required."}, 400

        # ── Duplicate check scoped to THIS tenant (case-insensitive) ──────
        existing = Category.query.filter(
            Category.tenant_id == tenant_id,
            func.lower(Category.name) == name.lower()
        ).first()
        if existing:
            return {"message": f"Category '{name}' already exists."}, 409

        category = Category(tenant_id=tenant_id, name=name)
        db.session.add(category)
        db.session.commit()
        return category.to_dict(), 201


class CategoryResource(Resource):
    """DELETE /categories/<id> — remove (admin only, blocked if in use)"""

    @jwt_required()
    def delete(self, category_id):
        tenant_id = get_tenant_id()
        if not is_admin():
            return {"message": "Admin access required."}, 403

        # ── SECURITY: scope the lookup to the tenant so an admin of Shop A
        # can't delete Shop B's category by guessing an id (IDOR).
        category = Category.query.filter_by(
            id=category_id, tenant_id=tenant_id
        ).first_or_404()

        # ── Only count products IN THIS TENANT using the category ─────────
        in_use = Product.query.filter(
            Product.tenant_id == tenant_id,
            func.lower(Product.category) == category.name.lower()
        ).count()

        if in_use > 0:
            return {
                "message": f"Can't delete — {in_use} product(s) still use "
                           f"'{category.name}'. Reassign them first."
            }, 409

        db.session.delete(category)
        db.session.commit()
        return {"message": f"Category '{category.name}' deleted."}, 200