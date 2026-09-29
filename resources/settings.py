from flask import request
from flask_restful import Resource
from flask_jwt_extended import jwt_required
from models import ShopSettings
from extensions import db
from utils.tenant import get_tenant_id, current_user_and_tenant, is_admin


def _get_or_create_settings(tenant_id):
    """Fetch this tenant's settings row, creating a default one if missing."""
    settings = ShopSettings.query.filter_by(tenant_id=tenant_id).first()
    if not settings:
        settings = ShopSettings(tenant_id=tenant_id)
        db.session.add(settings)
        db.session.commit()
    return settings


class SettingsResource(Resource):
    """
    GET  /settings  — fetch THIS tenant's shop settings
    PATCH /settings — update settings (admin only)
    """

    # ── SECURITY: this was PUBLIC (no auth) and returned the first/only
    # settings row. Under multi-tenancy that would leak one shop's settings
    # to anyone AND has no way to know which shop is asking. Now it requires
    # auth and returns strictly the caller's tenant's settings.
    @jwt_required()
    def get(self):
        tenant_id = get_tenant_id()
        if tenant_id is None:
            return {"message": "Unauthorized."}, 401

        settings = _get_or_create_settings(tenant_id)
        return settings.to_dict(), 200

    @jwt_required()
    def patch(self):
        tenant_id = get_tenant_id()
        if not is_admin():
            return {"message": "Admin access required."}, 403

        data     = request.get_json() or {}
        settings = _get_or_create_settings(tenant_id)

        if "shop_name" in data:
            name = (data["shop_name"] or "").strip()
            if not name:
                return {"message": "Shop name cannot be empty."}, 400
            settings.shop_name = name
        if "shop_tagline"   in data: settings.shop_tagline   = (data["shop_tagline"]   or "").strip() or None
        if "shop_phone"     in data: settings.shop_phone     = (data["shop_phone"]     or "").strip() or None
        if "shop_address"   in data: settings.shop_address   = (data["shop_address"]   or "").strip() or None
        if "receipt_footer" in data: settings.receipt_footer = (data["receipt_footer"] or "").strip() or None
        if "low_stock_threshold" in data:
            try:
                threshold = int(data["low_stock_threshold"])
                if threshold < 0:
                    return {"message": "Threshold cannot be negative."}, 400
                settings.low_stock_threshold = threshold
            except (ValueError, TypeError):
                return {"message": "Threshold must be a whole number."}, 400

        db.session.commit()
        return settings.to_dict(), 200


class ChangePasswordResource(Resource):
    """POST /settings/change-password — any logged-in user changes their own"""

    @jwt_required()
    def post(self):
        # ── SECURITY: resolve the user AND confirm they belong to the tenant
        # in the JWT before touching any password. A stale token from a user
        # moved/removed from a tenant can't change a password here.
        user, tenant_id = current_user_and_tenant()
        if not user or tenant_id is None:
            return {"message": "Unauthorized."}, 401

        data             = request.get_json() or {}
        current_password = data.get("current_password", "")
        new_password     = data.get("new_password",     "")

        if not current_password or not new_password:
            return {"message": "Both current and new password are required."}, 400

        if len(new_password) < 6:
            return {"message": "New password must be at least 6 characters."}, 400

        if not user.check_password(current_password):
            return {"message": "Current password is incorrect."}, 401

        user.set_password(new_password)
        db.session.commit()
        return {"message": "Password changed successfully."}, 200