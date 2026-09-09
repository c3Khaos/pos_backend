# resources/onboard.py — full updated version
import os
from flask import request
from flask_restful import Resource
from flask_jwt_extended import create_access_token
from models import Tenant, User, ShopSettings, Sale, Product
from extensions import db


def verify_superadmin():
    secret   = os.environ.get("SUPERADMIN_SECRET")
    provided = request.headers.get("X-Superadmin-Secret", "")
    return secret and provided == secret


class OnboardResource(Resource):
    def post(self):
        secret   = os.environ.get("ONBOARD_SECRET")
        provided = request.headers.get("X-Onboard-Secret", "")
        if secret and provided != secret:
            return {"message": "Invalid onboard secret."}, 401

        data = request.get_json()

        shop_name      = (data.get("shop_name")      or "").strip()
        admin_username = (data.get("admin_username")  or "").strip()
        admin_password =  data.get("admin_password",  "")
        phone          = (data.get("phone")           or "").strip()
        email          = (data.get("email")           or "").strip() or None
        plan           = (data.get("plan")            or "starter").strip()

        if not shop_name:
            return {"message": "shop_name is required."}, 400
        if not admin_username:
            return {"message": "admin_username is required."}, 400
        if not admin_password or len(admin_password) < 6:
            return {"message": "admin_password must be at least 6 characters."}, 400

        try:
            base_slug = shop_name.lower().replace(" ", "-")
            slug      = "".join(c for c in base_slug if c.isalnum() or c == "-")[:50]

            if Tenant.query.filter_by(slug=slug).first():
                slug = f"{slug}-{Tenant.query.count() + 1}"

            tenant = Tenant(
                name      = shop_name,
                slug      = slug,
                phone     = phone or None,
                email     = email,
                plan      = plan,
                is_active = True,
            )
            db.session.add(tenant)
            db.session.flush()

            existing_user = User.query.filter_by(
                tenant_id=tenant.id,
                username=admin_username,
            ).first()
            if existing_user:
                db.session.rollback()
                return {"message": "Username already taken."}, 409

            admin = User(
                tenant_id = tenant.id,
                username  = admin_username,
                email     = email,
                role      = "admin",
                active    = True,
            )
            admin.set_password(admin_password)
            db.session.add(admin)

            settings = ShopSettings(
                tenant_id           = tenant.id,
                shop_name           = shop_name,
                shop_phone          = phone or None,
                receipt_footer      = "Thank you for your business!",
                low_stock_threshold = 5,
            )
            db.session.add(settings)
            db.session.commit()

            access_token = create_access_token(
                identity=str(admin.id),
                additional_claims={
                    "role":      "admin",
                    "tenant_id": tenant.id,
                }
            )

            return {
                "message":      f"Shop '{shop_name}' onboarded successfully.",
                "access_token": access_token,
                "tenant":       tenant.to_dict(),
                "user":         admin.to_dict(),
            }, 201

        except Exception as e:
            db.session.rollback()
            return {"message": f"Onboarding failed: {str(e)}"}, 500


class SuperAdminResource(Resource):
    """GET /superadmin/tenants — list all tenants with stats"""

    def get(self):
        if not verify_superadmin():
            return {"message": "Unauthorized."}, 401

        tenants = Tenant.query.order_by(Tenant.created_at.desc()).all()
        result  = []

        for t in tenants:
            user_count    = User.query.filter_by(tenant_id=t.id).count()
            sale_count    = Sale.query.filter_by(tenant_id=t.id).count()
            product_count = Product.query.filter_by(tenant_id=t.id).count()
            settings      = ShopSettings.query.filter_by(tenant_id=t.id).first()

            result.append({
                **t.to_dict(),
                "user_count":    user_count,
                "sale_count":    sale_count,
                "product_count": product_count,
                "shop_phone":    settings.shop_phone if settings else None,
            })

        return {
            "tenants": result,
            "total":   len(result),
        }, 200


class SuperAdminTenantResource(Resource):
    """
    GET    /superadmin/tenants/<id>  — single tenant detail
    PATCH  /superadmin/tenants/<id>  — update plan or active status
    DELETE /superadmin/tenants/<id>  — deactivate tenant
    """

    def get(self, tenant_id):
        if not verify_superadmin():
            return {"message": "Unauthorized."}, 401

        tenant = Tenant.query.get_or_404(tenant_id)

        users    = User.query.filter_by(tenant_id=tenant_id).all()
        sales    = Sale.query.filter_by(tenant_id=tenant_id).count()
        products = Product.query.filter_by(tenant_id=tenant_id).count()
        settings = ShopSettings.query.filter_by(tenant_id=tenant_id).first()

        return {
            "tenant":   tenant.to_dict(),
            "users":    [u.to_dict() for u in users],
            "stats": {
                "sales":    sales,
                "products": products,
            },
            "settings": settings.to_dict() if settings else None,
        }, 200

    def patch(self, tenant_id):
        if not verify_superadmin():
            return {"message": "Unauthorized."}, 401

        tenant = Tenant.query.get_or_404(tenant_id)
        data   = request.get_json()

        if "plan"      in data: tenant.plan      = data["plan"]
        if "is_active" in data: tenant.is_active = data["is_active"]
        if "name"      in data: tenant.name      = data["name"]

        db.session.commit()
        return {
            "message": "Tenant updated.",
            "tenant":  tenant.to_dict(),
        }, 200

    def delete(self, tenant_id):
        if not verify_superadmin():
            return {"message": "Unauthorized."}, 401

        tenant = Tenant.query.get_or_404(tenant_id)

        # Soft delete — deactivate, don't destroy data
        tenant.is_active = False
        db.session.commit()

        return {
            "message": f"Tenant '{tenant.name}' deactivated. Data preserved."
        }, 200