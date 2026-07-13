from flask import request
from flask_restful import Resource
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import ShopSettings, User
from extensions import db


def is_admin(user_id):
    user = User.query.get(user_id)
    return user and user.role == 'admin'


class SettingsResource(Resource):
    """
    GET  /settings  — fetch current shop settings (public — needed for receipt)
    PATCH /settings — update settings (admin only)
    """

    def get(self):
        # Public — receipt and other frontend components need this without auth
        settings = ShopSettings.query.first()
        if not settings:
            # Auto-create defaults on first access
            settings = ShopSettings()
            db.session.add(settings)
            db.session.commit()
        return settings.to_dict(), 200

    @jwt_required()
    def patch(self):
        user_id = int(get_jwt_identity())
        if not is_admin(user_id):
            return {"message": "Admin access required."}, 403

        data = request.get_json()

        settings = ShopSettings.query.first()
        if not settings:
            settings = ShopSettings()
            db.session.add(settings)

        # Update only fields that were sent
        if "shop_name"           in data: settings.shop_name           = data["shop_name"].strip()
        if "shop_tagline"        in data: settings.shop_tagline        = data["shop_tagline"].strip() or None
        if "shop_phone"          in data: settings.shop_phone          = data["shop_phone"].strip() or None
        if "shop_address"        in data: settings.shop_address        = data["shop_address"].strip() or None
        if "receipt_footer"      in data: settings.receipt_footer      = data["receipt_footer"].strip() or None
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
    """POST /settings/change-password — any logged-in user can change their own"""

    @jwt_required()
    def post(self):
        user_id = int(get_jwt_identity())
        data    = request.get_json()

        current_password = data.get("current_password", "")
        new_password     = data.get("new_password",     "")

        if not current_password or not new_password:
            return {"message": "Both current and new password are required."}, 400

        if len(new_password) < 6:
            return {"message": "New password must be at least 6 characters."}, 400

        user = User.query.get(user_id)
        if not user:
            return {"message": "User not found."}, 404

        if not user.check_password(current_password):
            return {"message": "Current password is incorrect."}, 401

        user.set_password(new_password)
        db.session.commit()
        return {"message": "Password changed successfully."}, 200